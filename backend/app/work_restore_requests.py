"""Reviewed discard of pending synthetic Work input after restore quarantine."""

import argparse
import hashlib
import hmac
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
    workspace_id: UUID
    operator_id: UUID
    restored_database: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9_]+$")
    issued_at: datetime | None = None
    decision: Literal["preview", "discard_restored_requests"] = "preview"
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def valid(self):
        if self.issued_at is not None:
            work_lifecycle.clock(self.issued_at)
        if self.decision == "discard_restored_requests":
            if self.issued_at is None or self.reviewed_hash is None:
                raise ValueError("Exact issued plan and explicit decision required")
        elif self.reviewed_hash is not None:
            raise ValueError("Preview cannot carry apply authority")
        return self


def _fresh(db, issued):
    now = work_drafts._now(db)
    if not now - timedelta(minutes=5) <= issued <= now:
        raise ValueError("Use a current server-issued review")


def _plan(db, request):
    validate_target(settings.env)
    if (
        not isinstance(request, Request)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Explicit typed local transaction required")
    profile = db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),bool_and(current_user=pg_get_userbyid(relowner)),count(*) FROM pg_class WHERE oid IN ('public.work_workspaces'::regclass,'public.work_access_grants'::regclass,'public.users'::regclass,'public.audit_events'::regclass,'work.capture_intents'::regclass,'work.draft_reviews'::regclass,'public.work_confirmation_requests'::regclass) GROUP BY 1,2"
    ).fetchone()
    if profile != (True, "read committed", True, 7):
        raise ValueError("Clean local registry/request/review/audit owner required")
    target = db.execute(
        "SELECT datname,oid FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if request.restored_database != target[0] or target[0] != settings.postgres_db:
        raise ValueError("Explicit restored database must match actual configured target")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    db.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
    if not db.execute(
        "SELECT 1 FROM public.work_workspaces WHERE id=%s AND NOT is_active AND slug LIKE 'synthetic-%%' FOR UPDATE",
        (request.workspace_id,),
    ).fetchone():
        raise ValueError("Disabled synthetic workspace required")
    if db.execute(
        "SELECT 1 FROM public.work_access_grants WHERE workspace_id=%s LIMIT 1",
        (request.workspace_id,),
    ).fetchone():
        raise ValueError("Quarantined no-grant workspace required")
    if not db.execute(
        "SELECT 1 FROM public.users u JOIN public.user_scopes us ON us.user_id=u.id JOIN public.scopes s ON s.id=us.scope_id WHERE u.id=%s AND u.is_active AND s.key='technical_admin' FOR SHARE OF u,us,s",
        (request.operator_id,),
    ).fetchone():
        raise ValueError("Active technical-admin audit reference required")
    if not db.execute(
        "SELECT to_regprocedure('work.restore_requests_allowed(uuid)') IS NOT NULL"
    ).fetchone()[0]:
        raise ValueError("Restore request cleanup migration required")
    items = []
    captures = db.execute(
        "SELECT id,intent,target_record_id,expected_revision,expires_at FROM work.capture_intents WHERE workspace_id=%s AND state='pending' ORDER BY id LIMIT 101 FOR UPDATE",
        (request.workspace_id,),
    ).fetchall()
    for row in captures:
        items.append(
            {
                "kind": "capture",
                "id": str(row[0]),
                "intent": row[1],
                "record_id": str(row[2]) if row[2] else None,
                "revision": row[3],
                "expires_at": row[4].isoformat(),
            }
        )
    for kind, query in (
        (
            "confirmation",
            "SELECT id,record_id,reviewed_revision,expires_at FROM public.work_confirmation_requests WHERE workspace_id=%s AND state='pending' ORDER BY id LIMIT 101 FOR UPDATE",
        ),
        (
            "review",
            "SELECT id,record_id,revision,expires_at FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NOT NULL ORDER BY id LIMIT 101 FOR UPDATE",
        ),
    ):
        for row in db.execute(query, (request.workspace_id,)).fetchall():
            items.append(
                {
                    "kind": kind,
                    "id": str(row[0]),
                    "record_id": str(row[1]),
                    "revision": row[2],
                    "expires_at": row[3].isoformat(),
                }
            )
    if len(items) > 100:
        raise ValueError("Too many pending effects; no partial cleanup")
    issued = work_lifecycle.clock(request.issued_at) if request.issued_at else work_drafts._now(db)
    _fresh(db, issued)
    body = {
        "schema_version": 1,
        "mode": "synthetic_work_restore_requests_plan",
        "database": target[0],
        "database_oid": target[1],
        "workspace_id": str(request.workspace_id),
        "operator_id": str(request.operator_id),
        "issued_at": issued.isoformat(),
        "items": items,
        "workspace_enabled": False,
        "work_grants": 0,
        "recovery_complete": False,
    }
    result = {
        **body,
        "reviewed_hash": hashlib.sha256(
            b"butler.synthetic.work-restore-requests.v1\n" + canonical(body)
        ).hexdigest(),
    }
    if len(canonical(result)) > 32768:
        raise ValueError("Metadata plan exceeds byte limit")
    return result


def reconcile(db, request: Request):
    """Caller commits all denial/redaction/audit together; no note lifecycle write."""
    plan = _plan(db, request)
    if request.decision == "preview":
        return plan
    if not hmac.compare_digest(request.reviewed_hash, plan["reviewed_hash"]):
        raise ValueError("Plan changed or already applied; preview again")
    if not plan["items"]:
        raise ValueError("No pending effects; no completion receipt")
    db.execute("SET LOCAL butler.restore_requests='reviewed'")
    for item in plan["items"]:
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
            raise ValueError("Review cleanup changed during write; roll back")
    receipt = uuid4()
    result = {
        "schema_version": 1,
        "mode": "synthetic_work_restore_requests_discarded",
        "workspace_id": str(request.workspace_id),
        "operator_id": str(request.operator_id),
        "receipt_id": str(receipt),
        "plan_hash": plan["reviewed_hash"],
        "issued_at": plan["issued_at"],
        "outcomes": [
            {
                "kind": item["kind"],
                "id": item["id"],
                "outcome": "hash_redacted" if item["kind"] == "review" else "denied_stale",
            }
            for item in plan["items"]
        ],
        "workspace_enabled": False,
        "work_grants": 0,
        "recovery_complete": False,
    }
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(%s,clock_timestamp(),%s,'local_admin','trusted_host_operator','synthetic_work_restore_requests','technical_admin','admin.work_restore_requests_discarded','work_access_registry',%s,'success','{}',%s)",
        (receipt, settings.env, str(request.workspace_id), Jsonb(result)),
    )
    _fresh(db, datetime.fromisoformat(plan["issued_at"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--restored-database", required=True)
    parser.add_argument("--workspace", required=True, type=UUID)
    parser.add_argument("--operator", required=True, type=UUID)
    parser.add_argument("--issued-at", type=datetime.fromisoformat)
    parser.add_argument("--reviewed-hash")
    parser.add_argument(
        "--decision", choices=["preview", "discard_restored_requests"], default="preview"
    )
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        request = Request(
            workspace_id=args.workspace,
            operator_id=args.operator,
            restored_database=args.restored_database,
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
            "Synthetic restored-request cleanup failed; rolled back, inspect metadata and preview before retry\n",
        )
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
