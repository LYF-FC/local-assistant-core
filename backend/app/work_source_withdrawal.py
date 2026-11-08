"""Reviewed synthetic source withdrawal and bounded derived-note/copy redaction."""

import argparse
import hashlib
import hmac
import re
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from app import (
    work_capture_worker,
    work_confirmation_worker,
    work_drafts,
    work_lifecycle,
    work_notes_worker,
)
from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import validate_target
from app.work_suppression_file import canonical


class Request(work_lifecycle.Contract):
    database: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9_]+$")
    operator_id: UUID
    workspace_id: UUID
    source_ids: tuple[UUID, ...] = Field(min_length=1, max_length=10)
    issued_at: datetime | None = None
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    decision: Literal["preview", "withdraw_sources"] = "preview"

    @model_validator(mode="after")
    def valid(self):
        if self.source_ids != tuple(sorted(set(self.source_ids))):
            raise ValueError("Select sorted unique source UUIDs")
        if self.issued_at is not None:
            work_lifecycle.clock(self.issued_at)
        if self.decision == "withdraw_sources" and (
            self.issued_at is None or self.reviewed_hash is None
        ):
            raise ValueError("Exact issued plan and explicit decision required")
        if self.decision == "preview" and self.reviewed_hash is not None:
            raise ValueError("Preview cannot carry apply authority")
        return self


def _fresh(db, issued):
    now = work_drafts._now(db)
    if not now - timedelta(minutes=5) <= issued <= now:
        raise ValueError("Use a current server-issued review")


def _begin(db, request):
    validate_target(settings.env)
    if (
        not isinstance(request, Request)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Typed local transaction required")
    profile = db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),bool_and(current_user=pg_get_userbyid(relowner)),count(*) FROM pg_class WHERE oid IN ('work.source_registry'::regclass,'work.drafts'::regclass,'work.draft_revisions'::regclass,'work.capture_intents'::regclass,'work.draft_reviews'::regclass,'work.parties'::regclass,'public.work_confirmation_requests'::regclass,'public.work_workspaces'::regclass,'public.work_access_grants'::regclass,'public.users'::regclass,'public.audit_events'::regclass) GROUP BY 1,2"
    ).fetchone()
    if profile != (True, "read committed", True, 11):
        raise ValueError("Clean READ COMMITTED registry/storage/audit owner required")
    target = db.execute(
        "SELECT datname,oid FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if target[0] != request.database or target[0] != settings.postgres_db:
        raise ValueError("Explicit configured/actual database must match")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    if not db.execute("SELECT pg_try_advisory_xact_lock(%s,%s)", REGISTRY_KEY).fetchone()[0]:
        raise ValueError("Registry busy; stop consumers before retry")
    db.execute(
        "LOCK TABLE public.work_workspaces,public.work_access_grants,work.source_registry,work.drafts,work.draft_revisions,work.capture_intents,work.draft_reviews,public.work_confirmation_requests IN EXCLUSIVE MODE NOWAIT"
    )
    if not db.execute(
        "SELECT 1 FROM public.users u JOIN public.user_scopes us ON us.user_id=u.id JOIN public.scopes s ON s.id=us.scope_id WHERE u.id=%s AND u.is_active AND s.key='technical_admin' FOR SHARE OF u,us,s NOWAIT",
        (request.operator_id,),
    ).fetchone():
        raise ValueError("Active technical-admin audit reference required")
    workspace = db.execute(
        "SELECT slug,is_active FROM public.work_workspaces WHERE id=%s", (request.workspace_id,)
    ).fetchone()
    if (
        workspace is None
        or workspace[1]
        or not re.fullmatch(r"synthetic-[a-z0-9][a-z0-9_-]{0,53}", workspace[0])
    ):
        raise ValueError("Disabled synthetic workspace required")
    if db.execute(
        "SELECT 1 FROM public.work_access_grants WHERE workspace_id=%s LIMIT 1",
        (request.workspace_id,),
    ).fetchone():
        raise ValueError("Remove all workspace grants first")
    db.execute("SET LOCAL butler.restore_suppression='reviewed'")
    db.execute("SET LOCAL butler.restore_requests='reviewed'")
    if not db.execute(
        "SELECT work.restore_suppression_allowed(%s),work.restore_requests_allowed(%s)",
        (request.workspace_id, request.workspace_id),
    ).fetchone() == (True, True):
        raise ValueError("Existing quarantined redaction authority required")
    return target


def _notes(db, workspace, sources):
    rows = db.execute(
        "WITH related AS (SELECT d.id,d.revision,d.state,COALESCE((d.snapshot->'source_ids') ?| %s::text[],false) AS current_reference,EXISTS(SELECT 1 FROM work.draft_revisions r WHERE r.workspace_id=d.workspace_id AND r.record_id=d.id AND (r.snapshot->'source_ids') ?| %s::text[]) AS historical_reference FROM work.drafts d WHERE d.workspace_id=%s AND d.state<>'forgotten') SELECT * FROM related WHERE current_reference OR historical_reference ORDER BY id LIMIT 26",
        (sources, sources, workspace),
    ).fetchall()
    if len(rows) > 25:
        raise ValueError("Too many derived notes; no partial source withdrawal")
    return [
        {
            "id": str(row[0]),
            "revision": row[1],
            "state": row[2],
            "current_reference": row[3],
            "historical_reference": row[4],
        }
        for row in rows
    ]


def _linked(db, workspace, sources, note_ids):
    rows = db.execute(
        "SELECT * FROM (SELECT 'capture' AS kind,id,intent,target_record_id AS record_id,expected_revision AS revision,expires_at FROM work.capture_intents WHERE workspace_id=%s AND state='pending' AND (target_record_id=ANY(%s::uuid[]) OR COALESCE((payload->'draft'->'source_ids') ?| %s::text[],false)) UNION ALL SELECT 'confirmation',id,NULL,record_id,reviewed_revision,expires_at FROM public.work_confirmation_requests WHERE workspace_id=%s AND state='pending' AND record_id=ANY(%s::uuid[]) UNION ALL SELECT 'review',id,NULL,record_id,revision,expires_at FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NOT NULL AND record_id=ANY(%s::uuid[])) linked ORDER BY kind,id LIMIT 101",
        (workspace, note_ids, sources, workspace, note_ids, workspace, note_ids),
    ).fetchall()
    if len(rows) > 100:
        raise ValueError("Too many pending/cache effects; no partial source withdrawal")
    return [
        {
            "kind": row[0],
            "id": str(row[1]),
            "intent": row[2],
            "record_id": str(row[3]) if row[3] else None,
            "revision": row[4],
            "expires_at": row[5].isoformat(),
        }
        for row in rows
    ]


def _plan(db, request):
    target = _begin(db, request)
    sources = db.execute(
        "SELECT id,is_active FROM work.source_registry WHERE workspace_id=%s AND id=ANY(%s) ORDER BY id",
        (request.workspace_id, list(request.source_ids)),
    ).fetchall()
    if tuple(row[0] for row in sources) != request.source_ids:
        raise ValueError("Selected source unavailable in this workspace")
    references = [str(value) for value in request.source_ids]
    notes = _notes(db, request.workspace_id, references)
    linked = _linked(db, request.workspace_id, references, [UUID(item["id"]) for item in notes])
    issued = work_lifecycle.clock(request.issued_at) if request.issued_at else work_drafts._now(db)
    _fresh(db, issued)
    body = {
        "schema_version": 1,
        "mode": "synthetic_source_withdrawal_plan",
        "database": target[0],
        "database_oid": target[1],
        "workspace_id": str(request.workspace_id),
        "operator_id": str(request.operator_id),
        "issued_at": issued.isoformat(),
        "sources": [{"id": str(row[0]), "is_active": row[1]} for row in sources],
        "notes": notes,
        "linked": linked,
        "workspace_enabled": False,
        "work_grants": 0,
        "activation_authorized": False,
        "recovery_complete": False,
        "unverified": [
            "original_files_and_immutable_validation_markers",
            "other_derived_stores_and_unmanaged_exports",
            "independent_latest_note_and_source_withdrawal_checkpoints",
            "other_workspaces_and_full_host_key_recovery",
        ],
    }
    result = {
        **body,
        "reviewed_hash": hashlib.sha256(
            b"butler.synthetic.source-withdrawal.v1\n" + canonical(body)
        ).hexdigest(),
    }
    if len(canonical(result)) > 32768:
        raise ValueError("Metadata plan exceeds byte limit")
    return result


def reconcile(db, request: Request):
    """Caller commits redaction, withdrawal and metadata receipt together."""
    plan = _plan(db, request)
    if request.decision == "preview":
        return plan
    if not hmac.compare_digest(request.reviewed_hash, plan["reviewed_hash"]):
        raise ValueError("Plan changed or already applied; preview again")
    if not (any(item["is_active"] for item in plan["sources"]) or plan["notes"] or plan["linked"]):
        raise ValueError("No source withdrawal effects; no completion receipt")
    for item in plan["linked"]:
        reference = {"id": UUID(item["id"]), "workspace_id": request.workspace_id}
        if item["kind"] == "capture":
            finish = (
                work_capture_worker._finish
                if item["intent"] == "capture_draft"
                else work_notes_worker._finish
            )
            finish(db, reference, reason="stale")
        elif item["kind"] == "confirmation":
            work_confirmation_worker._finish(db, reference, reason="stale")
        elif (
            db.execute(
                "UPDATE work.draft_reviews SET payload_hash=NULL WHERE workspace_id=%s AND id=%s AND payload_hash IS NOT NULL",
                (request.workspace_id, reference["id"]),
            ).rowcount
            != 1
        ):
            raise ValueError("Review cleanup changed; roll back")
    for note in plan["notes"]:
        work_drafts.transition(
            db,
            request.workspace_id,
            request.operator_id,
            UUID(note["id"]),
            note["revision"],
            "forget",
            restore=True,
        )
    references = [str(value) for value in request.source_ids]
    if _notes(db, request.workspace_id, references) or _linked(
        db, request.workspace_id, references, [UUID(item["id"]) for item in plan["notes"]]
    ):
        raise ValueError("Derived-copy redaction invariant failed; roll back")
    if db.execute(
        "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s AND id=ANY(%s)",
        (request.workspace_id, list(request.source_ids)),
    ).rowcount != len(request.source_ids):
        raise ValueError("Source selection changed; roll back")
    receipt = uuid4()
    result = {
        "schema_version": 1,
        "mode": "synthetic_sources_withdrawn",
        "receipt_id": str(receipt),
        "database": plan["database"],
        "database_oid": plan["database_oid"],
        "workspace_id": plan["workspace_id"],
        "operator_id": plan["operator_id"],
        "issued_at": plan["issued_at"],
        "plan_hash": plan["reviewed_hash"],
        "sources": plan["sources"],
        "forgotten_notes": plan["notes"],
        "discarded_effects": [{"kind": item["kind"], "id": item["id"]} for item in plan["linked"]],
        "workspace_enabled": False,
        "work_grants": 0,
        "activation_authorized": False,
        "recovery_complete": False,
        "unverified": plan["unverified"],
    }
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(%s,clock_timestamp(),%s,'local_admin','trusted_host_operator','synthetic_source_withdrawal','technical_admin','admin.work_sources_withdrawn','work_access_registry',%s,'success','{}',%s)",
        (receipt, settings.env, str(request.workspace_id), Jsonb(result)),
    )
    _fresh(db, datetime.fromisoformat(plan["issued_at"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--database", required=True)
    parser.add_argument("--operator", required=True, type=UUID)
    parser.add_argument("--workspace", required=True, type=UUID)
    parser.add_argument("--source", required=True, type=UUID, action="append")
    parser.add_argument("--issued-at", type=datetime.fromisoformat)
    parser.add_argument("--reviewed-hash")
    parser.add_argument("--decision", choices=["preview", "withdraw_sources"], default="preview")
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        request = Request(
            database=args.database,
            operator_id=args.operator,
            workspace_id=args.workspace,
            source_ids=tuple(args.source),
            issued_at=args.issued_at,
            reviewed_hash=args.reviewed_hash,
            decision=args.decision,
        )
        with (
            psycopg.connect(
                settings.database_url.replace("postgresql+psycopg", "postgresql", 1),
                connect_timeout=3,
            ) as db,
            db.transaction(),
        ):
            result = reconcile(db, request)
    except (psycopg.Error, ValueError):
        parser.exit(
            1,
            "Synthetic source withdrawal failed; inspect metadata/receipt, stop consumers and preview before retry\n",
        )
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
