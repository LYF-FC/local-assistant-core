"""Reviewed current/orphan Work login quarantine on an isolated restored cluster."""

import argparse
import hashlib
import hmac
import re
from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from app import work_drafts, work_lifecycle
from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import check_role, login_name, validate_target
from app.work_storage import role_name
from app.work_suppression_file import canonical


class Request(work_lifecycle.Contract):
    restored_database: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9_]+$")
    operator_id: UUID
    workspace_id: UUID
    namespace_oids: list[Annotated[int, Field(strict=True)]] = Field(
        default_factory=list, max_length=10
    )
    issued_at: datetime | None = None
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    decision: Literal["preview", "revoke_restored_credentials"] = "preview"

    @model_validator(mode="after")
    def valid(self):
        if self.namespace_oids != sorted(set(self.namespace_oids)) or any(
            type(oid) is not int or not 1 <= oid <= 4294967295 for oid in self.namespace_oids
        ):
            raise ValueError("Select sorted unique database OIDs")
        if self.issued_at is not None:
            work_lifecycle.clock(self.issued_at)
        if self.decision != "preview" and (
            not self.namespace_oids or self.issued_at is None or self.reviewed_hash is None
        ):
            raise ValueError("Exact server-issued reviewed plan required")
        if self.decision == "preview" and self.reviewed_hash is not None:
            raise ValueError("Preview cannot carry apply authority")
        return self


def _fresh(db, issued):
    if not work_drafts._now(db) - timedelta(minutes=5) <= issued <= work_drafts._now(db):
        raise ValueError("Use a current server-issued review")


def _begin(db, request):
    validate_target(settings.env)
    if (
        not isinstance(request, Request)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Typed local transaction required")
    if db.execute(
        "SELECT session_user=current_user,rolsuper,current_setting('transaction_isolation') FROM pg_roles WHERE rolname=current_user"
    ).fetchone() != (True, True, "read committed"):
        raise ValueError("Clean superuser READ COMMITTED connection required")
    target = db.execute(
        "SELECT datname,oid FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if target[0] != request.restored_database or target[0] != settings.postgres_db:
        raise ValueError("Actual restored database must match explicit configured target")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    if not db.execute("SELECT pg_try_advisory_xact_lock(%s,%s)", REGISTRY_KEY).fetchone()[0]:
        raise ValueError("Registry busy; stop consumers before retry")
    db.execute(
        "LOCK TABLE public.work_workspaces,public.work_access_grants IN EXCLUSIVE MODE NOWAIT"
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
    return target


def _inventory(db, workspace):
    # Public catalog only: never inspect password verifiers, secrets or payloads.
    rows = db.execute(
        "SELECT oid,rolname,rolcanlogin,rolvaliduntil FROM pg_roles WHERE (starts_with(rolname,'butler_work_') OR starts_with(rolname,'butler_wlogin_')) AND right(rolname::text,33)=%s ORDER BY rolname LIMIT 51",
        ("_" + workspace.hex,),
    ).fetchall()
    namespaces = {}
    for oid, name, can_login, until in rows:
        match = re.fullmatch(r"butler_(work|wlogin)_([1-9][0-9]{0,9})_" + workspace.hex, name)
        if not match or int(match[2]) > 4294967295:
            raise ValueError("Malformed reserved namespace; manual cluster review required")
        namespace = int(match[2])
        expected = (
            role_name(namespace, workspace)
            if match[1] == "work"
            else login_name(namespace, workspace)
        )
        if name != expected:
            raise ValueError("Noncanonical reserved namespace")
        namespaces.setdefault(namespace, {})[match[1]] = {
            "role_oid": oid,
            "can_login": can_login,
            "valid_until": until.isoformat() if until else None,
        }
    if len(rows) > 50 or len(namespaces) > 25:
        raise ValueError("Namespace inventory exceeds cap; no partial review")
    result = []
    for namespace, roles in sorted(namespaces.items()):
        login = login_name(namespace, workspace)
        result.append(
            {
                "namespace_oid": namespace,
                "database_present": db.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_database WHERE oid=%s)", (namespace,)
                ).fetchone()[0],
                "storage": roles.get("work"),
                "login": roles.get("wlogin"),
                "connections": db.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE usename=%s", (login,)
                ).fetchone()[0],
            }
        )
    return result


def _plan(db, request):
    target = _begin(db, request)
    inventory = _inventory(db, request.workspace_id)
    selected = [item for item in inventory if item["namespace_oid"] in request.namespace_oids]
    if len(selected) != len(request.namespace_oids):
        raise ValueError("Selected namespace missing")
    for item in selected:
        namespace = item["namespace_oid"]
        if namespace != target[1] and item["database_present"]:
            raise ValueError("Selected source database still exists; never change its credentials")
        if not item["storage"] or not item["login"]:
            raise ValueError("Selected namespace requires reviewed storage/login pair")
        role, login = (
            role_name(namespace, request.workspace_id),
            login_name(namespace, request.workspace_id),
        )
        active = item["login"]["can_login"]
        with db.cursor() as cursor:
            check_role(cursor, role, login=False, expected_membership=None)
            check_role(cursor, login, login=active, expected_membership=role if active else None)
        # No extra principals may SET either selected identity.
        incoming = db.execute(
            "SELECT r.rolname,m.admin_option,m.inherit_option,m.set_option FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE m.roleid=%s ORDER BY r.rolname",
            (item["storage"]["role_oid"],),
        ).fetchall()
        if (
            incoming != ([(login, False, False, True)] if active else [])
            or db.execute(
                "SELECT 1 FROM pg_auth_members WHERE roleid=%s LIMIT 1",
                (item["login"]["role_oid"],),
            ).fetchone()
        ):
            raise ValueError("Unreviewed incoming memberships")
    issued = work_lifecycle.clock(request.issued_at) if request.issued_at else work_drafts._now(db)
    _fresh(db, issued)
    body = {
        "schema_version": 1,
        "mode": "restored_work_credential_plan",
        "database": target[0],
        "database_oid": target[1],
        "operator_id": str(request.operator_id),
        "workspace_id": str(request.workspace_id),
        "issued_at": issued.isoformat(),
        "namespace_oids": request.namespace_oids,
        "inventory": inventory,
        "selected_profiles_verified": bool(selected),
        "activation_authorized": False,
        "recovery_complete": False,
        "unverified": [
            "in_flight_authentication_and_post_commit_sessions",
            "other_workspace_credentials",
            "other_database_ownership_and_cluster_roles",
            "independent_secrets_and_full_host_acceptance",
        ],
    }
    result = {
        **body,
        "reviewed_hash": hashlib.sha256(
            b"butler.restored-work-credentials.v1\n" + canonical(body)
        ).hexdigest(),
    }
    if len(canonical(result)) > 32768:
        raise ValueError("Metadata plan exceeds byte limit")
    return result


def reconcile(db, request: Request):
    """Caller commits role DDL and audit together. Never reactivate or kill sessions."""
    plan = _plan(db, request)
    if request.decision == "preview":
        return plan
    if not hmac.compare_digest(request.reviewed_hash, plan["reviewed_hash"]):
        raise ValueError("Plan changed or already applied; preview again")
    selected = [
        item for item in plan["inventory"] if item["namespace_oid"] in request.namespace_oids
    ]
    if any(item["connections"] for item in selected):
        raise ValueError("Drain all selected login sessions across the cluster first")
    if not any(item["login"]["can_login"] for item in selected):
        raise ValueError("No live selected credentials; no completion receipt")
    for item in selected:
        namespace = item["namespace_oid"]
        login = sql.Identifier(login_name(namespace, request.workspace_id))
        db.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(login))
        if item["login"]["can_login"]:
            db.execute(
                sql.SQL("REVOKE {} FROM {}").format(
                    sql.Identifier(role_name(namespace, request.workspace_id)), login
                )
            )
    receipt = uuid4()
    result = {
        "schema_version": 1,
        "mode": "restored_work_credentials_revoked",
        "receipt_id": str(receipt),
        "database": plan["database"],
        "database_oid": plan["database_oid"],
        "operator_id": plan["operator_id"],
        "workspace_id": plan["workspace_id"],
        "namespace_oids": request.namespace_oids,
        "plan_hash": plan["reviewed_hash"],
        "issued_at": plan["issued_at"],
        "activation_authorized": False,
        "recovery_complete": False,
        "post_commit_inspection_required": True,
        "unverified": plan["unverified"],
    }
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(%s,clock_timestamp(),%s,'local_admin','trusted_host_operator','restored_work_credentials','technical_admin','admin.restored_work_credentials_revoked','work_access_registry',%s,'success','{}',%s)",
        (receipt, settings.env, str(request.workspace_id), Jsonb(result)),
    )
    _fresh(db, datetime.fromisoformat(plan["issued_at"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--restored-database", required=True)
    parser.add_argument("--operator", required=True, type=UUID)
    parser.add_argument("--workspace", required=True, type=UUID)
    parser.add_argument("--namespace-oid", type=int, action="append", default=[])
    parser.add_argument("--issued-at", type=datetime.fromisoformat)
    parser.add_argument("--reviewed-hash")
    parser.add_argument(
        "--decision", choices=["preview", "revoke_restored_credentials"], default="preview"
    )
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        request = Request(
            restored_database=args.restored_database,
            operator_id=args.operator,
            workspace_id=args.workspace,
            namespace_oids=args.namespace_oid,
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
            "Restored credential quarantine failed; inspect local metadata, isolate/drain consumers and preview before retry\n",
        )
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
