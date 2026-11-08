"""Manual bounded expiry reconciliation; no API, scheduler or restore certificate."""

import argparse
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from app import (
    work_capture_worker,
    work_confirmation_worker,
    work_drafts,
    work_lifecycle,
    work_notes_worker,
    work_parties,
)
from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import validate_target

MAX_LINKED = 100


class Request(work_lifecycle.Contract):
    workspace_id: UUID
    operator_id: UUID
    limit: int = Field(strict=True, ge=1, le=25, default=25)
    cutoff: datetime | None = None
    decision: Literal["preview", "apply_expired_cleanup"] = "preview"
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def review(self):
        if self.cutoff is not None:
            work_lifecycle.clock(self.cutoff)
        if self.decision == "apply_expired_cleanup":
            if self.cutoff is None or self.reviewed_hash is None:
                raise ValueError("Explicit cutoff and reviewed plan required")
        elif self.reviewed_hash is not None:
            raise ValueError("Preview cannot carry an apply decision")
        return self


def _rows(db, query, values):
    with db.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, values).fetchall()


def _begin(db, request):
    validate_target(settings.env)
    if (
        not isinstance(request, Request)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Explicit typed maintenance transaction required")
    profile = db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),bool_and(current_user=pg_get_userbyid(relowner)),count(*) FROM pg_class WHERE oid IN ('work.drafts'::regclass,'work.parties'::regclass,'work.capture_intents'::regclass,'work.draft_reviews'::regclass,'public.work_confirmation_requests'::regclass,'public.audit_events'::regclass) GROUP BY 1,2"
    ).fetchone()
    if profile != (True, "read committed", True, 6):
        raise ValueError("Clean local storage/audit owner required")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    db.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
    if not db.execute(
        "SELECT 1 FROM public.work_workspaces WHERE id=%s AND NOT is_active AND slug LIKE 'synthetic-%%' FOR UPDATE",
        (request.workspace_id,),
    ).fetchone():
        raise ValueError("Disabled synthetic workspace required")
    if not db.execute(
        "SELECT 1 FROM public.users u JOIN public.user_scopes us ON us.user_id=u.id JOIN public.scopes s ON s.id=us.scope_id WHERE u.id=%s AND u.is_active AND s.key='technical_admin' FOR SHARE OF u,us,s",
        (request.operator_id,),
    ).fetchone():
        raise ValueError("Explicit active technical-admin operator identity required")
    if not db.execute(
        "SELECT to_regprocedure('work.review_retention_barrier()') IS NOT NULL"
    ).fetchone()[0]:
        raise ValueError("Retention migration required")
    db.execute("SET LOCAL butler.retention_cleanup='expired'")


def _plan(db, request, cutoff):
    rows = _rows(
        db,
        """
      SELECT * FROM (
        SELECT 'capture' AS kind,id,NULL::integer AS revision,state,expires_at FROM work.capture_intents WHERE workspace_id=%s AND state='pending' AND expires_at<=%s
        UNION ALL SELECT 'confirmation',id,reviewed_revision,state,expires_at FROM public.work_confirmation_requests WHERE workspace_id=%s AND state='pending' AND expires_at<=%s
        UNION ALL SELECT 'note',id,revision,state,retain_until FROM work.drafts WHERE workspace_id=%s AND state<>'forgotten' AND retain_until<=%s
        UNION ALL SELECT 'party',id,revision,state,retain_until FROM work.parties WHERE workspace_id=%s AND state<>'forgotten' AND retain_until<=%s
        UNION ALL SELECT 'review',id,revision,'prepared',expires_at FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NOT NULL AND expires_at<=%s
      ) candidates ORDER BY kind,id LIMIT %s
    """,
        (*((request.workspace_id, cutoff) * 5), request.limit + 1),
    )
    items, linked_count = [], 0
    for row in rows[: request.limit]:
        item = {**row, "id": str(row["id"]), "expires_at": row["expires_at"].isoformat()}
        if row["kind"] == "note":
            linked = _rows(
                db,
                """
              SELECT * FROM (
                SELECT 'correction' AS kind,id,expires_at FROM work.capture_intents WHERE workspace_id=%s AND target_record_id=%s AND intent='correct_note' AND state='pending'
                UNION ALL SELECT 'confirmation',id,expires_at FROM public.work_confirmation_requests WHERE workspace_id=%s AND record_id=%s AND state='pending'
                UNION ALL SELECT 'review',id,expires_at FROM work.draft_reviews WHERE workspace_id=%s AND record_id=%s AND payload_hash IS NOT NULL
              ) linked ORDER BY kind,id LIMIT 101
            """,
                (request.workspace_id, row["id"]) * 3,
            )
            linked_count += len(linked)
            if linked_count > MAX_LINKED:
                raise ValueError("Too many linked requests; reconcile them before another preview")
            item["linked"] = [
                {**value, "id": str(value["id"]), "expires_at": value["expires_at"].isoformat()}
                for value in linked
            ]
        items.append(item)
    plan = {
        "schema_version": 1,
        "mode": "synthetic_work_retention_plan",
        "workspace_id": str(request.workspace_id),
        "operator_id": str(request.operator_id),
        "cutoff": cutoff.isoformat(),
        "limit": request.limit,
        "items": items,
        "has_more": len(rows) > request.limit,
        "linked_count": linked_count,
        "workspace_enabled": False,
    }
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > 32768:
        raise ValueError("Plan exceeds metadata byte limit")
    return {
        **plan,
        "reviewed_hash": hashlib.sha256(
            b"butler.synthetic.retention-plan.v1\n" + encoded
        ).hexdigest(),
    }


def _deny_capture(db, row):
    if row["intent"] == "capture_draft":
        work_capture_worker._finish(db, row, "expired")
    else:
        work_notes_worker._finish(db, row, "expired")


def reconcile(db, request: Request):
    """Caller owns commit; returned metadata is prepared until the transaction commits."""
    _begin(db, request)
    now = work_drafts._now(db)
    cutoff = work_lifecycle.clock(request.cutoff) if request.cutoff is not None else now
    if not now - timedelta(minutes=5) <= cutoff <= now:
        raise ValueError("Use a current server-issued cutoff")
    plan = _plan(db, request, cutoff)
    if request.decision == "preview":
        return plan
    if not hmac.compare_digest(request.reviewed_hash, plan["reviewed_hash"]):
        raise ValueError("Plan changed or was already applied; preview again")
    if not plan["items"]:
        raise ValueError("No expired candidates to apply")
    outcomes = []
    for item in plan["items"]:
        identifier, kind = UUID(item["id"]), item["kind"]
        if kind == "capture":
            row = work_capture_worker._one(
                db,
                "SELECT * FROM work.capture_intents WHERE workspace_id=%s AND id=%s FOR UPDATE",
                (request.workspace_id, identifier),
            )
            if row["state"] == "pending":
                _deny_capture(db, row)
        elif kind == "confirmation":
            row = work_confirmation_worker._one(
                db,
                "SELECT * FROM public.work_confirmation_requests WHERE workspace_id=%s AND id=%s FOR UPDATE",
                (request.workspace_id, identifier),
            )
            if row["state"] == "pending":
                work_confirmation_worker._finish(db, row, reason="expired")
        elif kind == "note":
            work_drafts.transition(
                db,
                request.workspace_id,
                request.operator_id,
                identifier,
                item["revision"],
                "forget",
                maintenance=True,
            )
            for linked in item["linked"]:
                if linked["kind"] == "confirmation":
                    row = work_confirmation_worker._one(
                        db,
                        "SELECT * FROM public.work_confirmation_requests WHERE workspace_id=%s AND id=%s FOR UPDATE",
                        (request.workspace_id, UUID(linked["id"])),
                    )
                    if row["state"] == "pending":
                        work_confirmation_worker._finish(db, row, reason="expired")
        elif kind == "party":
            work_parties.transition(
                db, request.workspace_id, identifier, item["revision"], "forget", maintenance=True
            )
        else:
            row = db.execute(
                "UPDATE work.draft_reviews SET payload_hash=NULL WHERE workspace_id=%s AND id=%s AND payload_hash IS NOT NULL AND expires_at<=%s RETURNING record_id,revision",
                (request.workspace_id, identifier, cutoff),
            ).fetchone()
            if row:
                db.execute(
                    "INSERT INTO work.draft_audit(workspace_id,record_id,revision,actor_id,event_type) VALUES(%s,%s,%s,%s,'draft.review_expired')",
                    (request.workspace_id, row[0], row[1], request.operator_id),
                )
        outcomes.append(
            {
                "kind": kind,
                "id": item["id"],
                "outcome": "redacted" if kind in {"note", "party", "review"} else "denied",
            }
        )
    receipt = str(uuid4())
    result = {
        "schema_version": 1,
        "mode": "synthetic_work_retention_applied",
        "workspace_id": str(request.workspace_id),
        "operator_id": str(request.operator_id),
        "cutoff": cutoff.isoformat(),
        "limit": request.limit,
        "plan_hash": plan["reviewed_hash"],
        "receipt_id": receipt,
        "outcomes": outcomes,
        "has_more": plan["has_more"],
        "workspace_enabled": False,
    }
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(%s,clock_timestamp(),%s,'local_admin','trusted_host_operator','synthetic_retention','technical_admin','admin.work_retention_applied','work_access_registry',%s,'success','{}',%s)",
        (UUID(receipt), settings.env, str(request.workspace_id), Jsonb(result)),
    )
    if work_drafts._now(db) - cutoff > timedelta(minutes=5):
        raise ValueError("Plan expired during cleanup; roll back")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--workspace", required=True, type=UUID)
    parser.add_argument("--operator", required=True, type=UUID)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--cutoff", type=datetime.fromisoformat)
    parser.add_argument("--reviewed-hash")
    parser.add_argument(
        "--decision", choices=["preview", "apply_expired_cleanup"], default="preview"
    )
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        request = Request(
            workspace_id=args.workspace,
            operator_id=args.operator,
            limit=args.limit,
            cutoff=args.cutoff,
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
            "Synthetic retention reconciliation failed; rolled back, preview/reconcile before retry\n",
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
