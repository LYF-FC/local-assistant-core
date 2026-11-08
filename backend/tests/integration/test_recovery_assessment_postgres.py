"""Bounded audited metadata assessment and known-checkpoint recovery integration."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from conftest import RUNTIME_PASSWORD
from psycopg import sql
from work_storage_helpers import connect

from app import recovery_assessment as assessment
from app import work_restore, work_suppression
from app import work_suppression_auth as auth
from app.config import settings
from app.manage import set_scope
from app.models import User
from app.work_suppression_file import Body, Manifest, digest

pytestmark = pytest.mark.integration


@pytest.fixture
def case(review_case):
    with review_case["maker"].begin() as db:
        user = db.get(User, review_case["actor"])
        set_scope(db, user, "technical_admin", True)
        set_scope(db, user, "finance_private", True)
    client = review_case["client"]
    headers = review_case["headers"]
    pending = client.post(
        "/api/v1/approvals",
        headers=headers,
        json={"scope": "finance_private", "payload": {"note": "synthetic:assessment-private"}},
    )
    assert pending.status_code == 201
    record = client.post(
        "/api/v1/approvals",
        headers=headers,
        json={"scope": "finance_private", "payload": {"note": "synthetic:assessment-job"}},
    ).json()
    assert (
        client.post(
            f"/api/v1/approvals/{record['id']}/decide",
            headers=headers,
            json={
                "decision": "approve",
                "payload_hash": record["payload_hash"],
                "policy_version": record["policy_version"],
            },
        ).status_code
        == 200
    )
    queued = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "approval_id": record["id"],
            "payload_hash": record["payload_hash"],
            "policy_version": record["policy_version"],
            "idempotency_key": "synthetic-assessment-" + uuid4().hex,
        },
    )
    assert queued.status_code == 201
    return dict(review_case, pending=pending.json()["id"], job=queued.json()["id"])


def request(case, **changes):
    return assessment.Request(
        **(
            {
                "restored_database": settings.postgres_db,
                "operator_id": case["actor"],
                "workspace_id": case["workspace"],
                "scope_key": "finance_private",
            }
            | changes
        )
    )


def run(case, evidence=None, **changes):
    with connect() as db, db.transaction():
        return assessment.assess(db, request(case, **changes), evidence)


def snapshot():
    tables = [
        ("public", name)
        for name in (
            "users",
            "user_scopes",
            "auth_credentials",
            "auth_sessions",
            "approvals",
            "durable_jobs",
            "job_outbox",
            "memory_records",
            "work_workspaces",
            "work_access_grants",
            "work_confirmation_requests",
        )
    ] + [
        ("work", name)
        for name in ("drafts", "parties", "draft_reviews", "capture_intents", "draft_revisions")
    ]
    with connect() as db:
        return {
            (schema, table): db.execute(
                sql.SQL("SELECT * FROM {}.{} ORDER BY 1,2").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            ).fetchall()
            for schema, table in tables
        }


def evidence(case, **changes):
    body = Body(
        export_id=uuid4(),
        workspace_id=case["workspace"],
        exported_by=case["actor"],
        source_database_oid=1,
        generated_at=datetime.now(UTC),
        items=(
            {
                "kind": "note",
                "id": case["item"].id,
                "forgotten_revision": 2,
                "forgotten_at": datetime.now(UTC) - timedelta(seconds=1),
            },
        ),
        **changes,
    )
    value = Manifest(body=body, digest=digest(body))
    key = auth.generate_key(case["workspace"])
    return assessment.Evidence(
        manifest=value,
        key_id=key.key_id,
        key_fingerprint=auth.fingerprint(key),
        expected_manifest_hash=value.digest,
    ), key


def quarantine(case):
    with connect() as db, db.transaction():
        context = {
            "restored_database": settings.postgres_db,
            "operator_id": case["actor"],
            "workspace_id": case["workspace"],
        }
        plan = work_restore.reconcile(db, work_restore.Request(**context))
        work_restore.reconcile(
            db,
            work_restore.Request(
                **context,
                issued_at=datetime.fromisoformat(plan["issued_at"]),
                reviewed_hash=plan["reviewed_hash"],
                decision="quarantine_restored_workspace",
            ),
        )


def test_inventory_exact_counts_audits_without_business_mutation(case):
    before = snapshot()
    report = run(case)
    assert snapshot() == before
    assert report["work"]["enabled"] and report["work"]["grants"] == 1
    assert report["execution"]["total_candidates"] >= 2
    assert report["execution"]["other_scope_outstanding"]["approvals"] >= 1
    assert report["global_unrevoked_sessions"] >= 1
    assert (
        not report["checkpoint"]["verified"]
        and "supply_independently_trusted_checkpoint" in report["required_actions"]
    )
    assert not report["activation_authorized"] and not report["recovery_complete"]
    assert "full_host_offsite_and_owner_acceptance" in report["unverified_gates"]
    assert report["credentials"]["credential_recovery_verified"] is False
    encoded = json.dumps(report)
    for hidden in (
        "synthetic:assessment-private",
        "synthetic:review-note",
        "token_hash",
        "csrf_hash",
        "password_hash",
        "payload_hash",
        "lease_hash",
        "idempotency_hash",
        case["slug"],
    ):
        assert hidden not in encoded
    with connect() as db:
        meta = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE id=%s", (report["report_id"],)
        ).fetchone()[0]
        assert meta["report_hash"] == report["report_hash"] and not meta["activation_authorized"]
        assert "items" not in meta and "synthetic:assessment-private" not in json.dumps(meta)
        count = db.execute(
            "SELECT count(*) FROM public.approvals WHERE scope_key='finance_private' AND status IN ('pending','approved')"
        ).fetchone()[0]
        assert report["execution"]["outstanding_approvals"] == count


def test_cap_is_explicit_and_unsafe_candidates_not_hidden(case):
    with connect() as db:
        for _ in range(27):
            db.execute(
                "INSERT INTO public.approvals(id,scope_key,action_type,status,requested_by,request_payload,payload_hash,policy_version,requested_at,expires_at) VALUES(%s,'finance_private','future.external','pending',%s,'{}',repeat('a',64),'v0.1-record-only-1',clock_timestamp(),clock_timestamp()+interval '1 hour')",
                (uuid4(), str(case["actor"])),
            )
        db.execute(
            "UPDATE public.job_outbox SET state='dead_letter',lease_hash=NULL,lease_until=NULL WHERE job_id=%s",
            (case["job"],),
        )
    report = run(case)
    assert report["execution"]["has_more"] and len(report["execution"]["items"]) == 25
    assert (
        report["execution"]["unsupported_handlers"] >= 27
        and report["execution"]["invalid_linkages"] >= 1
    )
    assert "manually_reconcile_unsupported_or_inconsistent_execution" in report["required_actions"]


@pytest.mark.parametrize(
    "fault",
    [
        "target",
        "operator",
        "inactive",
        "workspace",
        "ordinary",
        "runtime",
        "assumed",
        "isolation",
        "idle",
    ],
)
def test_unsafe_context_does_not_mutate_or_append_success(case, fault):
    changes = {}
    if fault == "target":
        changes["restored_database"] = "butler_test_wrong"
    if fault == "operator":
        changes["operator_id"] = uuid4()
    if fault == "workspace":
        changes["workspace_id"] = uuid4()
    if fault == "ordinary":
        with connect() as db:
            db.execute(
                "UPDATE public.work_workspaces SET slug=%s WHERE id=%s",
                ("ordinary-" + uuid4().hex, case["workspace"]),
            )
    if fault == "inactive":
        with connect() as db:
            db.execute("UPDATE public.users SET is_active=false WHERE id=%s", (case["actor"],))
    before = snapshot()
    if fault in {"runtime", "assumed", "isolation", "idle"}:
        with (
            pytest.raises((ValueError, psycopg.Error)),
            connect(
                "butler_runtime" if fault == "runtime" else None,
                RUNTIME_PASSWORD if fault == "runtime" else None,
            ) as db,
        ):
            if fault != "idle":
                db.execute("BEGIN")
            if fault == "assumed":
                db.execute("SET LOCAL ROLE butler_runtime")
            if fault == "isolation":
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            assessment.assess(db, request(case))
    else:
        with pytest.raises(ValueError):
            run(case, **changes)
    assert snapshot() == before
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM public.audit_events WHERE event_type='admin.recovery_assessed' AND metadata_json::jsonb->>'operator_id'=%s",
                (str(case["actor"]),),
            ).fetchone()[0]
            == 0
        )


def test_checkpoint_assesses_actual_suppression_preview_but_never_applies(case):
    supplied, _ = evidence(case)
    active = run(case, supplied)
    assert active["checkpoint"]["assessment"] == "requires_workspace_quarantine"
    assert (
        not active["checkpoint"]["verified"]
        and active["checkpoint"]["authentication"]["mode"] == "trusted_owner_input"
    )
    quarantine(case)
    before = snapshot()
    report = run(case, supplied)
    assert snapshot() == before
    assert (
        report["checkpoint"]["changes_required"] == 1
        and "reconcile_supplied_forgetting" in report["required_actions"]
    )
    assert "reviewed_hash" not in report["checkpoint"]
    with connect() as db, db.transaction():
        context = {
            "workspace_id": case["workspace"],
            "operator_id": case["actor"],
            "database": settings.postgres_db,
            "expected_manifest_hash": supplied.expected_manifest_hash,
        }
        plan = work_suppression.reconcile(
            db, work_suppression.Request(**context), supplied.manifest
        )
        work_suppression.reconcile(
            db,
            work_suppression.Request(
                **context,
                decision="reconcile_restored_suppressions",
                issued_at=datetime.fromisoformat(plan["issued_at"]),
                reviewed_hash=plan["reviewed_hash"],
            ),
            supplied.manifest,
        )
    after = run(case, supplied)
    assert after["checkpoint"]["changes_required"] == 0
    assert (
        not after["activation_authorized"]
        and not after["recovery_complete"]
        and after["unverified_gates"]
    )


def test_future_or_cross_workspace_checkpoint_rejects_without_audit(case):
    supplied, _ = evidence(case)
    changed = supplied.manifest.body.model_copy(
        update={"generated_at": datetime.now(UTC) + timedelta(hours=1)}
    )
    future = assessment.Evidence(
        manifest=Manifest(body=changed, digest=digest(changed)),
        key_id=supplied.key_id,
        key_fingerprint=supplied.key_fingerprint,
        expected_manifest_hash=digest(changed),
    )
    before = snapshot()
    with pytest.raises(ValueError, match="Future"):
        run(case, future)
    with pytest.raises(ValueError, match="workspace"):
        run(case, supplied, workspace_id=case["storage"]["b"]["workspace"])
    assert snapshot() == before


def test_audit_failure_rolls_back_report_and_preserves_business_state(case):
    before = snapshot()
    name = "synthetic_assessment_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE public.audit_events ADD CONSTRAINT {} CHECK(event_type<>'admin.recovery_assessed') NOT VALID"
            ).format(sql.Identifier(name))
        )
    try:
        with pytest.raises(psycopg.Error):
            run(case)
        assert snapshot() == before
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE public.audit_events DROP CONSTRAINT {}").format(
                    sql.Identifier(name)
                )
            )


@pytest.mark.parametrize("busy", ["registry", "writer"])
def test_busy_recovery_context_fails_fast_without_report(case, busy):
    before = snapshot()
    with connect() as db:
        if busy == "registry":
            db.execute("SELECT pg_advisory_xact_lock_shared(1508310,1)")
        else:
            db.execute("SELECT id FROM public.auth_sessions LIMIT 1 FOR UPDATE")
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(run, case)
            with pytest.raises((ValueError, psycopg.errors.LockNotAvailable)):
                future.result(timeout=4)
    assert snapshot() == before


def test_actual_cli_verified_checkpoint_and_missing_evidence_paths(case, tmp_path):
    supplied, key = evidence(case)
    key_path = tmp_path / "key.json"
    path = tmp_path / "manifest.json"
    auth.write_key(key_path, key)
    auth.write_signed(path, supplied.manifest, key)
    base = [
        sys.executable,
        "-m",
        "app.recovery_assessment",
        "--environment",
        "test",
        "--restored-database",
        settings.postgres_db,
        "--operator",
        str(case["actor"]),
        "--workspace",
        str(case["workspace"]),
        "--scope",
        "finance_private",
    ]
    empty = json.loads(subprocess.check_output(base, text=True))
    assert not empty["checkpoint"]["verified"]
    args = [
        *base,
        "--recovery-key",
        str(key_path),
        "--expected-key-fingerprint",
        auth.fingerprint(key),
        "--manifest",
        str(path),
        "--expected-manifest-hash",
        supplied.expected_manifest_hash,
    ]
    before = snapshot()
    report = json.loads(subprocess.check_output(args, text=True))
    assert snapshot() == before
    assert (
        report["checkpoint"]["verified"]
        and report["checkpoint"]["checkpoint"]["manifest_hash"] == supplied.expected_manifest_hash
    )
    assert (
        key.material.get_secret_value() not in json.dumps(report)
        and not report["activation_authorized"]
    )


def test_current_oid_login_observation_never_claims_role_or_secret_recovery(case):
    from app.work_credentials import login_name

    with connect() as db:
        oid = db.execute("SELECT oid FROM pg_database WHERE datname=current_database()").fetchone()[
            0
        ]
        login = login_name(oid, case["workspace"])
        db.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
            ).format(
                sql.Identifier(login),
                sql.Literal("synthetic-assessment-managed-password-0123456789"),
            )
        )
    try:
        with connect(login, "synthetic-assessment-managed-password-0123456789"):
            report = run(case)
        assert (
            report["credentials"]["managed_login_present"]
            and report["credentials"]["managed_login_can_login"]
        )
        assert report["credentials"]["managed_connections"] == 1
        assert (
            not report["credentials"]["role_profile_verified"]
            and not report["credentials"]["credential_recovery_verified"]
        )
        assert "review_managed_login_and_drain" in report["required_actions"]
        assert "synthetic-assessment-managed-password" not in json.dumps(report)
    finally:
        with connect() as db:
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(login)))


def test_expired_live_work_counts_are_observations_not_cleanup(case):
    from app import work_drafts, work_lifecycle, work_parties

    with connect() as db:
        until = work_drafts._now(db) + timedelta(seconds=2)
        work_drafts.create(
            db,
            case["workspace"],
            case["actor"],
            case["policy"],
            work_lifecycle.Draft(
                kind="decision",
                marker="synthetic:assessment-expiry",
                source_ids=(case["source"],),
                retain_until=until,
            ),
        )
        work_parties.create(
            db, case["workspace"], case["policy"], "synthetic:assessment-party", until
        )
    with connect() as db:
        db.execute(
            "SELECT pg_sleep(GREATEST(0,extract(epoch FROM (%s-clock_timestamp()))))",
            (until + timedelta(milliseconds=30),),
        )
    before = snapshot()
    report = run(case)
    assert report["work"]["expired_live_records"] == {"notes": 1, "parties": 1}
    assert "reconcile_expired_work_records" in report["required_actions"]
    assert snapshot() == before
