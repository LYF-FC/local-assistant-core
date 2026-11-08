"""Manual reviewed synthetic restored-workspace quarantine; no reactivation certificate."""

import argparse
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from app import work_drafts, work_lifecycle
from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import validate_target


class Request(work_lifecycle.Contract):
    workspace_id: UUID
    operator_id: UUID
    restored_database: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9_]+$")
    issued_at: datetime | None = None
    decision: Literal["preview", "quarantine_restored_workspace"] = "preview"
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def review(self):
        if self.issued_at is not None:
            work_lifecycle.clock(self.issued_at)
        if self.decision == "quarantine_restored_workspace":
            if self.issued_at is None or self.reviewed_hash is None:
                raise ValueError("Exact issued plan and explicit decision required")
        elif self.reviewed_hash is not None:
            raise ValueError("Preview cannot carry apply authority")
        return self


def _fresh(db, issued):
    if not work_drafts._now(db) - timedelta(minutes=5) <= issued <= work_drafts._now(db):
        raise ValueError("Use a current server-issued review")


def _plan(db, request):
    validate_target(settings.env)
    if (
        not isinstance(request, Request)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Explicit typed local transaction required")
    profile = db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),bool_and(current_user=pg_get_userbyid(relowner)),count(*) FROM pg_class WHERE oid IN ('public.work_workspaces'::regclass,'public.work_access_grants'::regclass,'public.users'::regclass,'public.auth_sessions'::regclass,'public.audit_events'::regclass) GROUP BY 1,2"
    ).fetchone()
    if profile != (True, "read committed", True, 5):
        raise ValueError("Clean local registry/session/audit owner required")
    target = db.execute(
        "SELECT datname,oid FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if request.restored_database != target[0] or target[0] != settings.postgres_db:
        raise ValueError("Explicit restored database must match actual configured target")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    db.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
    workspace = db.execute(
        "SELECT is_active FROM public.work_workspaces WHERE id=%s AND slug LIKE 'synthetic-%%' FOR UPDATE",
        (request.workspace_id,),
    ).fetchone()
    if workspace is None:
        raise ValueError("Synthetic workspace required")
    users = db.execute(
        "SELECT user_id FROM public.work_access_grants WHERE workspace_id=%s ORDER BY user_id LIMIT 26 FOR UPDATE",
        (request.workspace_id,),
    ).fetchall()
    if len(users) > 25:
        raise ValueError("Too many grantees; no partial quarantine")
    grantees = [row[0] for row in users]
    db.execute(
        "SELECT id FROM public.users WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
        (sorted(set(grantees + [request.operator_id])),),
    ).fetchall()
    if not db.execute(
        "SELECT 1 FROM public.users u JOIN public.user_scopes us ON us.user_id=u.id JOIN public.scopes s ON s.id=us.scope_id WHERE u.id=%s AND u.is_active AND s.key='technical_admin' FOR SHARE OF us,s",
        (request.operator_id,),
    ).fetchone():
        raise ValueError("Explicit active technical-admin operator required")
    sessions = db.execute(
        "SELECT id,user_id,expires_at,last_seen_at FROM public.auth_sessions WHERE user_id=ANY(%s) AND revoked_at IS NULL ORDER BY id LIMIT 101 FOR UPDATE",
        (grantees,),
    ).fetchall()
    if len(sessions) > 100:
        raise ValueError("Too many sessions; no partial quarantine")
    issued = work_lifecycle.clock(request.issued_at) if request.issued_at else work_drafts._now(db)
    _fresh(db, issued)
    plan = {
        "schema_version": 1,
        "mode": "synthetic_work_restore_quarantine_plan",
        "database": target[0],
        "database_oid": target[1],
        "workspace_id": str(request.workspace_id),
        "operator_id": str(request.operator_id),
        "issued_at": issued.isoformat(),
        "workspace_enabled": workspace[0],
        "grantees": [str(user) for user in grantees],
        "sessions": [
            {
                "id": str(row[0]),
                "user_id": str(row[1]),
                "expires_at": row[2].isoformat(),
                "last_seen_at": row[3].isoformat(),
            }
            for row in sessions
        ],
        "cross_scope_sign_out": True,
    }
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    result = {
        **plan,
        "reviewed_hash": hashlib.sha256(
            b"butler.synthetic.work-quarantine.v1\n" + encoded
        ).hexdigest(),
    }
    if len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()) > 32768:
        raise ValueError("Metadata plan exceeds byte limit")
    return result


def reconcile(db, request: Request):
    """Prepared until caller commits; no private Work content is read or changed."""
    plan = _plan(db, request)
    if request.decision == "preview":
        return plan
    if not hmac.compare_digest(request.reviewed_hash, plan["reviewed_hash"]):
        raise ValueError("Plan changed or already applied; preview again")
    if not plan["workspace_enabled"] and not plan["grantees"]:
        raise ValueError("Workspace already quarantined")
    db.execute(
        "UPDATE public.work_workspaces SET is_active=false WHERE id=%s", (request.workspace_id,)
    )
    deleted = db.execute(
        "DELETE FROM public.work_access_grants WHERE workspace_id=%s RETURNING user_id",
        (request.workspace_id,),
    ).fetchall()
    revoked = db.execute(
        "UPDATE public.auth_sessions SET revoked_at=clock_timestamp() WHERE id=ANY(%s) AND revoked_at IS NULL RETURNING id",
        ([UUID(row["id"]) for row in plan["sessions"]],),
    ).fetchall()
    if len(deleted) != len(plan["grantees"]) or len(revoked) != len(plan["sessions"]):
        raise ValueError("Quarantine changed during write; roll back")
    receipt = uuid4()
    result = {
        "schema_version": 1,
        "mode": "synthetic_work_restore_quarantined",
        "workspace_id": str(request.workspace_id),
        "operator_id": str(request.operator_id),
        "receipt_id": str(receipt),
        "plan_hash": plan["reviewed_hash"],
        "issued_at": plan["issued_at"],
        "previous_workspace_enabled": plan["workspace_enabled"],
        "workspace_enabled": False,
        "removed_grantees": plan["grantees"],
        "revoked_sessions": [row["id"] for row in plan["sessions"]],
        "cross_scope_sign_out": True,
        "recovery_complete": False,
    }
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(%s,clock_timestamp(),%s,'local_admin','trusted_host_operator','synthetic_work_restore','technical_admin','admin.work_restore_quarantined','work_access_registry',%s,'success','{}',%s)",
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
        "--decision", choices=["preview", "quarantine_restored_workspace"], default="preview"
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
            "Synthetic restore quarantine failed; rolled back, inspect metadata and preview before retry\n",
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
