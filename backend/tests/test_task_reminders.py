from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_manual_tasks import call, create

from app import identity, reminder_worker
from app import task_reminders as reminders
from app.manage import set_scope
from app.models import ManualTask, ReminderPreferences, TaskReminder, TaskReminderEvent, User


def post(client, h, path, body):
    return client.post("/api/v1/reminders/" + path, headers=h, json=body)


def schedule(client, h, task, when, revision=None):
    return post(
        client,
        h,
        "schedule",
        {
            "scope": task["scope"],
            "task_id": task["id"],
            "expected_task_revision": task["revision"],
            "expected_revision": revision,
            "scheduled_at": when.isoformat(),
        },
    )


def action(client, h, task, row, value):
    return post(
        client,
        h,
        "action",
        {
            "scope": task["scope"],
            "task_id": task["id"],
            "expected_revision": row["revision"],
            "action": value,
        },
    )


def policy(client, h, **changes):
    body = {
        "scope": "household_shared",
        "expected_revision": 0,
        "enabled": True,
        "timezone": "UTC",
        "quiet_start": 0,
        "quiet_end": 0,
        "daily_limit": 5,
    }
    body.update(changes)
    return post(client, h, "preferences/save", body)


def inbox(client, h, **changes):
    return post(client, h, "query", dict(scope="household_shared", **changes))


def test_lifecycle_private_delivery_acknowledge_snooze_cancel_and_history(
    auth_client, auth_store, monkeypatch
):
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    h = signin(auth_client)
    task = create(auth_client, h).json()
    assert policy(auth_client, h).status_code == 200
    response = schedule(auth_client, h, task, now + timedelta(minutes=1))
    assert response.status_code == 200
    row = response.json()
    assert row["state"] == "scheduled" and row["cycle"] == 1
    assert reminder_worker.run_once(auth_store)["checked"] == 0
    now += timedelta(minutes=2)
    assert reminder_worker.run_once(auth_store)["delivered"] == 1
    assert reminder_worker.run_once(auth_store)["checked"] == 0
    delivered = inbox(auth_client, h).json()["items"][0]["reminder"]
    assert delivered["revision"] == 2 and delivered["delivered_at"]
    assert call(auth_client, h, task, "read").json()["status"] == "open"
    row = action(auth_client, h, task, delivered, "acknowledge").json()
    assert row["state"] == "acknowledged"
    assert action(auth_client, h, task, delivered, "cancel").status_code == 409
    row = schedule(auth_client, h, task, now + timedelta(hours=1), row["revision"]).json()
    assert row["cycle"] == 2 and row["delivered_at"] is None
    row = action(auth_client, h, task, row, "cancel").json()
    assert row["state"] == "cancelled"
    history = post(
        auth_client, h, "history", {"scope": task["scope"], "task_id": task["id"]}
    ).json()
    assert [r["operation"] for r in history["items"]] == [
        "scheduled",
        "delivered",
        "acknowledged",
        "rescheduled",
        "cancelled",
    ]
    assert history["items"][1]["actor_id"] is None
    assert all("Synthetic task" not in str(r["snapshot"]) for r in history["items"])


@pytest.mark.parametrize("close", ["done", "cancelled", "forget"])
def test_task_close_or_forget_cancels_in_same_transaction(
    auth_client, auth_store, monkeypatch, close
):
    now = identity.now_utc()
    h = signin(auth_client)
    task = create(auth_client, h).json()
    schedule(auth_client, h, task, now + timedelta(hours=1))
    response = (
        call(auth_client, h, task, "forget")
        if close == "forget"
        else call(auth_client, h, task, "transition", status=close)
    )
    assert response.status_code == 200
    with auth_store() as db:
        row = db.scalar(select(TaskReminder))
        assert row.state == "cancelled" and row.reason == (
            "task_forgotten" if close == "forget" else "task_closed"
        )
    items = inbox(auth_client, h, state="all").json()["items"]
    assert items[0]["reminder"]["state"] == "cancelled"
    if close == "forget":
        assert "title" not in items[0]["task"]


def test_task_details_follow_current_authority_without_moving_reminder(
    auth_client, auth_store, monkeypatch
):
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    h = signin(auth_client)
    policy(auth_client, h)
    task = create(auth_client, h).json()
    row = schedule(auth_client, h, task, now + timedelta(minutes=1)).json()
    task = call(
        auth_client,
        h,
        task,
        "correct",
        title="Synthetic revised task",
        due_at=(now + timedelta(days=2)).isoformat(),
    ).json()
    now += timedelta(minutes=2)
    assert reminder_worker.run_once(auth_store)["delivered"] == 1
    item = inbox(auth_client, h).json()["items"][0]
    assert (
        item["task"]["title"] == "Synthetic revised task"
        and item["reminder"]["scheduled_at"] == row["scheduled_at"]
    )
    assert item["reminder"]["task_revision"] == task["revision"]


def test_shared_reader_and_same_private_grant_cannot_inspect_or_schedule(auth_client, auth_store):
    h = signin(auth_client)
    task = create(auth_client, h).json()
    when = identity.now_utc() + timedelta(hours=1)
    schedule(auth_client, h, task, when)
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, bob, "household_shared", True)
    other = signin(auth_client, "bob")
    assert inbox(auth_client, other, state="all").json()["items"] == []
    for path in ["read", "history"]:
        assert (
            post(
                auth_client, other, path, {"scope": task["scope"], "task_id": task["id"]}
            ).status_code
            == 404
        )
    assert schedule(auth_client, other, task, when).status_code == 404


def test_quiet_deferral_policy_change_pause_and_delivery(auth_client, auth_store, monkeypatch):
    now = datetime(2026, 11, 8, 23, tzinfo=UTC)
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    h = signin(auth_client)
    task = create(auth_client, h).json()
    policy(auth_client, h, quiet_start=1320, quiet_end=480)
    schedule(auth_client, h, task, now + timedelta(minutes=1))
    now += timedelta(minutes=2)
    assert reminder_worker.run_once(auth_store)["deferred"] == 1
    row = inbox(auth_client, h, state="all").json()["items"][0]["reminder"]
    assert row["reason"] == "quiet_hours" and row["next_attempt_at"] == "2026-11-09T08:00:00+00:00"
    assert reminder_worker.run_once(auth_store)["checked"] == 0
    policy(auth_client, h, expected_revision=1, enabled=False)
    assert reminder_worker.run_once(auth_store)["checked"] == 0
    policy(auth_client, h, expected_revision=2)
    assert reminder_worker.run_once(auth_store)["delivered"] == 1


def test_daily_budget_survives_ack_and_snooze_and_resets_on_local_day(
    auth_client, auth_store, monkeypatch
):
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    h = signin(auth_client)
    policy(auth_client, h, daily_limit=1)
    tasks = [create(auth_client, h, title=f"Synthetic budget {i}").json() for i in range(2)]
    for task in tasks:
        schedule(auth_client, h, task, now + timedelta(minutes=1))
    now += timedelta(minutes=2)
    result = reminder_worker.run_once(auth_store)
    assert result["delivered"] == 1 and result["deferred"] == 1
    rows = inbox(auth_client, h, state="all").json()["items"]
    delivered = next(r for r in rows if r["reminder"]["state"] == "delivered")
    task = next(t for t in tasks if t["id"] == delivered["task"]["id"])
    row = action(auth_client, h, task, delivered["reminder"], "acknowledge").json()
    schedule(auth_client, h, task, now + timedelta(minutes=1), row["revision"])
    now += timedelta(minutes=2)
    assert reminder_worker.run_once(auth_store)["delivered"] == 0
    now = datetime(2026, 11, 9, 0, 1, tzinfo=UTC)
    assert reminder_worker.run_once(auth_store)["delivered"] == 1


@pytest.mark.parametrize(
    "instant,expected",
    [
        ("2026-03-29T00:59:30+00:00", "2026-03-29T01:00:00+00:00"),
        ("2026-10-25T01:15:00+00:00", "2026-10-25T01:30:00+00:00"),
    ],
)
def test_dst_uses_real_utc_minutes(instant, expected):
    policy = reminders.policy_document()
    policy.update(timezone="Europe/Paris", quiet_start=0, quiet_end=150)
    now = datetime.fromisoformat(instant)
    assert reminder_worker.is_quiet(now, policy)
    assert reminder_worker.next_allowed(now, policy).isoformat() == expected


@pytest.mark.parametrize("reason", ["inactive", "revoked", "closed"])
def test_worker_current_authority_refuses_pending_delivery(
    auth_client, auth_store, monkeypatch, reason
):
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    h = signin(auth_client)
    task = create(auth_client, h).json()
    policy(auth_client, h)
    schedule(auth_client, h, task, now + timedelta(minutes=1))
    with auth_store.begin() as db:
        user = db.get(User, UUID(task["owner_id"]))
        if reason == "inactive":
            user.is_active = False
        elif reason == "revoked":
            set_scope(db, user, "household_shared", False)
        else:
            db.get(ManualTask, UUID(task["id"])).status = "done"
            db.get(
                ManualTask, UUID(task["id"])
            ).completed_at = now  # Raw fixture bypasses API hook.
    now += timedelta(minutes=2)
    assert reminder_worker.run_once(auth_store)["cancelled"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"expected_task_revision": True},
        {"scheduled_at": "2026-11-08T12:00:00"},
        {"scope": "technical_admin"},
        {"owner_id": "arbitrary"},
    ],
)
def test_invalid_schedule_sanitized(auth_client, change):
    h = signin(auth_client)
    task = create(auth_client, h).json()
    body = {
        "scope": task["scope"],
        "task_id": task["id"],
        "expected_task_revision": 1,
        "scheduled_at": (identity.now_utc() + timedelta(hours=1)).isoformat(),
    }
    body.update(change)
    response = post(auth_client, h, "schedule", body)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}


@pytest.mark.parametrize(
    "change",
    [
        {"timezone": "No/Such_Zone"},
        {"daily_limit": 21},
        {"quiet_start": 1440},
        {"daily_limit": True},
        {"enabled": 1},
    ],
)
def test_invalid_policy(auth_client, change):
    h = signin(auth_client)
    assert policy(auth_client, h, **change).status_code == 422


def test_audit_failure_rolls_back_delivery_and_can_retry(
    auth_client, auth_store, auth_engine, monkeypatch
):
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    h = signin(auth_client)
    task = create(auth_client, h).json()
    policy(auth_client, h)
    schedule(auth_client, h, task, now + timedelta(minutes=1))
    now += timedelta(minutes=2)

    def fail(conn, cursor, statement, params, context, many):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic reminder audit failure")

    event.listen(auth_engine, "before_cursor_execute", fail)
    try:
        assert reminder_worker.run_once(auth_store)["failed"] == 1
    finally:
        event.remove(auth_engine, "before_cursor_execute", fail)
    with auth_store() as db:
        assert db.scalar(select(TaskReminder)).state == "scheduled"
        assert len(list(db.scalars(select(TaskReminderEvent)))) == 1
    assert reminder_worker.run_once(auth_store)["delivered"] == 1


def test_api_export_copy_ack_csrf_and_private_ownership(auth_client, auth_store):
    h = signin(auth_client, "bob")
    task = create(auth_client, h, scope="member_b_private").json()
    schedule(auth_client, h, task, identity.now_utc() + timedelta(hours=1))
    response = post(
        auth_client,
        h,
        "export",
        {"scope": "member_b_private", "state": "all", "acknowledge_copy_limits": True},
    )
    assert (
        response.status_code == 200
        and response.json()["managed_copy"] is False
        and len(response.json()["items"]) == 1
    )
    assert response.headers["Cache-Control"] == "no-store"
    assert (
        post(
            auth_client,
            h,
            "export",
            {"scope": "member_b_private", "acknowledge_copy_limits": False},
        ).status_code
        == 422
    )
    assert post(auth_client, {}, "query", {"scope": "member_b_private"}).status_code == 403
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "member_b_private", True)
    other = signin(auth_client)
    assert (
        post(auth_client, other, "query", {"scope": "member_b_private", "state": "all"}).json()[
            "items"
        ]
        == []
    )
    assert (
        post(
            auth_client, other, "read", {"scope": "member_b_private", "task_id": task["id"]}
        ).status_code
        == 404
    )


def test_future_time_task_and_preference_conflicts(auth_client):
    h = signin(auth_client)
    task = create(auth_client, h).json()
    now = identity.now_utc()
    assert schedule(auth_client, h, task, now - timedelta(seconds=1)).status_code == 422
    assert schedule(auth_client, h, task, now + timedelta(days=366)).status_code == 422
    row = schedule(auth_client, h, task, now + timedelta(hours=1)).json()
    assert schedule(auth_client, h, task, now + timedelta(hours=2)).status_code == 409
    task = call(auth_client, h, task, "correct", title="Synthetic changed task").json()
    assert (
        schedule(
            auth_client, h, {**task, "revision": 1}, now + timedelta(hours=2), row["revision"]
        ).status_code
        == 409
    )
    assert policy(auth_client, h).status_code == 200
    assert policy(auth_client, h, daily_limit=2).status_code == 409


def test_worker_requires_bounded_pass():
    for limit in [0, 101]:
        with pytest.raises(ValueError):
            reminder_worker.run_once(limit=limit)


def test_paged_metadata_history_and_inbox(auth_client):
    h = signin(auth_client)
    task = create(auth_client, h).json()
    when = identity.now_utc() + timedelta(hours=1)
    row = None
    for _ in range(28):
        row = schedule(auth_client, h, task, when, row["revision"] if row else None).json()
    first = post(auth_client, h, "history", {"scope": task["scope"], "task_id": task["id"]}).json()
    second = post(
        auth_client,
        h,
        "history",
        {"scope": task["scope"], "task_id": task["id"], "after": first["next_cursor"]},
    ).json()
    assert len(first["items"]) == 25 and len(second["items"]) == 3 and second["next_cursor"] is None
    for n in range(26):
        current = create(auth_client, h, title=f"Synthetic paging reminder {n}").json()
        schedule(auth_client, h, current, when)
    first = inbox(auth_client, h, state="scheduled").json()
    second = inbox(auth_client, h, state="scheduled", after=first["next_cursor"]).json()
    assert len(first["items"]) == 25 and len(second["items"]) == 2 and second["next_cursor"] is None
    identifiers = [x["reminder"]["id"] for x in first["items"] + second["items"]]
    assert identifiers == sorted(set(identifiers))


def test_long_dst_day_budget_and_expired_browser_session(auth_client, auth_store, monkeypatch):
    now = datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    h = signin(auth_client)
    policy(auth_client, h, timezone="Europe/Paris", daily_limit=1)
    one = create(auth_client, h).json()
    two = create(auth_client, h).json()
    schedule(auth_client, h, one, now + timedelta(minutes=1))
    schedule(auth_client, h, two, datetime(2026, 10, 25, 22, 30, tzinfo=UTC))
    now += timedelta(minutes=2)
    assert reminder_worker.run_once(auth_store)["delivered"] == 1
    now = datetime(2026, 10, 25, 22, 31, tzinfo=UTC)
    result = reminder_worker.run_once(auth_store)
    assert (
        result["delivered"] == 0 and result["deferred"] == 1
    )  # Same Paris day after more than 24 real hours.
    now = datetime(2026, 10, 25, 23, 1, tzinfo=UTC)
    assert (
        reminder_worker.run_once(auth_store)["delivered"] == 1
    )  # New Paris day; the browser session has long expired.


def test_worker_reads_only_task_metadata_and_fails_closed_for_bad_zone(
    auth_client, auth_store, auth_engine, monkeypatch
):
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    h = signin(auth_client)
    task = create(auth_client, h).json()
    policy(auth_client, h)
    schedule(auth_client, h, task, now + timedelta(minutes=1))
    now += timedelta(minutes=2)
    with auth_store.begin() as db:
        db.scalar(select(ReminderPreferences)).timezone = "No/Such_Zone"
    statements = []

    def inspect_sql(conn, cursor, statement, params, ctx, many):
        statements.append(statement)

    event.listen(auth_engine, "before_cursor_execute", inspect_sql)
    try:
        assert reminder_worker.run_once(auth_store)["failed"] == 1
    finally:
        event.remove(auth_engine, "before_cursor_execute", inspect_sql)
    assert not any(
        "manual_tasks.title" in sql
        or "manual_tasks.details" in sql
        or "manual_tasks.source_reference" in sql
        for sql in statements
    )
    with auth_store() as db:
        assert db.scalar(select(TaskReminder)).state == "scheduled"
