"""Restricted local delivery, serialized budgets, history seals and authority races."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from conftest import RUNTIME_PASSWORD
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from test_manual_tasks import call, create
from test_task_reminders import action, inbox, policy, post, schedule

from app import identity, reminder_worker
from app import task_reminders as reminders
from app.manage import set_scope
from app.models import (
    AuthSession,
    ManualTask,
    TaskReminder,
    TaskReminderEvent,
    User,
)
from app.runtime_role import configure

pytestmark = pytest.mark.integration


def setup(scenario, monkeypatch, limit=5):
    client, h, _, admin, uid = scenario
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    assert policy(client, h, daily_limit=limit).status_code == 200
    task = create(client, h, title="Synthetic reminder " + uuid4().hex).json()
    response = schedule(client, h, task, now + timedelta(seconds=1))
    assert response.status_code == 200, response.json()
    monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(seconds=2))
    return client, h, admin, uid, task, response.json()


def candidate_for(db, identifier):
    return db.execute(
        select(
            TaskReminder.id, TaskReminder.owner_id, TaskReminder.task_id, TaskReminder.scope_key
        ).where(TaskReminder.id == UUID(identifier))
    ).one()


def only_pass(runtime_engine, row):
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with maker.begin() as db:
        candidate = candidate_for(db, row["id"])
    with maker.begin() as db:
        return reminder_worker.process(db, candidate)


def test_runtime_delivery_ack_reschedule_cancel_history(scenario, runtime_engine, monkeypatch):
    client, h, admin, _, task, row = setup(scenario, monkeypatch)
    assert only_pass(runtime_engine, row) == "delivered"
    rows = inbox(client, h).json()["items"]
    current = next(x["reminder"] for x in rows if x["reminder"]["id"] == row["id"])
    row = action(client, h, task, current, "acknowledge").json()
    assert row["state"] == "acknowledged"
    row = schedule(client, h, task, identity.now_utc() + timedelta(hours=1), row["revision"]).json()
    assert row["cycle"] == 2
    assert call(client, h, task, "transition", status="done").status_code == 200
    history = post(client, h, "history", {"scope": task["scope"], "task_id": task["id"]}).json()[
        "items"
    ]
    assert [r["operation"] for r in history] == [
        "scheduled",
        "delivered",
        "acknowledged",
        "rescheduled",
        "cancelled",
    ]
    with admin() as db:
        assert db.get(TaskReminder, UUID(row["id"])).reason == "task_closed"


def test_concurrent_workers_deliver_a_cycle_once(scenario, runtime_engine, monkeypatch):
    _, _, admin, uid, _, row = setup(scenario, monkeypatch)
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with maker.begin() as db:
        candidate = candidate_for(db, row["id"])

    def run():
        with maker.begin() as db:
            return reminder_worker.process(db, candidate)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(results) == ["delivered", "skipped"]
    with admin() as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(TaskReminderEvent).where(
                            TaskReminderEvent.owner_id == uid,
                            TaskReminderEvent.operation == "delivered",
                        )
                    )
                )
            )
            == 1
        )


def test_budget_serializes_two_due_tasks_across_scopes(scenario, runtime_engine, monkeypatch):
    client, h, admin, uid, _, first = setup(scenario, monkeypatch, limit=1)
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "member_a_private", True)
    now = identity.now_utc()
    task = create(client, h, scope="member_a_private").json()
    second = schedule(client, h, task, now + timedelta(seconds=1)).json()
    monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(seconds=2))
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with maker.begin() as db:
        items = [candidate_for(db, first["id"]), candidate_for(db, second["id"])]

    def run(item):
        with maker.begin() as db:
            return reminder_worker.process(db, item)

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(run, items))
    assert sorted(result) == ["deferred", "delivered"]
    with admin() as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(TaskReminderEvent).where(
                            TaskReminderEvent.owner_id == uid,
                            TaskReminderEvent.operation == "delivered",
                        )
                    )
                )
            )
            == 1
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "owner_id=:other,revision=revision+1",
        "scope_key='member_a_private',revision=revision+1",
        "task_id=:other,revision=revision+1",
        "created_at=created_at+interval '1s',revision=revision+1",
        "revision=revision+2",
        "cycle=cycle+2,revision=revision+1",
        "state='acknowledged',revision=revision+1",
        "state='delivered',next_attempt_at=NULL,delivered_at=now(),revision=revision+1",
        "state='scheduled',reason=NULL,revision=revision+1",
        "state='cancelled',next_attempt_at=NULL,reason=NULL,revision=revision+1",
    ],
)
def test_raw_state_identity_and_revision_guards(scenario, runtime_engine, monkeypatch, mutation):
    _, _, _, _, _, row = setup(scenario, monkeypatch)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(f"UPDATE task_reminders SET {mutation} WHERE id=:id"),
            {"id": UUID(row["id"]), "other": uuid4()},
        )


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM task_reminders WHERE id=:id",
        "TRUNCATE task_reminders CASCADE",
        "UPDATE task_reminder_events SET snapshot='{}' WHERE reminder_id=:id",
        "DELETE FROM task_reminder_events WHERE reminder_id=:id",
        "TRUNCATE task_reminder_events",
        "UPDATE reminder_preferences SET owner_id=:other WHERE owner_id=:owner",
        "UPDATE reminder_preferences SET daily_limit=21 WHERE owner_id=:owner",
        "DELETE FROM reminder_preferences WHERE owner_id=:owner",
        "SELECT metadata_json FROM audit_events",
        "UPDATE user_scopes SET created_at=created_at",
    ],
)
def test_runtime_history_and_least_privilege(scenario, runtime_engine, monkeypatch, statement):
    _, _, _, uid, _, row = setup(scenario, monkeypatch)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(statement), {"id": UUID(row["id"]), "owner": uid, "other": uuid4()})


def test_bad_history_snapshot_and_actor_refused(scenario, runtime_engine, monkeypatch):
    _, _, _, uid, _, row = setup(scenario, monkeypatch)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "INSERT INTO task_reminder_events(id,reminder_id,owner_id,revision,operation,recorded_at,snapshot) VALUES(:new,:id,:owner,2,'delivered',now(),'{}')"
            ),
            {"new": uuid4(), "id": UUID(row["id"]), "owner": uid},
        )


def wait_for_lock(admin, needle):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with admin() as db:
            if db.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE :needle"
                ),
                {"needle": needle},
            ):
                return
        time.sleep(0.02)
    raise AssertionError("Synthetic reminder did not reach real lock wait")


def test_session_expiry_after_real_task_lock_wait(scenario, monkeypatch):
    client, h, _, admin, uid = scenario
    task = create(client, h).json()
    with admin() as db:
        expiry = db.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == uid))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(select(ManualTask).where(ManualTask.id == UUID(task["id"])).with_for_update())
            pending = pool.submit(
                schedule, client, h, task, identity.now_utc() + timedelta(hours=1)
            )
            wait_for_lock(admin, "%manual_tasks%FOR UPDATE%")
            monkeypatch.setattr(
                identity, "now_utc", lambda: identity.aware(expiry) + timedelta(seconds=1)
            )
        response = pending.result(timeout=5)
    assert response.status_code == 401


def test_scope_revocation_pinned_through_worker_commit(scenario, runtime_engine, monkeypatch):
    _, _, admin, uid, _, row = setup(scenario, monkeypatch)
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with maker.begin() as db:
        candidate = candidate_for(db, row["id"])
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(
                select(ManualTask).where(ManualTask.id == candidate.task_id).with_for_update()
            )

            def run():
                with maker.begin() as db:
                    return reminder_worker.process(db, candidate)

            pending = pool.submit(run)
            wait_for_lock(admin, "%manual_tasks%FOR UPDATE%")
            for statement in [
                "UPDATE users SET is_active=false WHERE id=:uid",
                "DELETE FROM user_scopes WHERE user_id=:uid",
            ]:
                with admin.begin() as other, pytest.raises(DBAPIError) as error:
                    other.execute(text("SET LOCAL lock_timeout='100ms'"))
                    other.execute(text(statement), {"uid": uid})
                assert error.value.orig.sqlstate == "55P03"
        assert pending.result(timeout=5) == "delivered"


def test_audit_failure_rolls_back_runtime_delivery(scenario, runtime_engine, monkeypatch):
    _, _, admin, _, _, row = setup(scenario, monkeypatch)

    def fail(conn, cursor, statement, params, ctx, many):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic worker audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(SQLAlchemyError):
            only_pass(runtime_engine, row)
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert db.get(TaskReminder, UUID(row["id"])).state == "scheduled"
        assert (
            len(
                list(
                    db.scalars(
                        select(TaskReminderEvent).where(
                            TaskReminderEvent.reminder_id == UUID(row["id"])
                        )
                    )
                )
            )
            == 1
        )
    assert only_pass(runtime_engine, row) == "delivered"


def test_grouped_column_reset_removes_stale_grants(postgres_engine, runtime_engine):
    with postgres_engine.begin() as db:
        db.execute(
            text("GRANT UPDATE(created_at), INSERT(user_id) ON user_scopes TO butler_runtime")
        )
        db.execute(text("GRANT UPDATE(operation) ON task_reminder_events TO butler_runtime"))
        configure(db.connection.driver_connection, RUNTIME_PASSWORD)
    with runtime_engine.connect() as db:
        assert not db.scalar(
            text("SELECT has_column_privilege(current_user,'user_scopes','created_at','UPDATE')")
        )
        assert not db.scalar(
            text("SELECT has_column_privilege(current_user,'user_scopes','user_id','INSERT')")
        )
        assert not db.scalar(
            text(
                "SELECT has_column_privilege(current_user,'task_reminder_events','operation','UPDATE')"
            )
        )


def test_actual_process_exit_rolls_back_before_retry(scenario, runtime_engine, monkeypatch):
    import os
    import subprocess
    import sys

    _, _, admin, _, _, row = setup(scenario, monkeypatch)
    script = """
import os,sys
from datetime import datetime
from sqlalchemy import select
from uuid import UUID
from app import identity,reminder_worker
from app.db import SessionLocal
from app.models import TaskReminder
identity.now_utc=lambda:datetime.fromisoformat(sys.argv[2])
with SessionLocal.begin() as db:
 candidate=db.execute(select(TaskReminder.id,TaskReminder.owner_id,TaskReminder.task_id,TaskReminder.scope_key).where(TaskReminder.id==UUID(sys.argv[1]))).one()
 assert reminder_worker.process(db,candidate)=='delivered'
 os._exit(31)
"""
    env = dict(
        os.environ, BUTLER_POSTGRES_USER="butler_runtime", BUTLER_POSTGRES_PASSWORD=RUNTIME_PASSWORD
    )
    result = subprocess.run(
        [sys.executable, "-c", script, row["id"], identity.now_utc().isoformat()],
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 31, "Synthetic crash subprocess did not reach uncommitted delivery"
    with admin() as db:
        assert db.get(TaskReminder, UUID(row["id"])).state == "scheduled"
    assert only_pass(runtime_engine, row) == "delivered"


def test_runtime_quiet_deferral_reconsiders_changed_preferences(
    scenario, runtime_engine, monkeypatch
):
    client, h, _, _, _, row = setup(scenario, monkeypatch)
    now = identity.now_utc()
    minute = now.hour * 60 + now.minute
    assert (
        policy(
            client, h, expected_revision=1, quiet_start=minute, quiet_end=(minute + 60) % 1440
        ).status_code
        == 200
    )
    assert only_pass(runtime_engine, row) == "deferred"
    assert policy(client, h, expected_revision=2).status_code == 200
    assert only_pass(runtime_engine, row) == "delivered"


def test_forgetting_delivered_task_cancels_without_copying_text(
    scenario, runtime_engine, monkeypatch
):
    client, h, admin, _, task, row = setup(scenario, monkeypatch)
    assert only_pass(runtime_engine, row) == "delivered"
    assert call(client, h, task, "forget").status_code == 200
    with admin() as db:
        stored = db.get(TaskReminder, UUID(row["id"]))
        assert stored.state == "cancelled" and stored.reason == "task_forgotten"
        snapshots = list(
            db.scalars(
                select(TaskReminderEvent.snapshot).where(TaskReminderEvent.reminder_id == stored.id)
            )
        )
        assert len(snapshots) == 3 and all("Synthetic" not in str(r) for r in snapshots)
        assert db.get(ManualTask, UUID(task["id"])).title is None


@pytest.mark.parametrize("variant", ["actor", "extra_text", "task_identity"])
def test_history_guard_rejects_forged_current_snapshot(scenario, runtime_engine, variant):
    import json

    client, h, _, admin, uid = scenario
    task = create(client, h).json()
    now = identity.now_utc()
    when = now + timedelta(hours=1)
    with admin.begin() as db:
        row = TaskReminder(
            task_id=UUID(task["id"]),
            owner_id=uid,
            scope_key=task["scope"],
            revision=1,
            cycle=1,
            policy_revision=0,
            task_revision=1,
            state="scheduled",
            scheduled_at=when,
            next_attempt_at=when,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        identifier = row.id
        snapshot = reminders.document(row)
    actor = uuid4() if variant == "actor" else uid
    if variant == "extra_text":
        snapshot["title"] = "Synthetic forbidden content copy"
    if variant == "task_identity":
        snapshot["task_id"] = str(uuid4())
    with runtime_engine.begin() as db, pytest.raises(DBAPIError) as error:
        db.execute(
            text(
                "INSERT INTO task_reminder_events(id,reminder_id,owner_id,revision,actor_id,operation,recorded_at,snapshot) VALUES(:new,:id,:owner,1,:actor,'scheduled',:now,CAST(:snapshot AS jsonb))"
            ),
            {
                "new": uuid4(),
                "id": identifier,
                "owner": uid,
                "actor": actor,
                "now": now,
                "snapshot": json.dumps(snapshot),
            },
        )
    assert error.value.orig.sqlstate == "23514"
