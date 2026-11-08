"""Audited metadata assessment of isolated recovery; never activation authority."""

import argparse
import hashlib
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from app import approvals, identity, work_drafts, work_lifecycle, work_suppression
from app import work_suppression_auth as authentication
from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import login_name, validate_target
from app.work_storage import role_name
from app.work_suppression_file import Manifest, canonical


class Request(work_lifecycle.Contract):
    restored_database: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9_]+$")
    operator_id: UUID
    workspace_id: UUID
    scope_key: str

    @model_validator(mode="after")
    def valid(self):
        if self.scope_key not in identity.SCOPES:
            raise ValueError("Known execution scope required")
        return self


class Evidence(work_lifecycle.Contract):
    manifest: Manifest
    key_id: UUID
    key_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    authentication_mode: str = "trusted_owner_input"

    @model_validator(mode="after")
    def valid(self):
        if self.authentication_mode not in {"trusted_owner_input", "hmac_sha256"}:
            raise ValueError("Known evidence boundary required")
        authentication.require_checkpoint(self.manifest, self.expected_manifest_hash)
        return self


CANDIDATES = """
SELECT 'approval' AS kind,a.id,a.status AS state,COALESCE(a.action_type=%s,false) AS action_supported,
 COALESCE(a.policy_version=%s AND a.expires_at IS NOT NULL AND a.payload_hash IS NOT NULL,false) AS linkage_valid
 FROM public.approvals a WHERE a.scope_key=%s AND a.status IN ('pending','approved')
UNION ALL
SELECT 'job',j.id,j.status,COALESCE(j.action_type=%s AND a.action_type=%s,false),
 COALESCE(a.id IS NOT NULL AND a.scope_key=j.scope_key AND a.status='consumed'
 AND a.requested_by=j.requested_by::text AND a.payload_hash=j.payload_hash AND o.id IS NOT NULL
 AND CASE j.status WHEN 'queued' THEN o.state='pending' WHEN 'running' THEN o.state='leased' ELSE false END
 AND CASE WHEN o.state='leased' THEN o.lease_hash IS NOT NULL AND o.lease_until IS NOT NULL
 ELSE o.lease_hash IS NULL AND o.lease_until IS NULL END,false)
 FROM public.durable_jobs j LEFT JOIN public.approvals a ON a.id=j.approval_id
 LEFT JOIN public.job_outbox o ON o.job_id=j.id
 WHERE j.scope_key=%s AND (j.status IN ('queued','running') OR o.state IN ('pending','leased'))
"""


UNVERIFIED = (
    "independent_latest_forgetting_coverage",
    "independent_key_and_credential_recovery",
    "current_and_copied_cluster_role_review",
    "other_workspaces",
    "original_sources_and_derived_stores",
    "unmanaged_exports",
    "external_effect_reconciliation",
    "full_host_offsite_and_owner_acceptance",
)


def _count(db, query, parameters=()):
    return db.execute(query, parameters).fetchone()[0]


def _begin(db, request):
    validate_target(settings.env)
    if (
        not isinstance(request, Request)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Explicit typed local transaction required")
    profile = db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),bool_and(current_user=pg_get_userbyid(relowner)),count(*) FROM pg_class WHERE oid IN ('public.auth_sessions'::regclass,'public.users'::regclass,'public.audit_events'::regclass,'public.approvals'::regclass,'public.durable_jobs'::regclass,'public.job_outbox'::regclass,'public.work_workspaces'::regclass,'public.work_access_grants'::regclass,'public.work_confirmation_requests'::regclass,'work.drafts'::regclass,'work.parties'::regclass,'work.capture_intents'::regclass,'work.draft_reviews'::regclass) GROUP BY 1,2"
    ).fetchone()
    if profile != (True, "read committed", True, 13):
        raise ValueError("Clean local recovery-table/audit owner required")
    target = db.execute(
        "SELECT datname,oid FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if request.restored_database != target[0] or target[0] != settings.postgres_db:
        raise ValueError("Explicit restored database must match actual configured target")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    if not _count(db, "SELECT pg_try_advisory_xact_lock(%s,%s)", REGISTRY_KEY):
        raise ValueError("Stop and drain Work consumers before assessment")
    db.execute(
        "LOCK TABLE public.auth_sessions,public.approvals,public.durable_jobs,public.job_outbox,public.work_workspaces,public.work_access_grants,public.work_confirmation_requests,work.drafts,work.parties,work.capture_intents,work.draft_reviews IN EXCLUSIVE MODE NOWAIT"
    )
    if not db.execute(
        "SELECT 1 FROM public.users u JOIN public.user_scopes us ON us.user_id=u.id JOIN public.scopes s ON s.id=us.scope_id WHERE u.id=%s AND u.is_active AND s.key='technical_admin' FOR SHARE OF u,us,s NOWAIT",
        (request.operator_id,),
    ).fetchone():
        raise ValueError("Active technical-admin audit reference required")
    workspace = db.execute(
        "SELECT is_active FROM public.work_workspaces WHERE id=%s AND slug LIKE 'synthetic-%%'",
        (request.workspace_id,),
    ).fetchone()
    if workspace is None:
        raise ValueError("Explicit synthetic workspace required")
    return target, workspace[0]


def _execution(db, request):
    params = (
        approvals.ACTION,
        approvals.POLICY,
        request.scope_key,
        approvals.ACTION,
        approvals.ACTION,
        request.scope_key,
    )
    rows = db.execute(
        sql.SQL("SELECT * FROM ({}) candidates ORDER BY kind,id LIMIT 26").format(
            sql.SQL(CANDIDATES)
        ),
        params,
    ).fetchall()
    totals = db.execute(
        sql.SQL(
            "SELECT count(*),count(*) FILTER(WHERE kind='approval'),count(*) FILTER(WHERE kind='job'),count(*) FILTER(WHERE NOT action_supported),count(*) FILTER(WHERE NOT linkage_valid) FROM ({}) candidates"
        ).format(sql.SQL(CANDIDATES)),
        params,
    ).fetchone()
    global_approvals = _count(
        db, "SELECT count(*) FROM public.approvals WHERE status IN ('pending','approved')"
    )
    global_jobs = _count(
        db,
        "SELECT count(*) FROM public.durable_jobs j LEFT JOIN public.job_outbox o ON o.job_id=j.id WHERE j.status IN ('queued','running') OR o.state IN ('pending','leased')",
    )
    return {
        "scope": request.scope_key,
        "outstanding_approvals": totals[1],
        "outstanding_jobs": totals[2],
        "total_candidates": totals[0],
        "unsupported_handlers": totals[3],
        "invalid_linkages": totals[4],
        "items": [
            {
                "kind": row[0],
                "id": str(row[1]),
                "state": row[2],
                "action_supported": row[3],
                "linkage_valid": row[4],
            }
            for row in rows[:25]
        ],
        "has_more": len(rows) > 25,
        "other_scope_outstanding": {
            "approvals": global_approvals - totals[1],
            "jobs": global_jobs - totals[2],
        },
    }


def _work(db, request, enabled):
    workspace = request.workspace_id
    pending = {
        "captures": _count(
            db,
            "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND state='pending'",
            (workspace,),
        ),
        "confirmations": _count(
            db,
            "SELECT count(*) FROM public.work_confirmation_requests WHERE workspace_id=%s AND state='pending'",
            (workspace,),
        ),
        "review_hashes": _count(
            db,
            "SELECT count(*) FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NOT NULL",
            (workspace,),
        ),
    }
    expired = {
        "notes": _count(
            db,
            "SELECT count(*) FROM work.drafts WHERE workspace_id=%s AND state<>'forgotten' AND retain_until<=clock_timestamp()",
            (workspace,),
        ),
        "parties": _count(
            db,
            "SELECT count(*) FROM work.parties WHERE workspace_id=%s AND state<>'forgotten' AND retain_until<=clock_timestamp()",
            (workspace,),
        ),
    }
    return {
        "workspace_id": str(workspace),
        "enabled": enabled,
        "grants": _count(
            db, "SELECT count(*) FROM public.work_access_grants WHERE workspace_id=%s", (workspace,)
        ),
        "pending_input": pending,
        "pending_effects": sum(pending.values()),
        "expired_live_records": expired,
        "other_workspaces": _count(
            db, "SELECT count(*) FROM public.work_workspaces WHERE id<>%s", (workspace,)
        ),
    }


def _credentials(db, oid, workspace):
    role = role_name(oid, workspace)
    login = login_name(oid, workspace)
    storage = bool(_count(db, "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)", (role,)))
    managed = db.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname=%s", (login,)).fetchone()
    return {
        "namespace": "current_database_oid_only",
        "storage_role_present": storage,
        "managed_login_present": managed is not None,
        "managed_login_can_login": bool(managed and managed[0]),
        "managed_connections": _count(
            db, "SELECT count(*) FROM pg_stat_activity WHERE usename=%s", (login,)
        ),
        "role_profile_verified": False,
        "credential_recovery_verified": False,
    }


def _checkpoint(db, request, work, now, evidence):
    if evidence is None:
        return {"mode": "not_supplied", "verified": False}, [
            "supply_independently_trusted_checkpoint"
        ]
    if (
        not isinstance(evidence, Evidence)
        or evidence.manifest.body.workspace_id != request.workspace_id
    ):
        raise ValueError("Matching typed workspace checkpoint evidence required")
    if evidence.manifest.body.generated_at > now:
        raise ValueError("Future checkpoint cannot be assessed")
    context = authentication.require_checkpoint(evidence.manifest, evidence.expected_manifest_hash)
    result = {
        "mode": "supplied_checkpoint",
        "verified": evidence.authentication_mode == "hmac_sha256",
        "authentication": {
            "mode": evidence.authentication_mode,
            "key_id": str(evidence.key_id),
            "key_fingerprint": evidence.key_fingerprint,
        },
        "checkpoint": context,
        "export_id": str(evidence.manifest.body.export_id),
        "generated_at": evidence.manifest.body.generated_at.isoformat(),
        "decision_count": len(evidence.manifest.body.items),
        "assessment": "requires_workspace_quarantine",
    }
    if work["enabled"] or work["grants"]:
        return result, ["assess_checkpoint_after_workspace_quarantine"]
    authenticated = evidence.authentication_mode == "hmac_sha256"
    plan = work_suppression.reconcile(
        db,
        work_suppression.Request(
            workspace_id=request.workspace_id,
            operator_id=request.operator_id,
            database=request.restored_database,
            issued_at=now,
            expected_manifest_hash=evidence.expected_manifest_hash,
            auth_key_id=evidence.key_id if authenticated else None,
            auth_key_fingerprint=evidence.key_fingerprint if authenticated else None,
        ),
        evidence.manifest,
    )
    pending = sum(item["changes_required"] for item in plan["items"])
    result.update(
        assessment="supplied_decisions_need_reconciliation"
        if pending
        else "no_supplied_changes_observed",
        changes_required=pending,
        linked_effects=plan["linked_count"],
    )
    # Never export the action review hash: existing tools require their own full review.
    return result, ["reconcile_supplied_forgetting"] if pending else []


def assess(db, request: Request, evidence: Evidence | None = None):
    """Caller commits inspection audit only; never mutate recovery business state."""
    target, enabled = _begin(db, request)
    now = work_drafts._now(db)
    sessions = _count(db, "SELECT count(*) FROM public.auth_sessions WHERE revoked_at IS NULL")
    execution = _execution(db, request)
    work = _work(db, request, enabled)
    credentials = _credentials(db, target[1], request.workspace_id)
    actions = []
    if sessions:
        actions.append("revoke_global_sessions")
    if work["enabled"] or work["grants"]:
        actions.append("quarantine_selected_workspace")
    if execution["total_candidates"]:
        actions.append("review_selected_scope_execution")
    if execution["unsupported_handlers"] or execution["invalid_linkages"]:
        actions.append("manually_reconcile_unsupported_or_inconsistent_execution")
    if sum(execution["other_scope_outstanding"].values()):
        actions.append("assess_other_execution_scopes")
    if work["pending_effects"]:
        actions.append("discard_pending_work_input")
    if sum(work["expired_live_records"].values()):
        actions.append("reconcile_expired_work_records")
    if credentials["managed_login_can_login"] or credentials["managed_connections"]:
        actions.append("review_managed_login_and_drain")
    checkpoint, checkpoint_actions = _checkpoint(db, request, work, now, evidence)
    actions.extend(checkpoint_actions)
    report = {
        "schema_version": 1,
        "mode": "isolated_recovery_assessment",
        "report_id": str(uuid4()),
        "database": target[0],
        "database_oid": target[1],
        "operator_id": str(request.operator_id),
        "assessed_at": now.isoformat(),
        "global_unrevoked_sessions": sessions,
        "execution": execution,
        "work": work,
        "credentials": credentials,
        "checkpoint": checkpoint,
        "required_actions": actions,
        "unverified_gates": list(UNVERIFIED),
        "activation_authorized": False,
        "recovery_complete": False,
    }
    report_hash = hashlib.sha256(b"butler.recovery-assessment.v1\n" + canonical(report)).hexdigest()
    result = {**report, "report_hash": report_hash}
    if len(canonical(result)) > 32768:
        raise ValueError("Assessment exceeds metadata byte bound")
    metadata = {
        key: report[key]
        for key in (
            "report_id",
            "database_oid",
            "operator_id",
            "required_actions",
            "activation_authorized",
            "recovery_complete",
        )
    }
    metadata.update(
        report_hash=report_hash, scope=request.scope_key, workspace_id=str(request.workspace_id)
    )
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(%s,clock_timestamp(),%s,'local_admin','trusted_host_operator','recovery_assessment','technical_admin','admin.recovery_assessed','recovery_assessment',%s,'success','{}',%s)",
        (UUID(report["report_id"]), settings.env, report["report_id"], Jsonb(metadata)),
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--restored-database", required=True)
    parser.add_argument("--operator", required=True, type=UUID)
    parser.add_argument("--workspace", required=True, type=UUID)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--recovery-key")
    parser.add_argument("--expected-key-fingerprint")
    parser.add_argument("--manifest")
    parser.add_argument("--expected-manifest-hash")
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        request = Request(
            restored_database=args.restored_database,
            operator_id=args.operator,
            workspace_id=args.workspace,
            scope_key=args.scope,
        )
        supplied = (
            args.recovery_key,
            args.expected_key_fingerprint,
            args.manifest,
            args.expected_manifest_hash,
        )
        evidence = None
        if any(value is not None for value in supplied):
            if not all(value is not None for value in supplied):
                raise ValueError("Complete independently pinned checkpoint inputs required")
            key = authentication.load_key(
                args.recovery_key, args.expected_key_fingerprint, args.workspace
            )
            manifest = authentication.read_signed(args.manifest, key, args.workspace)
            authentication.require_checkpoint(manifest, args.expected_manifest_hash)
            evidence = Evidence(
                manifest=manifest,
                key_id=key.key_id,
                key_fingerprint=authentication.fingerprint(key),
                expected_manifest_hash=args.expected_manifest_hash,
                authentication_mode="hmac_sha256",
            )
        with (
            psycopg.connect(
                settings.database_url.replace("postgresql+psycopg", "postgresql", 1),
                connect_timeout=3,
            ) as db,
            db.transaction(),
        ):
            result = assess(db, request, evidence)
    except (ValueError, psycopg.Error, OSError):
        parser.exit(
            1,
            "Recovery assessment failed; stop consumers and inspect target/evidence before retry\n",
        )
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
