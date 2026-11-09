"""Actual restricted PostgreSQL lifecycle, serialization and permission/audit gates."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from test_routines import BASE, call, create

from app import identity, reminder_worker, routine_worker, routines
from app.models import (
    AuthSession,
    ManualTask,
    ManualTaskRevision,
    Routine,
    RoutineOccurrence,
    RoutineRevision,
    User,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    value = [BASE]
    monkeypatch.setattr(identity, "now_utc", lambda: value[0])
    return value


@pytest.fixture(autouse=True)
def quiesce_owned_intent(clock, scenario):
    # Keep append-only evidence, but do not leave due intent for unrelated worker tests.
    yield
    _, _, _, admin, uid = scenario
    with admin.begin() as db:
        owner = db.get(User, uid)
        rows = list(db.scalars(select(Routine).where(Routine.owner_id == uid).with_for_update()))
        for row in rows:
            routines.cancel_linked(db, owner, routines.linked_tasks(db, row, exclusive=True))
            if row.state == "active":
                row.state, row.next_at = "paused", None
                row.changes += 1
                row.revision += 1
                row.updated_at = identity.now_utc()
                routines.record(db, owner, row, "pause")


def test_runtime_generation_delivery_and_aggregate_scrub(scenario, runtime_engine, clock):
    client, h, _, admin, _ = scenario
    row = create(client, h, local_time="09:01").json()
    clock[0] = BASE + timedelta(minutes=2)
    runtime = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    assert routine_worker.run_once(runtime)["generated"] == 1
    row = call(client, h, row, "read").json()
    receipts = call(client, h, row, "occurrences").json()["occurrences"]["items"]
    assert len(receipts) == 1 and receipts[0]["task"]["status"] == "open"
    clock[0] += timedelta(seconds=2)
    assert reminder_worker.run_once(runtime)["delivered"] == 1
    assert routine_worker.run_once(runtime)["generated"] == 0
    row = call(client, h, row, "action", action="forget").json()
    assert row["state"] == "forgotten"
    with admin() as db:
        assert db.get(ManualTask, UUID(receipts[0]["task_id"])).state == "forgotten"
        assert all(
            x.snapshot is None
            for x in db.scalars(
                select(RoutineRevision).where(RoutineRevision.routine_id == UUID(row["id"]))
            )
        )
        assert all(
            x.snapshot is None
            for x in db.scalars(
                select(ManualTaskRevision).where(
                    ManualTaskRevision.task_id == UUID(receipts[0]["task_id"])
                )
            )
        )


def test_concurrent_workers_generate_one_local_date(scenario, runtime_engine, clock):
    client, h, _, admin, _ = scenario
    row = create(client, h, local_time="09:01").json()
    clock[0] = BASE + timedelta(minutes=2)
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: routine_worker.run_once(maker), range(2)))
    assert sum(r["generated"] for r in results) == 1 and not sum(r["failed"] for r in results)
    with admin() as db:
        receipts = list(
            db.scalars(
                select(RoutineOccurrence).where(RoutineOccurrence.routine_id == UUID(row["id"]))
            )
        )
        assert len(receipts) == 1 and receipts[0].task_id


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM routines WHERE id=:id",
        "TRUNCATE routines CASCADE",
        "UPDATE routines SET owner_id=:other,revision=revision+1 WHERE id=:id",
        "UPDATE routines SET revision=revision+2 WHERE id=:id",
        "UPDATE routines SET scope_key='member_a_private',revision=revision+1 WHERE id=:id",
        "UPDATE routine_revisions SET snapshot=NULL WHERE routine_id=:id",
        "DELETE FROM routine_revisions WHERE routine_id=:id",
        "TRUNCATE routine_revisions",
        "DELETE FROM routine_occurrences WHERE routine_id=:id",
        "TRUNCATE routine_occurrences",
    ],
)
def test_sql_identity_history_and_delete_denial(scenario, runtime_engine, clock, sql):
    client, h, _, _, _ = scenario
    row = create(client, h).json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(sql), {"id": UUID(row["id"]), "other": uuid4()})


def wait_lock(admin):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        with admin() as db:
            if db.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%routines%FOR %'"
                )
            ):
                return
        time.sleep(0.02)
    raise AssertionError("Routine request did not reach actual row wait")


@pytest.mark.parametrize(
    "op,payload",
    [
        ("read", {}),
        ("history", {}),
        ("occurrences", {}),
        ("export", {"acknowledge_copy_limits": True}),
        ("action", {"action": "forget"}),
    ],
)
def test_expiry_after_real_row_wait_no_release(scenario, monkeypatch, clock, op, payload):
    client, h, _, admin, uid = scenario
    row = create(client, h).json()
    with admin() as db:
        expiry = db.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == uid))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(select(Routine).where(Routine.id == UUID(row["id"])).with_for_update())
            pending = pool.submit(call, client, h, row, op, **payload)
            wait_lock(admin)
            clock[0] = identity.aware(expiry) + timedelta(seconds=1)
        assert pending.result(timeout=5).status_code == 401
    with admin() as db:
        assert db.get(Routine, UUID(row["id"])).revision == 1


def test_runtime_audit_failure_rolls_back_task_cursor_receipt(scenario, runtime_engine, clock):
    client, h, _, admin, _ = scenario
    row = create(client, h, local_time="09:01").json()
    clock[0] = BASE + timedelta(minutes=2)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic routine audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        assert (
            routine_worker.run_once(sessionmaker(bind=runtime_engine, expire_on_commit=False))[
                "failed"
            ]
            == 1
        )
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert db.get(Routine, UUID(row["id"])).revision == 1
        assert not list(
            db.scalars(
                select(RoutineOccurrence).where(RoutineOccurrence.routine_id == UUID(row["id"]))
            )
        )


def test_stale_human_mutation_after_worker_cursor_advance(scenario, runtime_engine, clock):
    client, h, _, _, _ = scenario
    row = create(client, h, local_time="09:01").json()
    clock[0] = BASE + timedelta(minutes=2)
    routine_worker.run_once(sessionmaker(bind=runtime_engine, expire_on_commit=False))
    assert call(client, h, row, "action", action="pause").status_code == 409


def test_worker_pins_current_user_and_scope_until_atomic_generation(
    scenario, runtime_engine, clock
):
    client, h, _, admin, uid = scenario
    row = create(client, h, local_time="09:01").json()
    clock[0] = BASE + timedelta(minutes=2)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(select(Routine).where(Routine.id == UUID(row["id"])).with_for_update())
            pending = pool.submit(
                routine_worker.run_once, sessionmaker(bind=runtime_engine, expire_on_commit=False)
            )
            wait_lock(admin)
            for statement in [
                "DELETE FROM user_scopes WHERE user_id=:id",
                "UPDATE users SET is_active=false WHERE id=:id",
            ]:
                with admin.begin() as revoker, pytest.raises(DBAPIError) as error:
                    revoker.execute(text("SET LOCAL lock_timeout='100ms'"))
                    revoker.execute(text(statement), {"id": uid})
                assert error.value.orig.sqlstate == "55P03"
        assert pending.result(timeout=5)["generated"] == 1


def test_human_change_limit_still_allows_pause_and_aggregate_forget(scenario, clock):
    client, h, _, _, _ = scenario
    row = create(client, h).json()
    for i in range(100):
        response = call(client, h, row, "correct", title=f"Synthetic bounded change {i}")
        assert response.status_code == 200
        row = response.json()
    assert call(client, h, row, "correct", title="Synthetic excess").status_code == 429
    row = call(client, h, row, "action", action="pause").json()
    row = call(client, h, row, "action", action="forget").json()
    assert row["state"] == "forgotten" and row["changes"] == 102
