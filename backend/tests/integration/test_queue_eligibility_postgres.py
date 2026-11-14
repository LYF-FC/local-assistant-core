"""Spec 073 acceptance tests 12–15: worker selection is unchanged and never delayed by the grace.

Frozen copies of the five pre-refactor selection statements (verbatim from ``main`` at
2e04ff8) run against one fixture matrix in a fresh database. The refactored workers must return
identical ordered candidate IDs; the shared rules E1–E8 at a time ``t`` must select exactly the
rows each worker selects at ``t``; and the observer's grace must never delay a worker.
"""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import and_, func, or_, select
from work_status_support import (
    Clock,
    G,
    approved_job,
    create_task,
    deliver_reminder,
    delivery_for,
    filing_request,
    observe,
    save_policy,
    schedule,
    set_outbox,
    signed_in,
    unguarded,
)

from app import (
    filing_worker,
    identity,
    jobs,
    notification_worker,
    operations,
    reminder_worker,
)
from app import notifications as notes
from app import queue_eligibility as eligible
from app.models import (
    FilingExecution,
    JobOutbox,
    NotificationDelivery,
    ReminderPreferences,
    TaskReminder,
)

pytestmark = pytest.mark.integration
S = timedelta(seconds=1)
D = notes.IN_FLIGHT_DEADLINE

# --- frozen pre-refactor selection statements ---------------------------------------------------


def frozen_job_claim(now):
    return (
        select(JobOutbox.id)
        .where(
            or_(
                (JobOutbox.state == "pending") & (JobOutbox.available_at <= now),
                (JobOutbox.state == "leased") & (JobOutbox.lease_until <= now),
            )
        )
        .order_by(JobOutbox.available_at, JobOutbox.id)
        .limit(1)
    )


def frozen_reminders(now, limit):
    return (
        select(TaskReminder.id)
        .outerjoin(ReminderPreferences, ReminderPreferences.owner_id == TaskReminder.owner_id)
        .where(
            TaskReminder.state == "scheduled",
            TaskReminder.scheduled_at <= now,
            or_(ReminderPreferences.owner_id.is_(None), ReminderPreferences.enabled.is_(True)),
            or_(
                TaskReminder.next_attempt_at <= now,
                TaskReminder.policy_revision != func.coalesce(ReminderPreferences.revision, 0),
            ),
        )
        .order_by(TaskReminder.next_attempt_at, TaskReminder.id)
        .limit(limit)
    )


def frozen_enqueue(limit):
    return (
        select(TaskReminder.id)
        .outerjoin(
            NotificationDelivery,
            and_(
                NotificationDelivery.reminder_id == TaskReminder.id,
                NotificationDelivery.cycle == TaskReminder.cycle,
            ),
        )
        .where(TaskReminder.state == "delivered", NotificationDelivery.id.is_(None))
        .order_by(TaskReminder.id)
        .limit(limit)
    )


def frozen_notifications(now, limit):
    stale = now - notes.IN_FLIGHT_DEADLINE
    return (
        select(NotificationDelivery.id)
        .outerjoin(
            ReminderPreferences, ReminderPreferences.owner_id == NotificationDelivery.owner_id
        )
        .where(
            or_(
                NotificationDelivery.reason.is_distinct_from("paused"),
                ReminderPreferences.enabled.is_distinct_from(False),
            ),
            or_(
                and_(
                    NotificationDelivery.state.in_(("pending", "unknown")),
                    NotificationDelivery.next_attempt_at <= now,
                    NotificationDelivery.attempt_started_at.is_(None),
                ),
                and_(
                    NotificationDelivery.state == "pending",
                    NotificationDelivery.attempt_started_at <= stale,
                ),
            ),
        )
        .order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id)
        .limit(limit)
    )


def frozen_filing(now, limit):
    stale = now - notes.IN_FLIGHT_DEADLINE
    return (
        select(FilingExecution.id)
        .where(
            or_(
                and_(
                    FilingExecution.state.in_(("pending", "unknown")),
                    FilingExecution.next_attempt_at <= now,
                    FilingExecution.attempt_started_at.is_(None),
                ),
                and_(
                    FilingExecution.state == "pending",
                    FilingExecution.attempt_started_at <= stale,
                ),
            )
        )
        .order_by(FilingExecution.next_attempt_at, FilingExecution.id)
        .limit(limit)
    )


# --- fixture matrix -----------------------------------------------------------------------------


def build_matrix(fresh_database, monkeypatch):
    """Rows covering every branch and both sides of every boundary, for three owners."""
    db_ns = fresh_database()
    base = identity.now_utc()
    clock = Clock(monkeypatch, base)
    with signed_in(db_ns) as first, signed_in(db_ns) as second, signed_in(db_ns) as third:
        # Approved jobs: pending due and not yet due, leased live, leased expired and exhausted.
        outboxes = [approved_job(first) for _ in range(4)]
        set_outbox(db_ns, outboxes[0], available_at=base - timedelta(minutes=5))
        set_outbox(db_ns, outboxes[1], available_at=base + timedelta(minutes=5))
        live = {"state": "leased", "attempts": 1, "lease_hash": "0" * 64}
        set_outbox(db_ns, outboxes[2], lease_until=base + timedelta(minutes=1), **live)
        exhausted = {"state": "leased", "attempts": 3, "lease_hash": "0" * 64}
        set_outbox(db_ns, outboxes[3], lease_until=base - timedelta(minutes=3), **exhausted)
        # Reminders: first owner with preferences, second without, third disabled later.
        save_policy(first, 0)
        save_policy(third, 0)
        r = [schedule(first, create_task(first), base + k * S) for k in (1, 2, 3, 4, 5)]
        future = schedule(first, create_task(first), base + timedelta(hours=2))
        absent = schedule(second, create_task(second), base + 6 * S)
        t0 = schedule(third, create_task(third), base + 7 * S)
        clock.set(base + 10 * S)
        for row in (r[0], r[1], r[2], t0):
            assert deliver_reminder(db_ns, row["id"]) == "delivered"
        with db_ns.runtime.begin() as db:
            assert notification_worker.enqueue_pass(db, 100) == 4
        assert deliver_reminder(db_ns, r[3]["id"]) == "delivered"  # stays enqueue-eligible
        # Third owner: disabled preferences and a parked (paused) delivery.
        save_policy(third, 1, enabled=False)
        channel = notes.SyntheticChannel()
        assert notification_worker.process(
            db_ns.runtime, delivery_for(db_ns, t0["id"]), channel
        ) == ("deferred")
        # First owner: one paused delivery whose owner resumed (eligible again).
        save_policy(first, 1, enabled=False)
        assert notification_worker.process(
            db_ns.runtime, delivery_for(db_ns, r[2]["id"]), channel
        ) == ("deferred")
        save_policy(first, 2, enabled=True)
        assert channel.sent == 0
        # Unknown due, in flight at D - 1 s / D + 1 s relative to the first comparison time.
        unknown, in_flight = delivery_for(db_ns, r[0]["id"]), delivery_for(db_ns, r[1]["id"])
        with unguarded(db_ns, "notification_deliveries", "butler_notification_guard") as db:
            row = db.get(NotificationDelivery, unknown.id)
            row.state, row.reason, row.next_attempt_at = "unknown", "ambiguous_outcome", base
            row.attempts = 1
            row = db.get(NotificationDelivery, in_flight.id)
            row.attempts, row.attempt_started_at = 1, base + 10 * S - D + S
        # Future-dated timestamps and an absent-preferences mismatch (fixture arrangements).
        with unguarded(db_ns, "task_reminders", "butler_reminder_guard") as db:
            db.get(TaskReminder, UUID(r[4]["id"])).updated_at = base + timedelta(hours=3)
            db.get(TaskReminder, UUID(r[3]["id"])).delivered_at = base + timedelta(hours=3)
            db.get(TaskReminder, UUID(absent["id"])).policy_revision = 2
        with unguarded(db_ns, "reminder_preferences", "butler_reminder_preferences_guard") as db:
            db.get(ReminderPreferences, first.uid).updated_at = base + timedelta(hours=3)
        # Filing: one request, in flight just before the deadline at the first comparison time.
        filing_row = filing_request(first)
        with unguarded(db_ns, "filing_executions", "butler_filing_guard") as db:
            row = db.get(FilingExecution, filing_row.id)
            started = base + 10 * S - D + S
            # As a real claim does: the first attempt consumes the authorization.
            row.attempts, row.attempt_started_at, row.authorization_consumed_at = (
                1,
                started,
                started,
            )
        assert future["state"] == "scheduled"
        rows = {
            "unknown": unknown.id,
            "in_flight": in_flight.id,
            "resumed_paused": delivery_for(db_ns, r[2]["id"]).id,
            "parked_paused": delivery_for(db_ns, t0["id"]).id,
            "enqueue_eligible": UUID(r[3]["id"]),
            "future_dated": UUID(r[4]["id"]),
            "absent_mismatch": UUID(absent["id"]),
            "later": UUID(future["id"]),
            "filing": filing_row.id,
            "exhausted": outboxes[3],
        }
        return db_ns, clock, base, rows


def delivery_exists(db_ns, reminder_id):
    with db_ns.runtime() as db:
        return (
            db.scalar(
                select(func.count())
                .select_from(NotificationDelivery)
                .where(NotificationDelivery.reminder_id == UUID(reminder_id))
            )
            > 0
        )


def ids(db_ns, statement):
    with db_ns.runtime() as db:
        return [row[0] for row in db.execute(statement)]


def worker_reminders(db_ns, limit):
    with db_ns.runtime() as db:
        return [row.id for row in reminder_worker.candidates(db, limit)]


def worker_notifications(db_ns, limit):
    with db_ns.runtime() as db:
        return [row.id for row in notification_worker.candidates(db, limit)]


def worker_filing(db_ns, limit):
    with db_ns.runtime() as db:
        return [row.id for row in filing_worker.candidates(db, limit)]


def worker_enqueue(db_ns, limit):
    """The reminders enqueue_pass would serve, observed inside a rolled-back transaction."""
    with db_ns.runtime() as db:
        transaction = db.begin()
        try:
            before = set(db.scalars(select(NotificationDelivery.reminder_id)))
            notification_worker.enqueue_pass(db, limit)
            db.flush()
            after = set(db.scalars(select(NotificationDelivery.reminder_id)))
            return sorted(after - before)
        finally:
            transaction.rollback()


def worker_claim(db_ns):
    """The outbox row jobs.claim would take (leased or dead-lettered), then rolled back."""
    with db_ns.runtime() as db:
        transaction = db.begin()
        try:
            before = {r.id: (r.state, r.attempts) for r in db.scalars(select(JobOutbox))}
            jobs.claim(db)
            db.flush()
            changed = [
                r.id
                for r in db.scalars(select(JobOutbox).execution_options(populate_existing=True))
                if (r.state, r.attempts) != before.get(r.id)
            ]
            return changed
        finally:
            transaction.rollback()


TIMES = [
    timedelta(0),
    timedelta(seconds=30),
    D - S,
    D + S,
    timedelta(minutes=10),
    timedelta(hours=4),
]


def test_12_refactored_workers_select_identical_ordered_ids(fresh_database, monkeypatch):
    db_ns, clock, base, rows = build_matrix(fresh_database, monkeypatch)
    compared, seen = 0, set()
    for offset in TIMES:
        now = clock.set(base + 10 * S + offset)
        for limit in (1, 2, 100):
            selected = [
                worker_reminders(db_ns, limit),
                worker_notifications(db_ns, limit),
                worker_filing(db_ns, limit),
                worker_enqueue(db_ns, limit),
            ]
            assert selected[0] == ids(db_ns, frozen_reminders(now, limit))
            assert selected[1] == ids(db_ns, frozen_notifications(now, limit))
            assert selected[2] == ids(db_ns, frozen_filing(now, limit))
            assert selected[3] == sorted(ids(db_ns, frozen_enqueue(limit)))
            seen.update(i for chosen in selected for i in chosen)
            compared += 4
        claimed = worker_claim(db_ns)
        assert claimed == ids(db_ns, frozen_job_claim(now))
        seen.update(claimed)
        compared += 1
    assert compared == len(TIMES) * 13
    # The comparisons were not vacuous: every branch's row was selected at some time ...
    for key in (
        "unknown",
        "in_flight",
        "resumed_paused",
        "enqueue_eligible",
        "future_dated",
        "absent_mismatch",
        "later",
        "filing",
    ):
        assert rows[key] in seen, key
    # ... and a parked paused delivery of an owner with disabled preferences never was.
    assert rows["parked_paused"] not in seen


def test_13_structure_shared_rules_take_only_a_cutoff_and_workers_import_no_guards():
    import inspect

    for name in (
        "job_pending",
        "job_lease_expired",
        "reminder_due",
        "notification_due",
        "notification_in_flight_expired",
        "filing_due",
        "filing_in_flight_expired",
    ):
        assert list(inspect.signature(getattr(eligible, name)).parameters) == ["t"]
    assert list(inspect.signature(eligible.notification_enqueue_eligible).parameters) == []
    for module in (jobs, reminder_worker, notification_worker, filing_worker):
        source = inspect.getsource(module)
        for forbidden in (
            "WORK_GRACE",
            "work_queries",
            "observe_work",
            "updated_at <=",
            "operations",
        ):
            assert forbidden not in source, (module.__name__, forbidden)
    guard_source = inspect.getsource(eligible)
    assert "updated_at" not in guard_source and "delivered_at" not in guard_source


def test_14_grace_never_delays_workers(fresh_database, monkeypatch):
    db_ns = fresh_database()
    base = identity.now_utc()
    clock = Clock(monkeypatch, base)
    with signed_in(db_ns) as scenario:
        save_policy(scenario, 0)
        at_t = schedule(scenario, create_task(scenario), base + 2 * S)
        before_t = schedule(scenario, create_task(scenario), base + S)
        t = clock.set(base + 2 * S)
        assert observe(db_ns, t)["reminders"] == "none_observed"
        for grace in (operations.WORK_GRACE, timedelta(minutes=10)):
            monkeypatch.setattr(operations, "WORK_GRACE", grace)
            assert {str(i) for i in worker_reminders(db_ns, 100)} == {
                at_t["id"],
                before_t["id"],
            }
        result = reminder_worker.run_once(db_ns.runtime)
        assert result["delivered"] == 2
        job = approved_job(scenario)
        set_outbox(db_ns, job, available_at=t)
        assert observe(db_ns, t)["approved_jobs"] == "none_observed"
        with db_ns.runtime.begin() as db:
            lease = jobs.claim(db)
        assert lease is not None and lease.delivery_id == job


def test_15_shared_rules_at_t_select_exactly_what_each_worker_selects_at_t(
    fresh_database, monkeypatch
):
    db_ns, clock, base, _ = build_matrix(fresh_database, monkeypatch)
    for offset in TIMES:
        t = clock.set(base + 10 * S + offset)
        rule_reminders = ids(
            db_ns,
            select(TaskReminder.id)
            .outerjoin(ReminderPreferences, eligible.preferences_on_reminder())
            .where(eligible.reminder_due(t)),
        )
        assert set(rule_reminders) == set(worker_reminders(db_ns, 100))
        rule_notifications = ids(
            db_ns,
            select(NotificationDelivery.id)
            .outerjoin(ReminderPreferences, eligible.preferences_on_delivery())
            .where(or_(eligible.notification_due(t), eligible.notification_in_flight_expired(t))),
        )
        assert set(rule_notifications) == set(worker_notifications(db_ns, 100))
        rule_enqueue = ids(
            db_ns,
            select(TaskReminder.id)
            .outerjoin(NotificationDelivery, eligible.enqueue_on())
            .where(eligible.notification_enqueue_eligible()),
        )
        assert sorted(rule_enqueue) == worker_enqueue(db_ns, 100)
        rule_jobs = ids(
            db_ns,
            select(JobOutbox.id).where(or_(eligible.job_pending(t), eligible.job_lease_expired(t))),
        )
        assert set(worker_claim(db_ns)) <= set(rule_jobs)
    # Observer cutoff G: everything the observer reports was selectable by the worker G ago.
    assert G == operations.WORK_GRACE
