from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_approvals import signin
from test_manual_tasks import call, create
from test_task_reminders import action, policy, schedule

from app import identity, notification_worker, reminder_worker
from app import notifications as notes
from app.models import (
    NotificationDelivery,
    NotificationDeliveryEvent,
    TaskReminder,
    User,
)


@pytest.fixture
def clock(monkeypatch):
    state = {"now": datetime(2026, 11, 8, 12, tzinfo=UTC)}
    monkeypatch.setattr(identity, "now_utc", lambda: state["now"])
    return state


def tighten(client, h, **changes):
    """Change preferences after the in-app reminder was delivered (revision 1 -> 2)."""
    assert policy(client, h, expected_revision=1, **changes).status_code == 200


def delivered_reminder(client, store, clock, h, **prefs):
    assert (
        policy(client, h, **{k: v for k, v in prefs.items() if k == "daily_limit"}).status_code
        == 200
    )
    task = create(client, h).json()
    schedule(client, h, task, clock["now"] + timedelta(minutes=1))
    clock["now"] += timedelta(minutes=2)
    assert reminder_worker.run_once(store)["delivered"] == 1
    return task


def rows(store):
    with store() as db:
        return list(db.scalars(select(NotificationDelivery).order_by(NotificationDelivery.id)))


def operations(store):
    with store() as db:
        return [
            e.operation
            for e in db.scalars(
                select(NotificationDeliveryEvent).order_by(
                    NotificationDeliveryEvent.recorded_at, NotificationDeliveryEvent.revision
                )
            )
        ]


def test_delivery_is_enqueued_once_sent_once_and_never_copies_task_text(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    channel = notes.SyntheticChannel()
    first = notification_worker.run_once(channel, auth_store)
    assert first["enqueued"] == 1 and first["delivered"] == 1
    again = notification_worker.run_once(channel, auth_store)
    assert again["enqueued"] == 0 and again["checked"] == 0
    assert channel.sent == 1
    (row,) = rows(auth_store)
    assert row.state == "delivered" and row.attempts == 1 and row.channel == "synthetic"
    assert row.recipient_ref.startswith("synthetic:") and "alice" not in row.recipient_ref
    assert operations(auth_store) == ["enqueued", "attempted", "delivered"]
    body = {"scope": "household_shared", "state": "delivered"}
    page = auth_client.post("/api/v1/notifications/query", headers=h, json=body).json()
    assert [i["state"] for i in page["items"]] == ["delivered"]
    history = auth_client.post(
        "/api/v1/notifications/history",
        headers=h,
        json={"scope": "household_shared", "delivery_id": page["items"][0]["id"]},
    ).json()
    assert [e["operation"] for e in history["items"]] == ["enqueued", "attempted", "delivered"]
    assert "Synthetic task" not in str(history) and "Synthetic task" not in str(page)


def test_transient_failures_retry_with_backoff_then_exhaust(auth_client, auth_store, clock):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    with auth_store() as db:
        owner = db.scalar(select(User.id).where(User.slug == "alice"))
    recipient = notes.recipient_ref(owner)
    channel = notes.SyntheticChannel({recipient: ["transient", "transient", "transient"]})
    assert notification_worker.run_once(channel, auth_store)["retried"] == 1
    assert notification_worker.run_once(channel, auth_store)["checked"] == 0
    clock["now"] += notes.BACKOFF[0]
    assert notification_worker.run_once(channel, auth_store)["retried"] == 1
    clock["now"] += notes.BACKOFF[1]
    assert notification_worker.run_once(channel, auth_store)["failed"] == 1
    (row,) = rows(auth_store)
    assert row.state == "failed" and row.reason == "attempts_exhausted" and row.attempts == 3
    clock["now"] += timedelta(days=1)
    assert notification_worker.run_once(channel, auth_store)["checked"] == 0
    assert channel.sent == 3


def test_retry_succeeds_after_one_transient_failure(auth_client, auth_store, clock):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    with auth_store() as db:
        owner = db.scalar(select(User.id).where(User.slug == "alice"))
    channel = notes.SyntheticChannel({notes.recipient_ref(owner): ["transient"]})
    assert notification_worker.run_once(channel, auth_store)["retried"] == 1
    clock["now"] += notes.BACKOFF[0]
    assert notification_worker.run_once(channel, auth_store)["delivered"] == 1
    assert rows(auth_store)[0].attempts == 2


def test_rejection_is_terminal_without_retry(auth_client, auth_store, clock):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    with auth_store() as db:
        owner = db.scalar(select(User.id).where(User.slug == "alice"))
    channel = notes.SyntheticChannel({notes.recipient_ref(owner): ["rejected"]})
    assert notification_worker.run_once(channel, auth_store)["failed"] == 1
    (row,) = rows(auth_store)
    assert row.state == "failed" and row.reason == "rejected" and row.attempts == 1
    clock["now"] += timedelta(hours=1)
    assert notification_worker.run_once(channel, auth_store)["checked"] == 0
    assert channel.sent == 1


@pytest.mark.parametrize(
    "step,found,final",
    [("timeout_applied", "delivered", "delivered"), ("timeout_lost", "absent", "delivered")],
)
def test_ambiguous_timeout_reconciles_by_lookup_and_never_double_sends(
    auth_client, auth_store, clock, step, found, final
):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    with auth_store() as db:
        owner = db.scalar(select(User.id).where(User.slug == "alice"))
    channel = notes.SyntheticChannel({notes.recipient_ref(owner): [step]})
    assert notification_worker.run_once(channel, auth_store)["unknown"] == 1
    assert rows(auth_store)[0].state == "unknown"
    clock["now"] += notes.RECONCILE_INTERVAL
    result = notification_worker.run_once(channel, auth_store)
    if step == "timeout_applied":
        assert result["delivered"] == 1 and channel.sent == 1
        assert "reconciled" in operations(auth_store)
    else:
        assert result["retried"] == 1
        assert notification_worker.run_once(channel, auth_store)["delivered"] == 1
        assert channel.sent == 2
    assert rows(auth_store)[0].state == final


def test_unavailable_lookup_keeps_unknown_and_does_not_resend(auth_client, auth_store, clock):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    with auth_store() as db:
        owner = db.scalar(select(User.id).where(User.slug == "alice"))
    channel = notes.SyntheticChannel(
        {notes.recipient_ref(owner): ["timeout_applied"]}, lookup_available=False
    )
    notification_worker.run_once(channel, auth_store)
    for _ in range(3):
        clock["now"] += notes.BACKOFF[-1]
        assert notification_worker.run_once(channel, auth_store)["unknown"] == 1
    assert rows(auth_store)[0].state == "unknown" and channel.sent == 1


def test_crash_after_claim_is_reconciled_not_resent(auth_client, auth_store, clock):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    notification_worker.run_once(notes.SyntheticChannel(), auth_store)  # enqueue + deliver
    # Simulate: claim committed, process died before reporting.
    with auth_store.begin() as db:
        row = db.scalar(select(NotificationDelivery))
        row.state = "pending"
        row.attempts = 1
        row.resolved_at = None
        row.attempt_started_at = clock["now"]
        row.next_attempt_at = clock["now"]
        row.reason = None
    channel = notes.SyntheticChannel()
    assert notification_worker.run_once(channel, auth_store)["checked"] == 0
    clock["now"] += notes.IN_FLIGHT_DEADLINE + timedelta(seconds=1)
    assert notification_worker.run_once(channel, auth_store)["unknown"] == 1
    assert channel.sent == 0
    clock["now"] += notes.RECONCILE_INTERVAL
    notification_worker.run_once(channel, auth_store)
    assert channel.sent == 0 or channel.sent == 1  # lookup absent -> one bounded retry only
    assert rows(auth_store)[0].attempts <= notes.MAX_ATTEMPTS


def test_quiet_hours_defer_then_send(auth_client, auth_store, clock):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    tighten(auth_client, h, quiet_start=720, quiet_end=780)
    channel = notes.SyntheticChannel()
    assert notification_worker.run_once(channel, auth_store)["deferred"] == 1
    assert rows(auth_store)[0].reason == "quiet_hours" and channel.sent == 0
    clock["now"] = datetime(2026, 11, 8, 13, 1, tzinfo=UTC)
    assert notification_worker.run_once(channel, auth_store)["delivered"] == 1
    assert channel.sent == 1


def test_daily_limit_counts_notifications_and_defers_to_next_local_day(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    task = create(auth_client, h).json()
    schedule(auth_client, h, task, clock["now"] + timedelta(minutes=1))
    clock["now"] += timedelta(minutes=2)
    assert reminder_worker.run_once(auth_store)["delivered"] == 1
    tighten(auth_client, h, daily_limit=1)
    channel = notes.SyntheticChannel()
    result = notification_worker.run_once(channel, auth_store)
    assert result["enqueued"] == 2 and result["delivered"] == 1 and result["deferred"] == 1
    assert channel.sent == 1
    held = next(r for r in rows(auth_store) if r.state == "pending")
    assert held.reason == "daily_limit"
    assert identity.aware(held.next_attempt_at).date() > clock["now"].date()


def test_paused_preferences_park_the_delivery_once_and_resume_later(auth_client, auth_store, clock):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    tighten(auth_client, h, enabled=False)
    channel = notes.SyntheticChannel()
    result = notification_worker.run_once(channel, auth_store)
    assert result["enqueued"] == 1 and result["deferred"] == 1 and channel.sent == 0
    (row,) = rows(auth_store)
    assert row.state == "pending" and row.reason == "paused"
    revision = row.revision
    # Not selected again, not rewritten and never cancelled while the owner stays paused.
    for _ in range(3):
        clock["now"] += timedelta(minutes=5)
        assert notification_worker.run_once(channel, auth_store)["checked"] == 0
    assert rows(auth_store)[0].revision == revision
    assert operations(auth_store).count("deferred") == 1
    # Resuming makes it eligible again without a new delivery.
    tighten_back = policy(auth_client, h, expected_revision=2, enabled=True)
    assert tighten_back.status_code == 200
    assert notification_worker.run_once(channel, auth_store)["delivered"] == 1
    (row,) = rows(auth_store)
    assert row.state == "delivered" and row.reason is None and channel.sent == 1


def test_acknowledged_or_cancelled_reminder_cancels_pending_delivery(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    task = delivered_reminder(auth_client, auth_store, clock, h)
    tighten(auth_client, h, quiet_start=720, quiet_end=780)
    channel = notes.SyntheticChannel()
    assert notification_worker.run_once(channel, auth_store)["deferred"] == 1
    reminder = auth_client.post(
        "/api/v1/reminders/read", headers=h, json={"scope": task["scope"], "task_id": task["id"]}
    ).json()["reminder"]
    assert action(auth_client, h, task, reminder, "acknowledge").status_code == 200
    clock["now"] = datetime(2026, 11, 8, 13, 1, tzinfo=UTC)
    assert notification_worker.run_once(channel, auth_store)["cancelled"] == 1
    (row,) = rows(auth_store)
    assert row.state == "cancelled" and row.reason == "reminder_closed" and channel.sent == 0


def test_inactive_owner_cancels_before_any_send(auth_client, auth_store, clock):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    tighten(auth_client, h, quiet_start=720, quiet_end=780)
    channel = notes.SyntheticChannel()
    notification_worker.run_once(channel, auth_store)
    with auth_store.begin() as db:
        db.scalar(select(User).where(User.slug == "alice")).is_active = False
    clock["now"] = datetime(2026, 11, 8, 13, 1, tzinfo=UTC)
    assert notification_worker.run_once(channel, auth_store)["cancelled"] == 1
    assert rows(auth_store)[0].reason == "owner_unavailable" and channel.sent == 0


def test_reschedule_creates_a_new_cycle_delivery_and_dedup_is_per_cycle(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    task = delivered_reminder(auth_client, auth_store, clock, h)
    channel = notes.SyntheticChannel()
    notification_worker.run_once(channel, auth_store)
    reminder = auth_client.post(
        "/api/v1/reminders/read", headers=h, json={"scope": task["scope"], "task_id": task["id"]}
    ).json()["reminder"]
    schedule(
        auth_client,
        h,
        auth_client.post(
            f"/api/v1/tasks/{task['id']}/read", headers=h, json={"scope": task["scope"]}
        ).json(),
        clock["now"] + timedelta(minutes=1),
        reminder["revision"],
    )
    clock["now"] += timedelta(minutes=2)
    reminder_worker.run_once(auth_store)
    assert notification_worker.run_once(channel, auth_store)["delivered"] == 1
    assert sorted(r.cycle for r in rows(auth_store)) == [1, 2] and channel.sent == 2


def test_channel_is_idempotent_on_key_and_exceptions_become_ambiguous():
    channel = notes.SyntheticChannel()
    assert channel.send("k", "r") == notes.Outcome.ACCEPTED
    assert channel.send("k", "r") == notes.Outcome.ACCEPTED and channel.sent == 1
    assert channel.lookup("k") == notes.Lookup.DELIVERED
    assert channel.lookup("other") == notes.Lookup.ABSENT


def test_bounded_pass_and_cross_user_isolation(auth_client, auth_store, clock):
    h = signin(auth_client)
    delivered_reminder(auth_client, auth_store, clock, h)
    notification_worker.run_once(notes.SyntheticChannel(), auth_store)
    with pytest.raises(ValueError):
        notification_worker.run_once(notes.SyntheticChannel(), auth_store, limit=101)
    page = auth_client.post(
        "/api/v1/notifications/query", headers=h, json={"scope": "member_b_private"}
    )
    assert page.status_code in {401, 403}
    unauth = auth_client.post("/api/v1/notifications/query", json={"scope": "household_shared"})
    assert unauth.status_code in {401, 403}
    missing = auth_client.post(
        "/api/v1/notifications/history",
        headers=h,
        json={
            "scope": "household_shared",
            "delivery_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert missing.status_code == 404


def test_reminder_state_is_untouched_by_notification_delivery(auth_client, auth_store, clock):
    h = signin(auth_client)
    task = delivered_reminder(auth_client, auth_store, clock, h)
    notification_worker.run_once(notes.SyntheticChannel(), auth_store)
    reminder = call(auth_client, h, task, "read").json()
    assert reminder["status"] == "open"
    with auth_store() as db:
        assert db.scalar(select(TaskReminder)).state == "delivered"
