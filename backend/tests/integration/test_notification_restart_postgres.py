"""Gate 5 process-restart evidence: the notification worker recovers after its process is gone.

Independent of the filing evidence: this is the notification worker path (`notification_worker.
process`) running as a separate operating-system process against a durable synthetic delivery
ledger. The ledger records every send call and every effect, so a blind resend would be visible even
though the channel is idempotent on the delivery key. Processes are killed with SIGKILL at
controlled points; distinct fresh processes recover from the same PostgreSQL rows and ledger.

This is process-restart evidence for a synthetic channel only: no real provider, device push or
recipient identity is involved.
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from restart_support import FileChannel, Ledger, Worker, run_to_completion  # noqa: F401
from sqlalchemy import select, text
from test_notifications_postgres import enqueued
from test_task_reminders import create, policy, schedule
from test_task_reminders_postgres import only_pass

from app import identity, notification_worker
from app import notifications as notes
from app.models import NotificationDelivery, NotificationDeliveryEvent

pytestmark = pytest.mark.integration

FULL_HISTORY = ["enqueued", "attempted", "unknown", "reconciled", "attempted", "delivered"]


def edit(admin, delivery_id, **columns):
    """Test-only backdating of timestamps; the seal trigger is re-enabled immediately."""
    with admin.begin() as db:
        db.execute(
            text("ALTER TABLE notification_deliveries DISABLE TRIGGER butler_notification_guard")
        )
        row = db.get(NotificationDelivery, delivery_id)
        for name, value in columns.items():
            setattr(row, name, value)
        db.flush()
        db.execute(
            text("ALTER TABLE notification_deliveries ENABLE TRIGGER butler_notification_guard")
        )


def age(admin, row):
    edit(
        admin,
        row.id,
        attempt_started_at=identity.now_utc() - notes.IN_FLIGHT_DEADLINE - timedelta(seconds=1),
    )


def due(admin, row):
    edit(admin, row.id, next_attempt_at=identity.now_utc())


def real_time(monkeypatch, admin, row, clock):
    """Return to the real clock (child processes use it) and make the delivery claimable now."""
    monkeypatch.setattr(identity, "now_utc", clock)
    past = clock() - timedelta(minutes=1)  # the test clock ran ahead of the children's real clock
    edit(admin, row.id, next_attempt_at=past, updated_at=past)


def another_delivery(scenario, runtime_engine, monkeypatch, maker, admin, clock):
    """A second delivered reminder cycle for the same owner, enqueued and claimable now."""
    client, headers = scenario[0], scenario[1]
    # The reminder worker has its own daily budget: widen it just long enough to deliver a second
    # reminder, then restore it so the notification budget is what the test exercises.
    assert policy(client, headers, expected_revision=1, daily_limit=2).status_code == 200
    task = create(client, headers, title="Synthetic reminder " + uuid4().hex).json()
    when = clock() + timedelta(seconds=1)
    scheduled = schedule(client, headers, task, when)
    assert scheduled.status_code == 200, scheduled.json()
    row = scheduled.json()
    monkeypatch.setattr(identity, "now_utc", lambda: when + timedelta(seconds=1))
    assert only_pass(runtime_engine, row) == "delivered"
    with maker.begin() as db:
        assert notification_worker.enqueue_pass(db, 100) >= 1
    with maker.begin() as db:
        delivery = db.execute(
            select(
                NotificationDelivery.id,
                NotificationDelivery.owner_id,
                NotificationDelivery.scope_key,
            ).where(NotificationDelivery.reminder_id == UUID(row["id"]))
        ).one()
    assert policy(client, headers, expected_revision=2, daily_limit=1).status_code == 200
    real_time(monkeypatch, admin, delivery, clock)
    return delivery


def snap(admin, row):
    with admin() as db:
        state = db.get(NotificationDelivery, row.id)
        events = db.scalars(
            select(NotificationDeliveryEvent)
            .where(NotificationDeliveryEvent.delivery_id == row.id)
            .order_by(NotificationDeliveryEvent.revision)
        ).all()
        return {
            "state": state.state,
            "revision": state.revision,
            "attempts": state.attempts,
            "in_flight": state.attempt_started_at is not None,
            "reason": state.reason,
            "next_attempt_at": state.next_attempt_at,
            "resolved_at": state.resolved_at,
            "operations": [e.operation for e in events],
            "event_revisions": [e.revision for e in events],
        }


def retire(admin, ids):
    """Leave no claimable rows behind: the database is shared with other tests' bounded passes."""
    with admin.begin() as db:
        db.execute(
            text("ALTER TABLE notification_deliveries DISABLE TRIGGER butler_notification_guard")
        )
        for identifier in ids:
            state = db.get(NotificationDelivery, identifier)
            if state is not None and state.state in {"pending", "unknown"}:
                state.state, state.reason = "cancelled", "owner_unavailable"
                state.attempt_started_at = state.next_attempt_at = None
                state.resolved_at = state.updated_at
        db.flush()
        db.execute(
            text("ALTER TABLE notification_deliveries ENABLE TRIGGER butler_notification_guard")
        )


@pytest.fixture
def procs():
    started = []
    yield started
    for worker in started:  # reliable cleanup, including after a failed assertion
        worker.stop()


@pytest.fixture
def leftovers():
    rows = []  # (admin engine, delivery id)
    yield rows
    for admin, identifier in rows:
        retire(admin, [identifier])


@pytest.fixture
def env(scenario, runtime_engine, monkeypatch, tmp_path, leftovers, procs):
    clock = identity.now_utc
    maker, admin, _, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)
    leftovers.append((admin, delivery.id))
    real_time(monkeypatch, admin, delivery, clock)
    ledger = Ledger(tmp_path / "channel")
    url = runtime_engine.url.render_as_string(hide_password=False)

    class Env:
        pass

    e = Env()
    e.admin, e.row, e.ledger, e.url, e.maker = admin, delivery, ledger, url, maker
    e.key, e.scenario, e.runtime_engine, e.monkeypatch = (
        str(delivery.id),
        scenario,
        runtime_engine,
        monkeypatch,
    )

    def spawn(crash_at=None, row=delivery):
        worker = Worker("notification", url, ledger, row.id, crash_at).start()
        procs.append(worker)
        return worker

    e.spawn = spawn
    e.fresh = lambda row=delivery: run_to_completion("notification", url, ledger, row.id)
    return e


def crash_at(env, point):
    worker = env.spawn(point)
    assert worker.wait_reached() == point
    at_point = snap(env.admin, env.row)
    effects_at_point = list(env.ledger.effects())
    worker.kill()
    assert snap(env.admin, env.row) == at_point  # durable state is what the dead process left
    assert env.ledger.effects() == effects_at_point
    return at_point, worker


def test_termination_before_delivery_recovers_and_delivers_once(env):
    at_death, worker = crash_at(env, "before_effect")
    assert at_death["state"] == "pending" and at_death["in_flight"] and at_death["attempts"] == 1
    assert env.ledger.objects() == [] and len(env.ledger.calls()) == 1

    assert env.fresh() == "skipped"  # inside the in-flight deadline the claim is respected
    assert len(env.ledger.calls()) == 1

    age(env.admin, env.row)
    assert env.fresh() == "unknown"  # reaped to unknown, never resent blindly
    assert len(env.ledger.calls()) == 1

    due(env.admin, env.row)
    assert env.fresh() == "retried"  # conclusive "absent" lookup is what permits a retry
    assert len(env.ledger.calls()) == 1 and env.ledger.lookups() == [env.key]

    assert env.fresh() == "delivered"
    final = snap(env.admin, env.row)
    assert final["state"] == "delivered" and final["attempts"] == 2
    assert final["operations"] == FULL_HISTORY and final["event_revisions"] == list(range(1, 7))
    [effect] = env.ledger.objects()
    assert effect["key"] == env.key
    assert len(env.ledger.effects()) == 1 and len(env.ledger.calls()) == 2
    assert worker.proc.returncode == -9


def test_termination_after_delivery_reconciles_without_resending(env):
    at_death, _ = crash_at(env, "after_effect")
    assert at_death["state"] == "pending" and at_death["in_flight"]
    [effect] = env.ledger.objects()  # the delivery effect is durable; the database does not know
    assert effect["key"] == env.key and len(env.ledger.calls()) == 1

    assert env.fresh() == "skipped"
    age(env.admin, env.row)
    assert env.fresh() == "unknown"  # not "failed": the notification may have been delivered
    due(env.admin, env.row)
    assert env.fresh() == "delivered"  # reconciled from the persistent ledger
    final = snap(env.admin, env.row)
    assert final["state"] == "delivered" and final["attempts"] == 1
    assert final["operations"] == ["enqueued", "attempted", "unknown", "reconciled"]
    assert len(env.ledger.calls()) == 1 and len(env.ledger.effects()) == 1
    assert env.ledger.objects() == [effect]


def test_an_inconclusive_lookup_keeps_delivery_unknown_without_resending(env):
    crash_at(env, "after_effect")
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    env.ledger.block_lookup()
    for _ in range(2):
        due(env.admin, env.row)
        assert env.fresh() == "unknown"
        state = snap(env.admin, env.row)
        assert state["state"] == "unknown" and state["reason"] == "ambiguous_outcome"
        assert state["attempts"] == 1 and state["resolved_at"] is None
    assert len(env.ledger.calls()) == 1 and len(env.ledger.effects()) == 1
    env.ledger.unblock_lookup()
    due(env.admin, env.row)
    assert env.fresh() == "delivered"
    assert len(env.ledger.calls()) == 1 and snap(env.admin, env.row)["attempts"] == 1


def test_an_inconclusive_lookup_never_triggers_a_resend_even_if_nothing_was_sent(env):
    crash_at(env, "before_effect")
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    env.ledger.block_lookup()
    due(env.admin, env.row)
    assert env.fresh() == "unknown"
    assert len(env.ledger.calls()) == 1 and env.ledger.objects() == []
    env.ledger.unblock_lookup()
    due(env.admin, env.row)
    assert env.fresh() == "retried"
    assert env.fresh() == "delivered"
    assert len(env.ledger.calls()) == 2 and len(env.ledger.effects()) == 1


def test_a_competing_recovery_worker_cannot_advance_a_claim_it_does_not_hold(env):
    crash_at(env, "before_effect")
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    due(env.admin, env.row)
    assert env.fresh() == "retried"
    holder = env.spawn("before_effect")
    assert holder.wait_reached() == "before_effect"
    held = snap(env.admin, env.row)
    assert held["state"] == "pending" and held["in_flight"] and held["attempts"] == 2
    calls_before = len(env.ledger.calls())
    assert env.fresh() == "skipped"  # the competitor loses without touching state or channel
    assert snap(env.admin, env.row) == held
    assert len(env.ledger.calls()) == calls_before and env.ledger.effects() == []
    holder.release()
    assert holder.finish() == "delivered"
    assert len(env.ledger.effects()) == 1


def test_simultaneous_fresh_workers_deliver_once(env):
    first, second = env.spawn("start"), env.spawn("start")
    assert (first.wait_reached(), second.wait_reached()) == ("start", "start")
    first.release()  # both are alive and past candidate selection before either may claim
    second.release()
    assert sorted([first.finish(), second.finish()]) == ["delivered", "skipped"]
    assert len(env.ledger.effects()) == 1 and len(env.ledger.calls()) == 1
    assert snap(env.admin, env.row)["operations"] == ["enqueued", "attempted", "delivered"]


@pytest.mark.parametrize("stall_at", ["before_effect", "after_effect"])
def test_a_stalled_worker_resuming_after_recovery_cannot_overwrite_the_newer_result(env, stall_at):
    stalled = env.spawn(stall_at)
    assert stalled.wait_reached() == stall_at
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    due(env.admin, env.row)
    if stall_at == "after_effect":
        assert env.fresh() == "delivered"
    else:
        assert env.fresh() == "retried"
        assert env.fresh() == "delivered"
    newer = snap(env.admin, env.row)
    effects = list(env.ledger.effects())
    assert newer["state"] == "delivered" and len(effects) == 1
    stalled.release()
    assert stalled.finish() == "skipped"  # its fence is obsolete: no write to row or history
    assert snap(env.admin, env.row) == newer
    assert env.ledger.effects() == effects and len(env.ledger.objects()) == 1


def test_a_delivered_cycle_is_never_enqueued_or_sent_again(env):
    assert env.fresh() == "delivered"
    effects = list(env.ledger.effects())
    with env.maker.begin() as db:  # deduplication across passes and processes
        assert notification_worker.enqueue_pass(db, 100) == 0
    assert env.fresh() == "skipped"
    assert env.ledger.effects() == effects and len(env.ledger.calls()) == 1


def test_a_reconciled_delivery_counts_against_the_daily_budget_in_a_fresh_process(
    scenario, runtime_engine, monkeypatch, tmp_path, leftovers, procs
):
    clock = identity.now_utc
    maker, admin, _, _, first = enqueued(runtime_engine, scenario, monkeypatch, limit=1)
    leftovers.append((admin, first.id))
    real_time(monkeypatch, admin, first, clock)
    ledger = Ledger(tmp_path / "channel")
    url = runtime_engine.url.render_as_string(hide_password=False)
    worker = Worker("notification", url, ledger, first.id, "after_effect").start()
    procs.append(worker)
    worker.wait_reached()
    worker.kill()
    age(admin, first)
    assert run_to_completion("notification", url, ledger, first.id) == "unknown"
    due(admin, first)
    assert run_to_completion("notification", url, ledger, first.id) == "delivered"
    # A second delivery for the same owner on the same day meets the budget the recovery consumed.
    second = another_delivery(scenario, runtime_engine, monkeypatch, maker, admin, clock)
    leftovers.append((admin, second.id))
    assert run_to_completion("notification", url, ledger, second.id) == "deferred"
    state = snap(admin, second)
    assert state["state"] == "pending" and state["reason"] == "daily_limit"
    assert len(ledger.effects()) == 1  # only the first delivery ever produced an effect


def test_recovery_after_a_crash_still_honours_quiet_hours(env):
    crash_at(env, "before_effect")
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    due(env.admin, env.row)
    assert env.fresh() == "retried"
    # Quiet hours now cover the present moment (UTC): the retry must be deferred, not sent.
    minute = identity.now_utc().hour * 60 + identity.now_utc().minute
    client, headers = env.scenario[0], env.scenario[1]
    saved = policy(
        client,
        headers,
        expected_revision=1,
        quiet_start=(minute - 60) % 1440,
        quiet_end=(minute + 60) % 1440,
    )
    assert saved.status_code == 200, saved.json()
    assert env.fresh() == "deferred"
    state = snap(env.admin, env.row)
    assert state["state"] == "pending" and state["reason"] == "quiet_hours"
    assert len(env.ledger.calls()) == 1 and env.ledger.effects() == []


def test_a_stalled_worker_cannot_finish_a_newer_in_flight_claim(env):
    stalled = env.spawn("before_effect")  # attempt 1: claimed, no effect, then stalls
    assert stalled.wait_reached() == "before_effect"
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    due(env.admin, env.row)
    assert env.fresh() == "retried"
    newer = env.spawn("before_effect")  # attempt 2 holds the current claim
    assert newer.wait_reached() == "before_effect"
    held = snap(env.admin, env.row)
    assert held["state"] == "pending" and held["in_flight"] and held["attempts"] == 2
    # The stale worker resumes and performs its (idempotent) effect, but its fence is obsolete:
    # it must not complete, fail or alter the claim that attempt 2 holds.
    stalled.release()
    assert stalled.finish() == "skipped"
    assert snap(env.admin, env.row) == held
    newer.release()
    assert newer.finish() == "delivered"
    assert len(env.ledger.effects()) == 1
    assert snap(env.admin, env.row)["state"] == "delivered"


def test_a_crashing_lookup_keeps_the_outcome_unknown_and_never_resends(env):
    crash_at(env, "after_effect")
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    env.ledger.break_lookup()  # the lookup raises inside the worker process
    due(env.admin, env.row)
    assert env.fresh() == "unknown"
    state = snap(env.admin, env.row)
    assert state["state"] == "unknown" and state["reason"] == "ambiguous_outcome"
    assert len(env.ledger.calls()) == 1 and len(env.ledger.effects()) == 1
    env.ledger.repair_lookup()
    due(env.admin, env.row)
    assert env.fresh() == "delivered"
    assert len(env.ledger.calls()) == 1 and len(env.ledger.effects()) == 1


def test_recovery_re_checks_the_owner_and_never_applies_for_an_unavailable_owner(env):
    crash_at(env, "before_effect")
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    due(env.admin, env.row)
    assert env.fresh() == "retried"
    owner = env.row.owner_id
    with env.admin.begin() as db:
        db.execute(text("UPDATE users SET is_active=false WHERE id=:i"), {"i": owner})
    try:
        assert env.fresh() == "cancelled"
    finally:
        with env.admin.begin() as db:
            db.execute(text("UPDATE users SET is_active=true WHERE id=:i"), {"i": owner})
    assert snap(env.admin, env.row)["state"] == "cancelled"
    assert len(env.ledger.calls()) == 1 and env.ledger.effects() == []
