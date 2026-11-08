"""Reviewed platform-session revocation in bounded restored-database batches."""

import argparse
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from app import work_drafts, work_lifecycle
from app.config import settings
from app.work_credentials import validate_target
from app.work_suppression_file import canonical


class Request(work_lifecycle.Contract):
    restored_database: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9_]+$")
    operator_id: UUID
    limit: int = Field(default=100, strict=True, ge=1, le=100)
    issued_at: datetime | None = None
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    decision: Literal["preview", "revoke_restored_sessions"] = "preview"

    @model_validator(mode="after")
    def valid(self):
        if self.issued_at is not None:
            work_lifecycle.clock(self.issued_at)
        if self.decision == "revoke_restored_sessions":
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
        "SELECT session_user=current_user,current_setting('transaction_isolation'),bool_and(current_user=pg_get_userbyid(relowner)),count(*) FROM pg_class WHERE oid IN ('public.auth_sessions'::regclass,'public.users'::regclass,'public.audit_events'::regclass) GROUP BY 1,2"
    ).fetchone()
    if profile != (True, "read committed", True, 3):
        raise ValueError("Clean local session/user/audit owner required")
    target = db.execute(
        "SELECT datname,oid FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if request.restored_database != target[0] or target[0] != settings.postgres_db:
        raise ValueError("Explicit restored database must match actual configured target")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    # Resolve uses FOR UPDATE; login/logout mutate this table. No new API lock path.
    db.execute("LOCK TABLE public.auth_sessions IN EXCLUSIVE MODE NOWAIT")
    if not db.execute(
        "SELECT 1 FROM public.users u JOIN public.user_scopes us ON us.user_id=u.id JOIN public.scopes s ON s.id=us.scope_id WHERE u.id=%s AND u.is_active AND s.key='technical_admin' FOR SHARE OF u,us,s NOWAIT",
        (request.operator_id,),
    ).fetchone():
        raise ValueError("Active technical-admin audit reference required")
    rows = db.execute(
        "SELECT id,user_id,created_at,last_seen_at,expires_at FROM public.auth_sessions WHERE revoked_at IS NULL ORDER BY id LIMIT %s FOR UPDATE",
        (request.limit + 1,),
    ).fetchall()
    issued = work_lifecycle.clock(request.issued_at) if request.issued_at else work_drafts._now(db)
    _fresh(db, issued)
    body = {
        "schema_version": 1,
        "mode": "restored_session_quarantine_plan",
        "database": target[0],
        "database_oid": target[1],
        "operator_id": str(request.operator_id),
        "issued_at": issued.isoformat(),
        "limit": request.limit,
        "items": [
            {
                "id": str(row[0]),
                "user_id": str(row[1]),
                "created_at": row[2].isoformat(),
                "last_seen_at": row[3].isoformat(),
                "expires_at": row[4].isoformat(),
            }
            for row in rows[: request.limit]
        ],
        "has_more": len(rows) > request.limit,
        "api_activated": False,
        "recovery_complete": False,
    }
    result = {
        **body,
        "reviewed_hash": hashlib.sha256(
            b"butler.restored-session-quarantine.v1\n" + canonical(body)
        ).hexdigest(),
    }
    if len(canonical(result)) > 32768:
        raise ValueError("Metadata plan exceeds byte limit")
    return result


def reconcile(db, request: Request):
    """Caller commits batch revocation/audit together; never change credentials."""
    plan = _plan(db, request)
    if request.decision == "preview":
        return plan
    if not hmac.compare_digest(request.reviewed_hash, plan["reviewed_hash"]):
        raise ValueError("Plan changed or already applied; preview again")
    if not plan["items"]:
        raise ValueError("No unrevoked sessions; no completion receipt")
    changed = db.execute(
        "UPDATE public.auth_sessions SET revoked_at=clock_timestamp() WHERE id=ANY(%s) AND revoked_at IS NULL",
        ([UUID(item["id"]) for item in plan["items"]],),
    ).rowcount
    if changed != len(plan["items"]):
        raise ValueError("Session batch changed during write; roll back")
    remaining = db.execute(
        "SELECT EXISTS(SELECT 1 FROM public.auth_sessions WHERE revoked_at IS NULL)"
    ).fetchone()[0]
    receipt = uuid4()
    result = {
        "schema_version": 1,
        "mode": "restored_sessions_revoked",
        "database": plan["database"],
        "database_oid": plan["database_oid"],
        "operator_id": str(request.operator_id),
        "receipt_id": str(receipt),
        "plan_hash": plan["reviewed_hash"],
        "issued_at": plan["issued_at"],
        "limit": request.limit,
        "revoked_sessions": [
            {"id": item["id"], "user_id": item["user_id"]} for item in plan["items"]
        ],
        "remaining_unrevoked": remaining,
        "session_set_clear_at_commit": not remaining,
        "api_activated": False,
        "recovery_complete": False,
    }
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(%s,clock_timestamp(),%s,'local_admin','trusted_host_operator','restored_session_quarantine','technical_admin','admin.restored_sessions_revoked','session_recovery',%s,'success','{}',%s)",
        (receipt, settings.env, str(receipt), Jsonb(result)),
    )
    _fresh(db, datetime.fromisoformat(plan["issued_at"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--restored-database", required=True)
    parser.add_argument("--operator", required=True, type=UUID)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--issued-at", type=datetime.fromisoformat)
    parser.add_argument("--reviewed-hash")
    parser.add_argument(
        "--decision", choices=["preview", "revoke_restored_sessions"], default="preview"
    )
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        request = Request(
            restored_database=args.restored_database,
            operator_id=args.operator,
            limit=args.limit,
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
            "Restored session quarantine failed; inspect metadata/receipt, stop consumers and preview before retry\n",
        )
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
