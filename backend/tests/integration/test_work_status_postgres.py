"""Spec 073 acceptance tests 1–11, 4a, 4b and 16 on PostgreSQL with the restricted runtime role.

Every test runs in its own fresh database (see ``work_status_support``) so that household-wide
queue states reflect only the rows the test created. Observer calls run on the restricted role.
"""

import json
import os
import re
import subprocess
import sys
import threading
from datetime import timedelta
from uuid import UUID

import pytest
from conftest import RUNTIME_PASSWORD
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from work_status_support import (
    BACKEND,
    Clock,
    G,
    approved_job,
    create_task,
    deliver_reminder,
    delivery_for,
    filing_request,
    observe,
    post,
    save_policy,
    schedule,
    set_outbox,
    signed_in,
    status,
    unguarded,
)

from app import filing, filing_worker, identity, jobs, notification_worker, reminder_worker
from app import notifications as notes
from app.manage import set_scope
from app.models import (
    AuditEvent,
    AuthSession,
    DurableJob,
    FilingExecution,
    JobOutbox,
    NotificationDelivery,
    ReminderPreferences,
    TaskReminder,
    User,
)

pytestmark = pytest.mark.integration
S = timedelta(seconds=1)
D = notes.IN_FLIGHT_DEADLINE


def work_audits(db_ns, uid):
    with db_ns.owner() as db:
        return list(
            db.execute(
                select(AuditEvent.metadata_json, AuditEvent.result_status).where(
                    AuditEvent.event_type == "operations.work_status",
                    AuditEvent.initiator_id == str(uid),
                )
            )
        )


def reminders_rows(db_ns, now, limit=100):
    # Workers read the patched application clock; callers set it to ``now`` first.
    assert identity.now_utc() == now
    with db_ns.runtime() as db:
        return [str(r.id) for r in reminder_worker.candidates(db, limit)]


# --- test 1: approved jobs ----------------------------------------------------------------------


def test_approved_jobs_overdue_and_stalled_boundaries(ws):
    db = ws.db
    now = identity.now_utc()
    job = approved_job(ws)
    set_outbox(db, job, available_at=now - G - S)
    assert observe(db, now)["approved_jobs"] == "overdue"
    set_outbox(db, job, available_at=now - G + 5 * S)
    assert observe(db, now)["approved_jobs"] == "none_observed"
    set_outbox(db, job, available_at=now - timedelta(hours=1))
    with db.runtime.begin() as session:
        assert jobs.claim(session) is not None  # a fresh, live lease
    assert observe(db, identity.now_utc())["approved_jobs"] == "none_observed"
    now = identity.now_utc()
    set_outbox(db, job, lease_until=now - G - S)
    assert observe(db, now)["approved_jobs"] == "stalled"
    set_outbox(db, job, lease_until=now - G + 5 * S)
    assert observe(db, now)["approved_jobs"] == "none_observed"


def test_stalled_job_with_exhausted_attempts_is_dead_lettered_not_executed(ws):
    db = ws.db
    job = approved_job(ws)
    with db.runtime.begin() as session:
        assert jobs.claim(session) is not None
    now = identity.now_utc()
    set_outbox(db, job, attempts=3, lease_until=now - G - S)
    assert observe(db, now)["approved_jobs"] == "stalled"
    with db.runtime.begin() as session:
        assert jobs.claim(session) is None  # dead-lettered, never handed out for execution
    with db.owner() as session:
        outbox = session.get(JobOutbox, job)
        record = session.get(DurableJob, outbox.job_id)
        assert (outbox.state, record.status, record.result_code) == (
            "dead_letter",
            "dead_letter",
            "attempts_exhausted",
        )
    assert observe(db, identity.now_utc())["approved_jobs"] == "none_observed"


def test_claimed_job_whose_authority_lapsed_is_dead_lettered_by_finish(ws):
    db = ws.db
    job = approved_job(ws)
    with db.runtime.begin() as session:
        lease = jobs.claim(session)
    with db.owner.begin() as session:
        set_scope(session, session.get(User, ws.uid), "household_shared", False)
    with db.runtime.begin() as session:
        assert jobs.finish(session, lease)
    with db.owner() as session:
        record = session.get(DurableJob, session.get(JobOutbox, job).job_id)
        assert (record.status, record.result_code) == ("dead_letter", "authority_invalid")


# --- test 2: reminders --------------------------------------------------------------------------


def due_reminder(ws, clock, delay=10):
    save_policy(ws, 0)
    task = create_task(ws)
    return schedule(ws, task, clock.now + timedelta(seconds=delay))


def test_reminder_overdue_at_the_cutoff_boundary_and_never_stalled(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc())
    start = clock.now
    due_reminder(ws, clock)
    due = start + 10 * S
    assert observe(ws.db, due + G + S)["reminders"] == "overdue"
    assert observe(ws.db, due + G - 5 * S)["reminders"] == "none_observed"
    assert "stalled" not in {observe(ws.db, due + G * k)["reminders"] for k in range(1, 6)}


def test_reminder_deferred_disabled_or_future_is_not_overdue(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc())
    start = clock.now
    minute = start.hour * 60 + start.minute
    # Quiet hours cover now: one worker pass defers the reminder to a future next attempt.
    save_policy(ws, 0, quiet_start=minute, quiet_end=(minute + 120) % 1440)
    task = create_task(ws)
    row = schedule(ws, task, start + S)  # the API accepts only future schedules
    clock.set(start + 2 * S)
    assert deliver_reminder(ws.db, row["id"]) == "deferred"
    assert observe(ws.db, start + G + 10 * S)["reminders"] == "none_observed"
    # A future scheduled_at is not overdue.
    later = schedule(ws, create_task(ws), start + timedelta(hours=3))
    assert later["state"] == "scheduled"
    assert observe(ws.db, start + G + 10 * S)["reminders"] == "none_observed"
    # Disabled preferences: due, but excluded exactly as the worker excludes it.
    other = schedule(ws, create_task(ws), start + 5 * S)
    save_policy(ws, 1, enabled=False, quiet_start=0, quiet_end=0)
    clock.set(start + 10 * S)
    assert other["id"] not in reminders_rows(ws.db, clock.now)
    assert observe(ws.db, start + timedelta(minutes=10))["reminders"] == "none_observed"


def test_reminder_revision_mismatch_is_overdue_only_after_preferences_settle(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc())
    start = clock.now
    minute = start.hour * 60 + start.minute
    save_policy(ws, 0, quiet_start=minute, quiet_end=(minute + 120) % 1440)
    row = schedule(ws, create_task(ws), start + S)
    clock.set(start + 2 * S)
    assert deliver_reminder(ws.db, row["id"]) == "deferred"  # next attempt now in the future
    changed = clock.set(start + 30 * S)
    save_policy(ws, 1, quiet_start=minute, quiet_end=(minute + 120) % 1440, daily_limit=19)
    # The worker selects the mismatch immediately; the observer waits for the grace period.
    assert row["id"] in reminders_rows(ws.db, changed)
    assert observe(ws.db, changed + G - 5 * S)["reminders"] == "none_observed"
    assert observe(ws.db, changed + G + S)["reminders"] == "overdue"


def test_future_dated_preferences_hide_the_row_from_the_observer_but_not_the_worker(
    ws, monkeypatch
):
    clock = Clock(monkeypatch, identity.now_utc())
    start = clock.now
    row = due_reminder(ws, clock, delay=1)
    with unguarded(ws.db, "reminder_preferences", "butler_reminder_preferences_guard") as db:
        db.get(ReminderPreferences, ws.uid).updated_at = start + timedelta(hours=1)
    check = clock.set(start + G + 10 * S)
    assert observe(ws.db, check)["reminders"] == "none_observed"
    assert row["id"] in reminders_rows(ws.db, check)
    assert deliver_reminder(ws.db, row["id"]) == "delivered"


def test_future_dated_reminder_and_past_schedule_are_not_yet_overdue_but_selected(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc())
    start = clock.now
    row = due_reminder(ws, clock, delay=1)
    with unguarded(ws.db, "task_reminders", "butler_reminder_guard") as db:
        db.get(TaskReminder, UUID(row["id"])).updated_at = start + timedelta(hours=1)
    check = clock.set(start + G + 10 * S)
    assert observe(ws.db, check)["reminders"] == "none_observed"
    assert row["id"] in reminders_rows(ws.db, check)
    # A reminder created now (the API accepts only future times, so: due one second later) is
    # selected by the worker as soon as it is due, but observed only after the grace period.
    fresh = schedule(ws, create_task(ws), check + S)
    due = clock.set(check + S)
    assert fresh["id"] in reminders_rows(ws.db, due)
    assert observe(ws.db, due)["reminders"] == "none_observed"
    assert observe(ws.db, due + G + S)["reminders"] == "overdue"


def test_absent_preferences_follow_the_row_guard(fresh_database, monkeypatch):
    db_ns = fresh_database()
    with signed_in(db_ns) as scenario:
        clock = Clock(monkeypatch, identity.now_utc())
        start = clock.now
        row = schedule(scenario, create_task(scenario), start + S)  # no preferences saved
        with db_ns.owner() as db:
            assert db.get(ReminderPreferences, scenario.uid) is None
            assert db.get(TaskReminder, UUID(row["id"])).policy_revision == 0
        assert observe(db_ns, start + G - 5 * S)["reminders"] == "none_observed"
        assert observe(db_ns, start + S + G + S)["reminders"] == "overdue"
        # Non-zero policy revision without preferences (not reachable at runtime): same rule.
        with unguarded(db_ns, "task_reminders", "butler_reminder_guard") as db:
            reminder = db.get(TaskReminder, UUID(row["id"]))
            reminder.policy_revision, reminder.next_attempt_at = 3, start + timedelta(hours=5)
            reminder.updated_at = start + timedelta(minutes=10)
        clock.set(start + timedelta(minutes=10))
        assert row["id"] in reminders_rows(db_ns, clock.now)
        assert observe(db_ns, start + timedelta(minutes=10) + G - S)["reminders"] == (
            "none_observed"
        )
        assert observe(db_ns, start + timedelta(minutes=10) + G + S)["reminders"] == "overdue"


# --- test 3: notifications ----------------------------------------------------------------------


def delivered_reminder(ws, clock):
    save_policy(ws, 0)
    row = schedule(ws, create_task(ws), clock.now + S)
    clock.set(clock.now + 2 * S)
    assert deliver_reminder(ws.db, row["id"]) == "delivered"
    return row, clock.now


def enqueue(db_ns):
    with db_ns.runtime.begin() as db:
        return notification_worker.enqueue_pass(db, 100)


def test_enqueue_backlog_is_overdue_after_the_grace_period(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc())
    _, delivered = delivered_reminder(ws, clock)
    assert observe(ws.db, delivered + G - 5 * S)["notifications"] == "none_observed"
    assert observe(ws.db, delivered + G + S)["notifications"] == "overdue"


def test_future_dated_delivered_at_is_not_observed_but_still_enqueued(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc())
    row, delivered = delivered_reminder(ws, clock)
    with unguarded(ws.db, "task_reminders", "butler_reminder_guard") as db:
        db.get(TaskReminder, UUID(row["id"])).delivered_at = delivered + timedelta(hours=2)
    check = clock.set(delivered + G + 10 * S)
    assert observe(ws.db, check)["notifications"] == "none_observed"
    assert enqueue(ws.db) == 1


def test_pending_and_unknown_deliveries_and_stalled_attempts(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc())
    row, _ = delivered_reminder(ws, clock)
    queued = clock.set(clock.now + S)
    assert enqueue(ws.db) == 1
    assert observe(ws.db, queued + G - 5 * S)["notifications"] == "none_observed"
    assert observe(ws.db, queued + G + S)["notifications"] == "overdue"
    delivery = delivery_for(ws.db, row["id"])

    class Timeout(notes.SyntheticChannel):
        def send(self, key, recipient):
            self.sent += 1
            return notes.Outcome.TIMEOUT

    attempted = clock.set(queued + 2 * S)
    assert notification_worker.process(ws.db.runtime, delivery, Timeout()) == "unknown"
    due = attempted + notes.RECONCILE_INTERVAL
    assert observe(ws.db, due + G - 5 * S)["notifications"] == "none_observed"
    assert observe(ws.db, due + G + S)["notifications"] == "overdue"  # reconciliation is due

    class Crash(notes.SyntheticChannel):
        def send(self, key, recipient):
            raise KeyboardInterrupt

    # Reconcile as absent, then crash during the fresh attempt: an in-flight claim is left.
    clock.set(due + S)
    # Lookup proves the timed-out send absent: back to pending, never resent blindly.
    assert notification_worker.process(ws.db.runtime, delivery, notes.SyntheticChannel()) == (
        "retried"
    )
    with ws.db.owner() as db:
        assert db.get(NotificationDelivery, delivery.id).state == "pending"
    started = clock.set(due + 2 * S)
    with pytest.raises(KeyboardInterrupt):
        notification_worker.process(ws.db.runtime, delivery, Crash())
    assert observe(ws.db, started + D + G - 5 * S)["notifications"] == "none_observed"
    assert observe(ws.db, started + D + G + S)["notifications"] == "stalled"
    channel = notes.SyntheticChannel()
    clock.set(started + D + G + S)
    assert notification_worker.process(ws.db.runtime, delivery, channel) == "unknown"
    assert channel.sent == 0


def test_paused_delivery_is_excluded_but_unparked_disabled_owner_work_is_overdue(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc())
    row, _ = delivered_reminder(ws, clock)
    disabled = clock.set(clock.now + S)
    save_policy(ws, 1, enabled=False)
    assert enqueue(ws.db) == 1  # enqueue ignores preferences (stage 1)
    # Not yet parked: the worker's due work is to park it, so it is overdue after G.
    assert observe(ws.db, disabled + G + S)["notifications"] == "overdue"
    delivery = delivery_for(ws.db, row["id"])
    channel = notes.SyntheticChannel()
    clock.set(disabled + 2 * S)
    assert notification_worker.process(ws.db.runtime, delivery, channel) == "deferred"
    with ws.db.owner() as db:
        assert db.get(NotificationDelivery, delivery.id).reason == "paused"
    assert observe(ws.db, disabled + timedelta(minutes=30))["notifications"] == "none_observed"
    assert channel.sent == 0


# --- test 4: filing -----------------------------------------------------------------------------


def test_filing_overdue_stalled_and_scrub_constraint(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc())
    requested = clock.now
    row = filing_request(ws)
    assert observe(ws.db, requested + G - 5 * S)["filing"] == "none_observed"
    assert observe(ws.db, requested + G + S)["filing"] == "overdue"
    # Future-dated updated_at (fixture arrangement): not observed, still selected by the worker.
    with ws.db.owner() as db:
        original = db.get(FilingExecution, row.id).updated_at
    with unguarded(ws.db, "filing_executions", "butler_filing_guard") as db:
        db.get(FilingExecution, row.id).updated_at = requested + timedelta(hours=2)
    check = clock.set(requested + G + 10 * S)
    assert observe(ws.db, check)["filing"] == "none_observed"
    with ws.db.runtime() as db:
        assert row.id in {r.id for r in filing_worker.candidates(db, 100)}
    with unguarded(ws.db, "filing_executions", "butler_filing_guard") as db:
        db.get(FilingExecution, row.id).updated_at = original

    class Crash(filing.SyntheticDestination):
        def put(self, key, path, sha256, size):
            raise KeyboardInterrupt

    started = clock.set(requested + 2 * S)
    with pytest.raises(KeyboardInterrupt):
        filing_worker.process(ws.db.runtime, row, Crash())
    assert observe(ws.db, started + D + G - 5 * S)["filing"] == "none_observed"
    assert observe(ws.db, started + D + G + S)["filing"] == "stalled"
    destination = filing.SyntheticDestination()
    clock.set(started + D + G + S)
    assert filing_worker.process(ws.db.runtime, row, destination) == "unknown"
    assert destination.writes == 0
    # A scrubbed row can never be pending (so can never be selected): the constraint refuses it.
    with (
        pytest.raises(IntegrityError),
        unguarded(ws.db, "filing_executions", "butler_filing_guard") as db,
    ):
        db.execute(
            text(
                "UPDATE filing_executions SET scrubbed_at=updated_at, destination_key=NULL "
                "WHERE id=:id"
            ),
            {"id": row.id},
        )


# --- test 4a: clock rollback limitation ---------------------------------------------------------


def test_4a_clock_rollback_reports_prematurely_but_never_affects_workers(ws, monkeypatch):
    """Demonstrates the documented limitation (spec 073 §1.4.1); not correct behaviour."""
    clock = Clock(monkeypatch, identity.now_utc())
    base = clock.now
    save_policy(ws, 0)  # preferences settled well before the observation cutoff
    t0 = base + timedelta(minutes=10)  # the observer's time; cutoff c = t0 - G
    stepped = clock.set(t0 - G - 10 * S)  # the clock is behind real time for this write
    row = schedule(ws, create_task(ws), stepped + 5 * S)
    with ws.db.owner() as db:
        assert db.get(TaskReminder, UUID(row["id"])).updated_at <= t0 - G
    clock.set(t0)
    assert observe(ws.db, t0)["reminders"] == "overdue"  # premature by real time
    assert row["id"] in reminders_rows(ws.db, t0)
    assert deliver_reminder(ws.db, row["id"]) == "delivered"


# --- test 4b: enqueue versus permission to send; both timestamp guards ----------------------------


def test_4b_enqueue_then_park_then_resume_needs_both_guards(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc())
    row, delivered = delivered_reminder(ws, clock)
    clock.set(delivered + S)
    save_policy(ws, 1, enabled=False)
    # 1–2: delivered, preferences disabled, no delivery: overdue through the enqueue branch.
    c = clock.set(delivered + G + 10 * S)
    assert observe(ws.db, c)["notifications"] == "overdue"
    # 3: enqueue creates one pending delivery due now.
    assert enqueue(ws.db) == 1
    delivery = delivery_for(ws.db, row["id"])
    with ws.db.owner() as db:
        created = db.get(NotificationDelivery, delivery.id)
        assert (created.state, created.next_attempt_at) == ("pending", c)
    # 4: one pass parks it as paused and sends nothing.
    channel = notes.SyntheticChannel()
    t_p = clock.set(c + S)
    assert notification_worker.process(ws.db.runtime, delivery, channel) == "deferred"
    with ws.db.owner() as db:
        parked = db.get(NotificationDelivery, delivery.id)
        assert (parked.state, parked.reason) == ("pending", "paused")
        assert parked.next_attempt_at == parked.updated_at == t_p
    # 5: paused exclusion.
    assert observe(ws.db, t_p + timedelta(minutes=10))["notifications"] == "none_observed"
    # 6.1: re-enable through the real write path.
    t_e = clock.set(t_p + 2 * G)
    saved = save_policy(ws, 2, enabled=True)
    assert saved["revision"] == 3
    with ws.db.owner() as db:
        assert db.get(ReminderPreferences, ws.uid).updated_at == t_e

    def selected(at):
        clock.set(at)
        with ws.db.runtime() as db:
            return delivery.id in {r.id for r in notification_worker.candidates(db, 100)}

    # 6.2: the worker selects immediately; the observer does not report.
    assert selected(t_e)
    assert observe(ws.db, t_e)["notifications"] == "none_observed"
    # 6.3: only the preferences guard blocks.
    now1 = t_e + G / 2
    assert selected(now1)
    assert observe(ws.db, now1)["notifications"] == "none_observed"
    # 6.4: only the delivery guard blocks (fixture arrangement: updated_at only).
    now2 = t_e + 2 * G
    with ws.db.owner() as db:
        before = db.get(NotificationDelivery, delivery.id)
        snapshot = (before.state, before.reason, before.next_attempt_at, before.revision)
    with unguarded(ws.db, "notification_deliveries", "butler_notification_guard") as db:
        db.get(NotificationDelivery, delivery.id).updated_at = now2
    assert selected(now2)
    assert observe(ws.db, now2)["notifications"] == "none_observed"
    # 6.5: both guards hold.
    now3 = t_e + 3 * G + S
    assert selected(now3)
    assert observe(ws.db, now3)["notifications"] == "overdue"
    # 6.6: no side effects.
    with ws.db.owner() as db:
        after = db.get(NotificationDelivery, delivery.id)
        assert (after.state, after.reason, after.next_attempt_at, after.revision) == snapshot
    assert channel.sent == 0


# --- tests 5–11: output, privacy, authorization and failure -------------------------------------

EXPECTED_KEYS = [
    "actor_id",
    "checked_at",
    "excludes",
    "not_observed",
    "queues",
    "schema_version",
    "scope",
    "valid_until",
]


def test_precedence_and_exact_output(ws):
    overdue = approved_job(ws)
    stalled = approved_job(ws)
    now = identity.now_utc()
    set_outbox(ws.db, overdue, available_at=now - G - timedelta(minutes=1))
    set_outbox(ws.db, stalled, available_at=now - timedelta(hours=1))
    with ws.db.runtime.begin() as session:
        jobs.claim(session)
    for outbox in (overdue, stalled):
        with ws.db.owner() as db:
            row = db.get(JobOutbox, outbox)
            if row.state == "leased":
                set_outbox(ws.db, outbox, lease_until=now - G - timedelta(minutes=1))
    response = status(ws)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert sorted(body) == EXPECTED_KEYS
    assert [q["key"] for q in body["queues"]] == [
        "approved_jobs",
        "reminders",
        "notifications",
        "filing",
    ]
    assert all(sorted(q) == ["key", "state"] for q in body["queues"])
    assert body["queues"][0]["state"] == "stalled"
    assert body["not_observed"] == ["calendar_sync", "routines", "work"]
    assert body["excludes"] == [
        "counts",
        "ages",
        "owners_and_scopes",
        "items",
        "worker_liveness",
        "capacity",
        "backups",
        "restore",
    ]
    text_body = response.text
    with ws.db.owner() as db:
        for outbox in (overdue, stalled):
            row = db.get(JobOutbox, outbox)
            assert str(row.id) not in text_body and str(row.job_id) not in text_body
    assert "household_shared" not in text_body

    def numbers(value):
        if isinstance(value, dict):
            return [n for k, v in value.items() if k != "schema_version" for n in numbers(v)]
        if isinstance(value, list):
            return [n for v in value for n in numbers(v)]
        return [value] if isinstance(value, int | float) and not isinstance(value, bool) else []

    assert numbers(body) == []  # no counts anywhere


def pattern(fresh_database, scope):
    db_ns = fresh_database()
    with signed_in(db_ns, scopes=(scope, "technical_admin")) as scenario:
        now = identity.now_utc()
        record = post(
            scenario, "/api/v1/approvals", {"scope": scope, "payload": {"note": "synthetic"}}
        ).json()
        binding = {
            "payload_hash": record["payload_hash"],
            "policy_version": record["policy_version"],
        }
        post(
            scenario, f"/api/v1/approvals/{record['id']}/decide", dict(binding, decision="approve")
        )
        queued = post(
            scenario,
            "/api/v1/jobs",
            dict(binding, approval_id=record["id"], idempotency_key="synthetic-perm-" + scope),
        )
        assert queued.status_code == 201, queued.text
        with db_ns.owner.begin() as db:
            db.execute(
                text("UPDATE job_outbox SET available_at=:t"), {"t": now - G - timedelta(hours=1)}
            )
        return json.dumps(status(scenario).json()["queues"])


def test_permutation_between_owners_and_scopes_is_byte_identical(fresh_database):
    assert pattern(fresh_database, "household_shared") == pattern(
        fresh_database, "member_a_private"
    )


def test_observer_reads_only_allowed_tables_and_cannot_read_work_or_audit(ws):
    with ws.db.runtime() as db:
        assert db.scalar(text("SELECT has_schema_privilege('work', 'USAGE')")) is False
        assert (
            db.scalar(text("SELECT has_table_privilege('public.audit_events', 'SELECT')")) is False
        )
    with ws.db.owner() as db:
        work_table = db.scalar(
            text("SELECT tablename FROM pg_tables WHERE schemaname='work' ORDER BY 1 LIMIT 1")
        )
    assert work_table
    for statement in (f"SELECT 1 FROM work.{work_table} LIMIT 1", "SELECT 1 FROM audit_events"):
        with ws.db.runtime() as db, pytest.raises(DBAPIError):
            db.execute(text(statement))
    captured = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)

    event.listen(ws.db.runtime_engine, "before_cursor_execute", capture)
    try:
        assert status(ws).status_code == 200
    finally:
        event.remove(ws.db.runtime_engine, "before_cursor_execute", capture)
    read = set()
    for statement in captured:
        for match in re.finditer(r"\b(?:FROM|JOIN)\s+([a-z_\.]+)", statement):
            if match.group(1) not in {"false", "true", "null"}:
                read.add(match.group(1).removeprefix("public."))
    assert not any(name.startswith("work.") for name in read)
    queue_tables = {
        "job_outbox",
        "task_reminders",
        "reminder_preferences",
        "notification_deliveries",
        "filing_executions",
    }
    assert queue_tables <= read
    assert "audit_events" not in read
    assert any(s.startswith("INSERT INTO audit_events") for s in captured)
    others = read - queue_tables
    assert others <= {
        "users",
        "auth_sessions",
        "user_scopes",
        "scopes",
        "installation_state",
        "installation_revisions",
        "pg_catalog.set_config",
    }, others


def test_authorization_denials_return_no_payload(fresh_database):
    db_ns = fresh_database()
    with signed_in(db_ns, scopes=("household_shared",)) as member:
        response = status(member)
        assert response.status_code == 403 and "queues" not in response.text
    with signed_in(db_ns) as admin:
        assert (
            admin.client.post(
                "/api/v1/operations/work-status", json={"scope": "technical_admin"}
            ).status_code
            == 403
        )
        wrong_origin = admin.client.post(
            "/api/v1/operations/work-status",
            headers={**admin.headers, "Origin": "https://evil.invalid"},
            json={"scope": "technical_admin"},
        )
        assert wrong_origin.status_code == 403 and "queues" not in wrong_origin.text
        extra = status(admin, extra="x")
        assert extra.status_code == 422 and "queues" not in extra.text and '"x"' not in extra.text
        assert status(admin, scope="household_shared").status_code == 422
        with db_ns.owner.begin() as db:
            set_scope(db, db.get(User, admin.uid), "technical_admin", False)
        revoked = status(admin)
        assert revoked.status_code == 403 and "queues" not in revoked.text
        with db_ns.owner.begin() as db:
            set_scope(db, db.get(User, admin.uid), "technical_admin", True)
            for session in db.scalars(select(AuthSession).where(AuthSession.user_id == admin.uid)):
                session.last_seen_at = identity.now_utc() - timedelta(hours=2)
        idle = status(admin)
        assert idle.status_code == 401 and "queues" not in idle.text


def test_audit_failure_withholds_the_whole_response(ws):
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("synthetic-private-error")

    event.listen(ws.db.runtime_engine, "before_cursor_execute", fail)
    try:
        response = status(ws)
    finally:
        event.remove(ws.db.runtime_engine, "before_cursor_execute", fail)
    assert response.status_code == 503
    assert "queues" not in response.text and "synthetic-private" not in response.text
    assert work_audits(ws.db, ws.uid) == []


def test_lock_and_statement_timeouts_are_unavailable_never_a_state(ws, monkeypatch):
    holding, release = threading.Event(), threading.Event()

    def hold():
        with ws.db.owner.begin() as db:
            db.execute(text("LOCK TABLE task_reminders IN ACCESS EXCLUSIVE MODE"))
            holding.set()
            release.wait(30)

    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert holding.wait(10)
        locked = status(ws)
    finally:
        release.set()
        thread.join()
    assert locked.status_code == 503 and "queues" not in locked.text
    from app import operations

    # Statement timeout: no lock timeout, so the same wait is ended by the statement timeout.
    monkeypatch.setattr(operations, "WORK_LOCK_TIMEOUT", "0")
    monkeypatch.setattr(operations, "WORK_STATEMENT_TIMEOUT", "1s")
    holding.clear()
    release.clear()
    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert holding.wait(10)
        slow = status(ws)
    finally:
        release.set()
        thread.join()
    assert slow.status_code == 503 and "queues" not in slow.text
    assert work_audits(ws.db, ws.uid) == []


def test_successful_read_writes_exactly_one_metadata_free_audit_event(ws):
    response = status(ws)
    assert response.status_code == 200
    assert work_audits(ws.db, ws.uid) == [({}, "success")]
    with ws.db.owner() as db:
        count = db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "operations.work_status")
        )
    assert count == 1


# --- test 16: synthetic process test (real worker subprocess, synthetic channel only) -----------


def run_worker(db_ns):
    env = {
        **os.environ,
        "BUTLER_ENV": "test",
        "BUTLER_POSTGRES_DB": db_ns.name,
        "BUTLER_POSTGRES_USER": "butler_runtime",
        "BUTLER_POSTGRES_PASSWORD": RUNTIME_PASSWORD,
    }
    result = subprocess.run(
        [sys.executable, "-m", "app.notification_worker", "--once"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_16_real_worker_process_clears_overdue_and_converts_stalled(ws, monkeypatch):
    clock = Clock(monkeypatch, identity.now_utc() - 20 * S)
    save_policy(ws, 0)
    row = schedule(ws, create_task(ws), clock.now + S)
    clock.set(clock.now + 2 * S)
    assert deliver_reminder(ws.db, row["id"]) == "delivered"
    assert enqueue(ws.db) == 1  # due in the past relative to the real clock
    clock.real()
    now = identity.now_utc()
    assert observe(ws.db, now + G + S)["notifications"] == "overdue"
    out = run_worker(ws.db)
    assert "delivered=1" in out, out
    now = identity.now_utc()
    assert observe(ws.db, now + G + S)["notifications"] == "none_observed"
    # A second delivery left in flight past D + G: stalled until one fresh pass converts it.
    clock.set(identity.now_utc() - 10 * S)
    row2 = schedule(ws, create_task(ws), clock.now + S)
    clock.set(clock.now + 2 * S)
    assert deliver_reminder(ws.db, row2["id"]) == "delivered"
    assert enqueue(ws.db) == 1
    clock.real()
    delivery = delivery_for(ws.db, row2["id"])
    with unguarded(ws.db, "notification_deliveries", "butler_notification_guard") as db:
        stuck = db.get(NotificationDelivery, delivery.id)
        stuck.attempts, stuck.attempt_started_at = 1, identity.now_utc() - D - G - S
    assert observe(ws.db, identity.now_utc())["notifications"] == "stalled"
    out = run_worker(ws.db)
    assert "unknown=1" in out, out
    with ws.db.owner() as db:
        assert db.get(NotificationDelivery, delivery.id).state == "unknown"
    assert observe(ws.db, identity.now_utc())["notifications"] != "stalled"
