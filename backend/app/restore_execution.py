"""Reviewed selected no-op execution quarantine on isolated restored databases."""

import argparse
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from app import approvals, identity, work_drafts, work_lifecycle
from app.config import settings
from app.work_credentials import validate_target
from app.work_suppression_file import canonical


class Request(work_lifecycle.Contract):
    restored_database: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9_]+$")
    operator_id: UUID
    scope_key: str
    approval_ids: tuple[UUID, ...] = Field(default=(), max_length=25)
    job_ids: tuple[UUID, ...] = Field(default=(), max_length=25)
    issued_at: datetime | None = None
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    decision: Literal["preview", "quarantine_restored_execution"] = "preview"

    @model_validator(mode="after")
    def valid(self):
        if self.scope_key not in identity.SCOPES:
            raise ValueError("Known scope required")
        if not 1 <= len(self.approval_ids) + len(self.job_ids) <= 25:
            raise ValueError("Select 1–25 combined approval/job IDs")
        for selected in (self.approval_ids, self.job_ids):
            if tuple(sorted(set(selected))) != selected:
                raise ValueError("Unique sorted IDs required")
        if self.issued_at is not None:
            work_lifecycle.clock(self.issued_at)
        if self.decision == "quarantine_restored_execution":
            if self.issued_at is None or self.reviewed_hash is None:
                raise ValueError("Exact issued plan and decision required")
        elif self.reviewed_hash is not None:
            raise ValueError("Preview cannot carry apply authority")
        return self


def _fresh(db, issued):
    now = work_drafts._now(db)
    if not now - timedelta(minutes=5) <= issued <= now:
        raise ValueError("Use a current server-issued review")


def _iso(value):
    return value.isoformat() if value is not None else None


def _plan(db, request):
    validate_target(settings.env)
    if (
        not isinstance(request, Request)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Explicit typed local transaction required")
    profile = db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),bool_and(current_user=pg_get_userbyid(relowner)),count(*) FROM pg_class WHERE oid IN ('public.approvals'::regclass,'public.durable_jobs'::regclass,'public.job_outbox'::regclass,'public.users'::regclass,'public.audit_events'::regclass) GROUP BY 1,2"
    ).fetchone()
    if profile != (True, "read committed", True, 5):
        raise ValueError("Clean local approval/job/audit owner required")
    target = db.execute(
        "SELECT datname,oid FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if request.restored_database != target[0] or target[0] != settings.postgres_db:
        raise ValueError("Explicit restored database must match actual configured target")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    # EXCLUSIVE conflicts with row-locking/INSERT/UPDATE worker and API transactions.
    # NOWAIT prevents a lock-order cycle with existing consumers: stop/drain and retry.
    db.execute(
        "LOCK TABLE public.approvals,public.durable_jobs,public.job_outbox IN EXCLUSIVE MODE NOWAIT"
    )
    if not db.execute(
        "SELECT 1 FROM public.users u JOIN public.user_scopes us ON us.user_id=u.id JOIN public.scopes s ON s.id=us.scope_id WHERE u.id=%s AND u.is_active AND s.key='technical_admin' FOR SHARE OF u,us,s NOWAIT",
        (request.operator_id,),
    ).fetchone():
        raise ValueError("Active technical-admin audit reference required")
    rows = db.execute(
        "SELECT id,scope_key,action_type,status,requested_by,approved_by,resolved_at,expires_at,consumed_at,policy_version,payload_hash IS NOT NULL FROM public.approvals WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
        (list(request.approval_ids),),
    ).fetchall()
    if len(rows) != len(request.approval_ids):
        raise ValueError("Complete selected approval set required")
    items = []
    for row in rows:
        if row[1] != request.scope_key or row[2] != approvals.ACTION:
            raise ValueError("Matching no-op scope required")
        live = row[3] in {"pending", "approved"}
        if row[3] not in {
            "pending",
            "approved",
            "consumed",
            "rejected",
            "cancelled",
            "expired",
        } or (live and (row[9] != approvals.POLICY or row[7] is None or not row[10])):
            raise ValueError("Bound known approval state required")
        items.append(
            {
                "kind": "approval",
                "id": str(row[0]),
                "state": row[3],
                "requested_by": row[4],
                "approved_by": str(row[5]) if row[5] else None,
                "resolved_at": _iso(row[6]),
                "expires_at": _iso(row[7]),
                "consumed_at": _iso(row[8]),
                "changes_required": live,
            }
        )
    rows = db.execute(
        "SELECT j.id,j.scope_key,j.action_type,j.status,j.approval_id,j.requested_by,a.scope_key,a.action_type,a.status,a.requested_by,j.payload_hash=a.payload_hash,o.id,o.state,o.attempts,o.available_at,o.lease_until,o.lease_hash IS NOT NULL,j.result_code,j.finished_at,j.reviewed_at FROM public.durable_jobs j JOIN public.approvals a ON a.id=j.approval_id LEFT JOIN public.job_outbox o ON o.job_id=j.id WHERE j.id=ANY(%s) ORDER BY j.id FOR UPDATE OF j,a",
        (list(request.job_ids),),
    ).fetchall()
    if len(rows) != len(request.job_ids):
        raise ValueError("Complete selected job set required")
    for row in rows:
        if (
            row[1] != request.scope_key
            or row[2] != approvals.ACTION
            or row[6:8] != (request.scope_key, approvals.ACTION)
        ):
            raise ValueError("Matching no-op scope required")
        if row[8] != "consumed" or str(row[5]) != row[9] or not row[10] or row[11] is None:
            raise ValueError("Intact job/approval/outbox linkage required")
        paired = {
            "queued": "pending",
            "running": "leased",
            "succeeded": "done",
            "dead_letter": "dead_letter",
        }
        if paired.get(row[3]) != row[12] or (
            (row[12] == "leased") != (row[15] is not None and row[16])
        ):
            raise ValueError("Consistent paired job/outbox required")
        items.append(
            {
                "kind": "job",
                "id": str(row[0]),
                "state": row[3],
                "approval_id": str(row[4]),
                "outbox_id": str(row[11]),
                "outbox_state": row[12],
                "attempts": row[13],
                "available_at": _iso(row[14]),
                "lease_until": _iso(row[15]),
                "lease_present": row[16],
                "result_code": row[17],
                "finished_at": _iso(row[18]),
                "reviewed_at": _iso(row[19]),
                "changes_required": row[3] in {"queued", "running"},
            }
        )
    issued = work_lifecycle.clock(request.issued_at) if request.issued_at else work_drafts._now(db)
    _fresh(db, issued)
    body = {
        "schema_version": 1,
        "mode": "restored_noop_execution_plan",
        "database": target[0],
        "database_oid": target[1],
        "operator_id": str(request.operator_id),
        "scope": request.scope_key,
        "issued_at": issued.isoformat(),
        "items": items,
        "dispatch_activated": False,
        "recovery_complete": False,
    }
    result = {
        **body,
        "reviewed_hash": hashlib.sha256(
            b"butler.restored-noop-execution.v1\n" + canonical(body)
        ).hexdigest(),
    }
    if len(canonical(result)) > 32768:
        raise ValueError("Metadata plan exceeds byte limit")
    return result


def _audit(db, request, event, entity_type, entity_id, metadata, identifier=None):
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(%s,clock_timestamp(),%s,'local_admin','trusted_host_operator','restored_noop_execution',%s,%s,%s,%s,'success','{}',%s)",
        (
            identifier or uuid4(),
            settings.env,
            request.scope_key,
            event,
            entity_type,
            entity_id,
            Jsonb(metadata),
        ),
    )


def reconcile(db, request: Request):
    """Caller commits; never execute, retry, unconsume or recreate authority."""
    plan = _plan(db, request)
    if request.decision == "preview":
        return plan
    if not hmac.compare_digest(request.reviewed_hash, plan["reviewed_hash"]):
        raise ValueError("Plan changed or already applied; preview again")
    if not any(item["changes_required"] for item in plan["items"]):
        raise ValueError("No outstanding authority; no completion receipt")
    receipt = uuid4()
    outcomes = []
    for item in plan["items"]:
        outcome = "preserved"
        if item["changes_required"]:
            if item["kind"] == "approval":
                db.execute(
                    "UPDATE public.approvals SET status='cancelled',resolved_at=COALESCE(resolved_at,clock_timestamp()) WHERE id=%s",
                    (UUID(item["id"]),),
                )
                outcome = "cancelled"
            else:
                db.execute(
                    "UPDATE public.job_outbox SET state='dead_letter',lease_hash=NULL,lease_until=NULL WHERE id=%s",
                    (UUID(item["outbox_id"]),),
                )
                db.execute(
                    "UPDATE public.durable_jobs SET status='dead_letter',result_code='restore_quarantined',finished_at=clock_timestamp() WHERE id=%s",
                    (UUID(item["id"]),),
                )
                outcome = "dead_letter"
            _audit(
                db,
                request,
                "admin.restored_" + item["kind"] + "_quarantined",
                item["kind"],
                item["id"],
                {"receipt_id": str(receipt), "previous_state": item["state"], "outcome": outcome},
            )
        outcomes.append(
            {
                "kind": item["kind"],
                "id": item["id"],
                "previous_state": item["state"],
                "outcome": outcome,
            }
        )
    result = {
        "schema_version": 1,
        "mode": "restored_noop_execution_quarantined",
        "database": plan["database"],
        "database_oid": plan["database_oid"],
        "scope": request.scope_key,
        "operator_id": str(request.operator_id),
        "receipt_id": str(receipt),
        "plan_hash": plan["reviewed_hash"],
        "issued_at": plan["issued_at"],
        "outcomes": outcomes,
        "dispatch_activated": False,
        "recovery_complete": False,
    }
    _audit(
        db,
        request,
        "admin.restored_execution_quarantined",
        "execution_recovery",
        str(receipt),
        result,
        receipt,
    )
    _fresh(db, datetime.fromisoformat(plan["issued_at"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--restored-database", required=True)
    parser.add_argument("--operator", required=True, type=UUID)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--approval", action="append", default=[], type=UUID)
    parser.add_argument("--job", action="append", default=[], type=UUID)
    parser.add_argument("--issued-at", type=datetime.fromisoformat)
    parser.add_argument("--reviewed-hash")
    parser.add_argument(
        "--decision", choices=["preview", "quarantine_restored_execution"], default="preview"
    )
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        request = Request(
            restored_database=args.restored_database,
            operator_id=args.operator,
            scope_key=args.scope,
            approval_ids=tuple(sorted(args.approval)),
            job_ids=tuple(sorted(args.job)),
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
            "Restored execution quarantine failed; inspect metadata/receipt, stop consumers and preview before retry\n",
        )
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
