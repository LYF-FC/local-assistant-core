from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin

from app import identity, reminder_worker, routine_worker
from app import routine_contracts as contract
from app.manage import set_scope
from app.models import (
    AuditEvent,
    ManualTask,
    ManualTaskRevision,
    Routine,
    RoutineOccurrence,
    RoutineRevision,
    TaskReminder,
    User,
)

BASE = datetime(2026, 11, 9, 8, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch):
    value = [BASE]
    monkeypatch.setattr(identity, "now_utc", lambda: value[0])
    return value


def values(**changes):
    return {
        "scope": "household_shared",
        "title": "Synthetic routine",
        "details": "Synthetic routine details",
        "source_reference": "Synthetic instructions",
        "timezone": "Europe/Paris",
        "local_time": "10:00",
        "frequency": "daily",
        "interval": 1,
        "weekdays": [],
        "starts_on": "2026-11-09",
        "ends_on": "2026-11-12",
        "remind": True,
        **changes,
    }


def create(client, h, **changes):
    return client.post(
        "/api/v1/routines", headers=h, json={**values(), "authorize_future_tasks": True, **changes}
    )


def call(client, h, row, op, **changes):
    body = {"scope": row["scope"]}
    if op in {"action", "correct"}:
        body["expected_revision"] = row["revision"]
    if op == "correct":
        body.update({**values(scope=row["scope"]), "authorize_future_tasks": True})
    return client.post(f"/api/v1/routines/{row['id']}/{op}", headers=h, json={**body, **changes})


def read(client, h, row):
    return call(client, h, row, "read").json()


def test_plan_daily_weekly_gap_fold_and_forward_only():
    daily = contract.resolve(contract.Values(**values()), BASE)
    assert len(daily["plan"]) == 4 and daily["plan"][0]["due_at"] == "2026-11-09T09:00:00+00:00"
    weekly = contract.resolve(
        contract.Values(
            **values(frequency="weekly", interval=2, weekdays=[1, 3], ends_on="2026-11-30")
        ),
        BASE,
    )
    assert [p["day"] for p in weekly["plan"]] == [
        "2026-11-09",
        "2026-11-11",
        "2026-11-23",
        "2026-11-25",
    ]
    assert contract.local_instant(datetime(2026, 3, 29).date(), "02:30", "Europe/Paris") is None
    assert contract.local_instant(
        datetime(2026, 10, 25).date(), "02:30", "Europe/Paris"
    ) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    a = contract.local_instant(datetime(2026, 3, 28).date(), "10:00", "Europe/Paris")
    b = contract.local_instant(datetime(2026, 3, 29).date(), "10:00", "Europe/Paris")
    assert b - a == timedelta(hours=23)
    late = contract.resolve(contract.Values(**values()), BASE + timedelta(hours=2))
    assert late["plan"][0]["day"] == "2026-11-10"


def test_full_generation_current_status_pause_resume_and_forget(auth_client, auth_store, clock):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    assert row["revision"] == 1
    clock[0] = BASE + timedelta(hours=1)
    assert routine_worker.run_once(auth_store)["generated"] == 1
    h = signin(auth_client)
    row = read(auth_client, h, row)
    assert row["revision"] == 2 and row["position"] == 1
    page = call(auth_client, h, row, "occurrences").json()["occurrences"]
    task = page["items"][0]["task"]
    assert task["title"] == "Synthetic routine" and task["status"] == "open"
    assert routine_worker.run_once(auth_store)["generated"] == 0
    clock[0] += timedelta(seconds=2)
    assert reminder_worker.run_once(auth_store)["delivered"] == 1
    r = auth_client.post(
        f"/api/v1/tasks/{task['id']}/transition",
        headers=h,
        json={"scope": task["scope"], "expected_revision": 1, "status": "done"},
    )
    assert r.status_code == 200
    assert (
        call(auth_client, h, row, "occurrences").json()["occurrences"]["items"][0]["task"]["status"]
        == "done"
    )
    row = call(auth_client, h, row, "action", action="pause").json()
    clock[0] += timedelta(days=1)
    assert routine_worker.run_once(auth_store)["checked"] == 0
    # Refresh the expired browser session; persisted worker intent itself does not use it.
    h = signin(auth_client)
    row = call(auth_client, h, row, "action", action="resume").json()
    assert row["data"]["plan"][0]["day"] == "2026-11-11"
    history = call(auth_client, h, row, "history").json()
    assert history["items"][1]["actor_id"] is None
    assert (
        call(auth_client, h, row, "export", acknowledge_copy_limits=True).json()["managed_copy"]
        is False
    )
    row = call(auth_client, h, row, "action", action="forget").json()
    assert row["state"] == "forgotten" and row["data"] is None
    assert call(auth_client, h, row, "action", action="resume").status_code == 410
    with auth_store() as db:
        assert all(r.snapshot is None for r in db.scalars(select(RoutineRevision)))
        assert db.get(ManualTask, UUID(task["id"])).state == "forgotten"
        assert all(r.snapshot is None for r in db.scalars(select(ManualTaskRevision)))


def test_downtime_latest_only_and_metadata_receipts(auth_client, auth_store, clock):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    clock[0] += timedelta(days=3, hours=1)
    assert routine_worker.run_once(auth_store)["generated"] == 1
    h = signin(auth_client)
    h = signin(auth_client)
    row = read(auth_client, h, row)
    assert row["state"] == "finished"
    receipts = call(auth_client, h, row, "occurrences").json()["occurrences"]["items"]
    assert [r["outcome"] for r in receipts] == ["missed", "missed", "missed", "created"]
    with auth_store() as db:
        audits = list(
            db.scalars(select(AuditEvent).where(AuditEvent.event_type.like("routines.%")))
        )
        assert all("Synthetic" not in str(r.metadata_json) + str(r.after_json) for r in audits)
        assert len(list(db.scalars(select(ManualTask)))) == 1


def test_correction_cancels_previous_reminders_and_local_date_never_duplicates(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    clock[0] += timedelta(hours=1)
    routine_worker.run_once(auth_store)
    h = signin(auth_client)
    row = read(auth_client, h, row)
    changed = call(auth_client, h, row, "correct", local_time="11:00", title="Synthetic corrected")
    assert changed.status_code == 200
    with auth_store() as db:
        assert db.scalar(select(TaskReminder)).state == "cancelled"
    row = changed.json()
    clock[0] += timedelta(hours=1)
    assert routine_worker.run_once(auth_store)["generated"] == 0
    with auth_store() as db:
        assert len(list(db.scalars(select(RoutineOccurrence)))) == 1
        assert db.scalar(select(ManualTask)).title == "Synthetic routine"
    clock[0] += timedelta(days=1)
    assert routine_worker.run_once(auth_store)["generated"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"authorize_future_tasks": 1},
        {"interval": True},
        {"interval": 5},
        {"weekdays": [1]},
        {"frequency": "weekly"},
        {"weekdays": [True], "frequency": "weekly"},
        {"local_time": "25:30"},
        {"timezone": "No/Zone"},
        {"starts_on": "2026-11-08"},
        {"ends_on": "2028-01-01"},
        {"remind": 1},
        {"scope": "technical_admin"},
        {"title": " "},
        {"starts_on": 0},
    ],
)
def test_invalid_rules_are_sanitized(auth_client, clock, change):
    h = signin(auth_client)
    r = create(auth_client, h, **change)
    assert r.status_code == 422 and "Synthetic" not in str(r.json())


def test_private_shared_admin_current_grants_and_csrf(auth_client, auth_store, clock):
    h = signin(auth_client)
    with auth_store.begin() as db:
        alice = db.scalar(select(User).where(User.slug == "alice"))
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, alice, "member_b_private", True)
        set_scope(db, bob, "household_shared", True)
        set_scope(db, bob, "technical_admin", True)
    shared = create(auth_client, h).json()
    private = create(auth_client, h, scope="member_b_private").json()
    bh = signin(auth_client, "bob")
    assert call(auth_client, bh, shared, "read").status_code == 200
    for op, payload in [
        ("read", {}),
        ("history", {}),
        ("occurrences", {}),
        ("export", {"acknowledge_copy_limits": True}),
        ("action", {"action": "forget"}),
        ("correct", {}),
    ]:
        assert call(auth_client, bh, private, op, **payload).status_code == 404
        if op != "read":
            assert call(auth_client, bh, shared, op, **payload).status_code == 403
    assert call(auth_client, {}, shared, "read").status_code == 403
    assert (
        call(auth_client, {**bh, "Origin": "https://other.invalid"}, shared, "read").status_code
        == 403
    )
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "bob")), "household_shared", False)
    assert call(auth_client, bh, shared, "read").status_code == 403


def test_worker_revocation_blocks_no_task_and_requires_explicit_resume(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    with auth_store.begin() as db:
        set_scope(
            db, db.scalar(select(User).where(User.slug == "alice")), "household_shared", False
        )
    clock[0] += timedelta(hours=1)
    assert routine_worker.run_once(auth_store)["blocked"] == 1
    with auth_store.begin() as db:
        assert db.scalar(select(ManualTask)) is None
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "household_shared", True)
    assert routine_worker.run_once(auth_store)["checked"] == 0
    h = signin(auth_client)
    row = read(auth_client, h, row)
    assert call(auth_client, h, row, "action", action="resume").status_code == 200


def test_audit_failure_rolls_back_generation_and_aggregate_forget(
    auth_client, auth_store, auth_engine, clock
):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    clock[0] += timedelta(hours=1)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic audit failure")

    event.listen(auth_engine, "before_cursor_execute", fail)
    try:
        assert routine_worker.run_once(auth_store)["failed"] == 1
    finally:
        event.remove(auth_engine, "before_cursor_execute", fail)
    with auth_store() as db:
        assert (
            db.scalar(select(ManualTask)) is None and db.get(Routine, UUID(row["id"])).revision == 1
        )
    assert routine_worker.run_once(auth_store)["generated"] == 1
    h = signin(auth_client)
    row = read(auth_client, h, row)
    event.listen(auth_engine, "before_cursor_execute", fail)
    try:
        assert call(auth_client, h, row, "action", action="forget").status_code == 503
    finally:
        event.remove(auth_engine, "before_cursor_execute", fail)
    with auth_store() as db:
        assert (
            db.scalar(select(ManualTask)).state == "active"
            and db.get(Routine, UUID(row["id"])).data
        )


def test_dst_gap_receipt_and_older_than_day_is_missed(auth_client, auth_store, clock):
    clock[0] = datetime(2026, 3, 28, 0, tzinfo=UTC)
    h = signin(auth_client)
    row = create(
        auth_client,
        h,
        local_time="02:30",
        starts_on="2026-03-28",
        ends_on="2026-03-30",
        remind=False,
    ).json()
    assert [p["due_at"] is None for p in row["data"]["plan"]] == [False, True, False]
    clock[0] = datetime(2026, 3, 30, 1, tzinfo=UTC)
    assert routine_worker.run_once(auth_store)["generated"] == 1
    h = signin(auth_client)
    r = call(auth_client, h, row, "occurrences").json()["occurrences"]["items"]
    assert [x["outcome"] for x in r] == ["missed", "dst_gap", "created"]
    assert not any(x["task_id"] for x in r[:2])


def test_identity_quota_and_history_keyset_and_strict_copy_ack(auth_client, auth_store, clock):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    for i in range(6):
        row = call(auth_client, h, row, "correct", title=f"Synthetic revision {i}").json()
    first = call(auth_client, h, row, "history").json()
    second = call(auth_client, h, row, "history", after=first["next_cursor"]).json()
    assert len(first["items"]) == 5 and len(second["items"]) == 2
    assert call(auth_client, h, row, "export", acknowledge_copy_limits=1).status_code == 422
    assert call(auth_client, h, {**row, "revision": 1}, "action", action="pause").status_code == 409
    call(auth_client, h, row, "action", action="forget")
    for _ in range(9):
        assert create(auth_client, h).status_code == 201
    assert create(auth_client, h).status_code == 429


def test_future_dst_gap_is_not_reserved_before_a_schedule_correction(
    auth_client, auth_store, clock
):
    clock[0] = datetime(2026, 3, 28, 0, tzinfo=UTC)
    h = signin(auth_client)
    row = create(
        auth_client,
        h,
        local_time="02:30",
        starts_on="2026-03-28",
        ends_on="2026-03-30",
        remind=False,
    ).json()
    clock[0] = datetime(2026, 3, 28, 1, 30, tzinfo=UTC)
    assert routine_worker.run_once(auth_store)["generated"] == 1
    with auth_store() as db:
        assert len(list(db.scalars(select(RoutineOccurrence)))) == 1
    h = signin(auth_client)
    row = read(auth_client, h, row)
    row = call(
        auth_client,
        h,
        row,
        "correct",
        local_time="10:00",
        starts_on="2026-03-28",
        ends_on="2026-03-30",
        remind=False,
    ).json()
    clock[0] = datetime(2026, 3, 29, 8, tzinfo=UTC)
    assert routine_worker.run_once(auth_store)["generated"] == 1
    with auth_store() as db:
        assert list(
            db.scalars(
                select(RoutineOccurrence.local_date)
                .where(RoutineOccurrence.outcome == "created")
                .order_by(RoutineOccurrence.local_date)
            )
        ) == ["2026-03-28", "2026-03-29"]
