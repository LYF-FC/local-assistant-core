"""Real API-created approvals/jobs, restored authority and worker lease fencing."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from conftest import RUNTIME_PASSWORD
from psycopg import sql
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from work_storage_helpers import connect

from app import jobs, work_drafts
from app import restore_execution as recovery
from app.config import settings
from app.manage import set_scope
from app.models import JobOutbox, User

pytestmark = pytest.mark.integration


@pytest.fixture
def case(scenario, runtime_engine):
    client, headers, initial, admin, user_id = scenario
    with admin.begin() as db:
        user = db.get(User, user_id)
        set_scope(db, user, "technical_admin", True)
        set_scope(db, user, "finance_private", True)

    def approval(scope="household_shared", approve=False):
        result = client.post(
            "/api/v1/approvals",
            headers=headers,
            json={"scope": scope, "payload": {"note": "synthetic-recovery-only"}},
        )
        assert result.status_code == 201
        record = result.json()
        if approve:
            response = client.post(
                f"/api/v1/approvals/{record['id']}/decide",
                headers=headers,
                json={
                    "payload_hash": record["payload_hash"],
                    "policy_version": record["policy_version"],
                    "decision": "approve",
                },
            )
            assert response.status_code == 200
        return record

    def enqueue():
        record = approval(approve=True)
        response = client.post(
            "/api/v1/jobs",
            headers=headers,
            json={
                "approval_id": record["id"],
                "payload_hash": record["payload_hash"],
                "policy_version": record["policy_version"],
                "idempotency_key": "synthetic-recovery-" + uuid4().hex,
            },
        )
        assert response.status_code == 201
        return UUID(response.json()["id"])

    runtime = sessionmaker(bind=runtime_engine, expire_on_commit=False)

    def claim_selected(identifier):
        with admin.begin() as db:
            db.scalars(
                select(JobOutbox).where(JobOutbox.job_id != identifier).with_for_update()
            ).all()
            with runtime.begin() as worker:
                lease = jobs.claim(worker)
        assert lease is not None
        return lease

    approved = approval(approve=True)
    queued = enqueue()
    running = enqueue()
    lease = claim_selected(running)
    completed = enqueue()
    finished = claim_selected(completed)
    with runtime.begin() as db:
        assert jobs.finish(db, finished)
    foreign = approval("finance_private")
    unselected = enqueue()
    return {
        "operator": user_id,
        "approval_ids": tuple(sorted((UUID(initial["id"]), UUID(approved["id"])))),
        "job_ids": tuple(sorted((queued, running, completed))),
        "queued": queued,
        "running": running,
        "completed": completed,
        "lease": lease,
        "runtime": runtime,
        "foreign": UUID(foreign["id"]),
        "unselected": unselected,
        "approved": approved,
    }


def request(case, **changes):
    return recovery.Request(
        **(
            {
                "restored_database": settings.postgres_db,
                "operator_id": case["operator"],
                "scope_key": "household_shared",
                "approval_ids": case["approval_ids"],
                "job_ids": case["job_ids"],
            }
            | changes
        )
    )


def run(case, **changes):
    with connect() as db, db.transaction():
        return recovery.reconcile(db, request(case, **changes))


def apply(case, plan):
    return run(
        case,
        issued_at=datetime.fromisoformat(plan["issued_at"]),
        reviewed_hash=plan["reviewed_hash"],
        decision="quarantine_restored_execution",
    )


def snapshot(case):
    with connect() as db:
        return (
            db.execute("SELECT * FROM public.approvals ORDER BY id").fetchall(),
            db.execute("SELECT * FROM public.durable_jobs ORDER BY id").fetchall(),
            db.execute("SELECT * FROM public.job_outbox ORDER BY id").fetchall(),
            db.execute(
                "SELECT count(*) FROM public.audit_events WHERE event_type='admin.restored_execution_quarantined' AND metadata_json::jsonb->>'operator_id'=%s",
                (str(case["operator"]),),
            ).fetchone()[0],
        )


def test_mixed_quarantine_cancels_authority_fences_old_lease_preserves_history(case):
    before = snapshot(case)
    plan = run(case)
    assert len(plan["items"]) == 5 and sum(i["changes_required"] for i in plan["items"]) == 4
    assert run(case, issued_at=datetime.fromisoformat(plan["issued_at"])) == plan
    encoded = json.dumps(plan)
    for hidden in (
        "payload_hash",
        "idempotency_hash",
        "lease_hash",
        "synthetic-recovery-only",
        case["lease"].token,
    ):
        assert hidden not in encoded
    result = apply(case, plan)
    assert not result["dispatch_activated"] and not result["recovery_complete"]
    after = snapshot(case)
    selected_approvals = set(case["approval_ids"])
    selected_jobs = {case["queued"], case["running"]}
    assert [r for r in before[0] if r[0] not in selected_approvals] == [
        r for r in after[0] if r[0] not in selected_approvals
    ]
    assert [r for r in before[1] if r[0] not in selected_jobs] == [
        r for r in after[1] if r[0] not in selected_jobs
    ]
    assert [row for row in before[2] if row[1] not in selected_jobs] == [
        row for row in after[2] if row[1] not in selected_jobs
    ]
    with connect() as held:
        held.execute(
            "SELECT id FROM public.job_outbox WHERE NOT(job_id=ANY(%s)) FOR UPDATE",
            (list(selected_jobs),),
        ).fetchall()
        with case["runtime"].begin() as worker:
            assert jobs.claim(worker) is None
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM public.approvals WHERE id=ANY(%s) AND status='cancelled'",
                (list(selected_approvals),),
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "SELECT count(*) FROM public.job_outbox WHERE job_id=ANY(%s) AND state='dead_letter' AND lease_hash IS NULL AND lease_until IS NULL",
                (list(selected_jobs),),
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s", (result["receipt_id"],)
            ).fetchone()[0]
            == result
        )
    with case["runtime"].begin() as db:
        assert not jobs.finish(db, case["lease"])
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    with pytest.raises(ValueError, match="No outstanding"):
        apply(case, run(case))


@pytest.mark.parametrize(
    "fault",
    [
        "target",
        "operator",
        "inactive",
        "foreign",
        "missing",
        "unknown",
        "pair",
        "outbox",
        "isolation",
        "runtime",
        "assumed",
        "old",
        "future",
    ],
)
def test_fail_closed_context_linkage_and_handler(case, fault):
    changes = {}
    if fault == "target":
        changes["restored_database"] = "butler_test_wrong"
    if fault == "operator":
        changes["operator_id"] = uuid4()
    if fault == "foreign":
        changes["approval_ids"] = (case["foreign"],)
    if fault == "missing":
        changes["approval_ids"] = (uuid4(),)
    if fault in {"old", "future"}:
        changes["issued_at"] = datetime.now(UTC) + timedelta(minutes=-6 if fault == "old" else 1)
    if fault in {"inactive", "unknown", "pair", "outbox"}:
        with connect() as db:
            if fault == "inactive":
                db.execute(
                    "UPDATE public.users SET is_active=false WHERE id=%s", (case["operator"],)
                )
            elif fault == "unknown":
                unknown = uuid4()
                db.execute(
                    "INSERT INTO public.approvals(id,scope_key,action_type,status,requested_by,request_payload,payload_hash,policy_version,requested_at,expires_at) VALUES(%s,'household_shared','future.external','pending',%s,'{}',repeat('a',64),'v0.1-record-only-1',clock_timestamp(),clock_timestamp()+interval '1 hour')",
                    (unknown, str(case["operator"])),
                )
                changes["approval_ids"] = (unknown,)
            elif fault == "pair":
                db.execute(
                    "UPDATE public.job_outbox SET state='dead_letter',lease_hash=NULL,lease_until=NULL WHERE job_id=%s",
                    (case["running"],),
                )
            else:
                db.execute("DELETE FROM public.job_outbox WHERE job_id=%s", (case["queued"],))
    before = snapshot(case)
    if fault in {"isolation", "runtime", "assumed"}:
        with (
            pytest.raises((ValueError, psycopg.Error)),
            connect(
                "butler_runtime" if fault == "runtime" else None,
                RUNTIME_PASSWORD if fault == "runtime" else None,
            ) as db,
            db.transaction(),
        ):
            if fault == "isolation":
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            if fault == "assumed":
                db.execute("SET LOCAL ROLE butler_runtime")
            recovery.reconcile(db, request(case))
    else:
        with pytest.raises(ValueError):
            run(case, **changes)
    assert snapshot(case) == before


def test_changed_approval_and_lease_metadata_invalidate_review(case):
    plan = run(case)
    with connect() as db:
        db.execute(
            "UPDATE public.job_outbox SET available_at=available_at+interval '1 second' WHERE job_id=%s",
            (case["queued"],),
        )
    before = snapshot(case)
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    assert snapshot(case) == before
    plan = run(case)
    with connect() as db:
        db.execute(
            "UPDATE public.approvals SET status='cancelled',resolved_at=COALESCE(resolved_at,clock_timestamp()) WHERE id=%s",
            (UUID(case["approved"]["id"]),),
        )
    before = snapshot(case)
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    assert snapshot(case) == before


def test_audit_failure_and_final_age_roll_back_every_change(case, monkeypatch):
    plan = run(case)
    before = snapshot(case)
    name = "synthetic_execution_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE public.audit_events ADD CONSTRAINT {} CHECK(event_type<>'admin.restored_execution_quarantined') NOT VALID"
            ).format(sql.Identifier(name))
        )
    try:
        with pytest.raises(psycopg.Error):
            apply(case, plan)
        assert snapshot(case) == before
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE public.audit_events DROP CONSTRAINT {}").format(
                    sql.Identifier(name)
                )
            )
    original = work_drafts._now
    calls = 0

    def late(db):
        nonlocal calls
        calls += 1
        return original(db) + timedelta(minutes=6) if calls >= 2 else original(db)

    monkeypatch.setattr(work_drafts, "_now", late)
    with pytest.raises(ValueError, match="current server"):
        apply(case, plan)
    assert snapshot(case) == before


def test_busy_writer_fails_fast_then_cleanup_succeeds(case):
    before = snapshot(case)
    with connect() as writer:
        writer.execute(
            "SELECT id FROM public.approvals WHERE id=%s FOR UPDATE", (case["approval_ids"][0],)
        )
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(run, case)
            with pytest.raises(psycopg.errors.LockNotAvailable):
                future.result(timeout=4)
    assert snapshot(case) == before
    apply(case, run(case))


def test_cleanup_fences_concurrent_worker_then_rejects_old_token(case):
    plan = run(case)
    with connect() as db, db.transaction():
        recovery.reconcile(
            db,
            request(
                case,
                issued_at=datetime.fromisoformat(plan["issued_at"]),
                reviewed_hash=plan["reviewed_hash"],
                decision="quarantine_restored_execution",
            ),
        )

        def worker():
            with case["runtime"].begin() as session:
                session.execute(text("SET LOCAL lock_timeout='200ms'"))
                return jobs.finish(session, case["lease"])

        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(worker)
            with pytest.raises(DBAPIError):
                future.result(timeout=4)
    with case["runtime"].begin() as session:
        assert not jobs.finish(session, case["lease"])


def test_actual_cli(case):
    base = [
        sys.executable,
        "-m",
        "app.restore_execution",
        "--environment",
        "test",
        "--restored-database",
        settings.postgres_db,
        "--operator",
        str(case["operator"]),
        "--scope",
        "household_shared",
    ]
    for identifier in case["approval_ids"]:
        base += ["--approval", str(identifier)]
    for identifier in case["job_ids"]:
        base += ["--job", str(identifier)]
    plan = json.loads(subprocess.check_output(base, text=True))
    args = [
        *base,
        "--issued-at",
        plan["issued_at"],
        "--reviewed-hash",
        plan["reviewed_hash"],
        "--decision",
        "quarantine_restored_execution",
    ]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)["outcomes"]) == 5
    replay = subprocess.run(args, capture_output=True, text=True, check=False)
    assert replay.returncode != 0 and not replay.stdout
