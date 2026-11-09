"""Restricted-role, current-authority, audit and actual lock-wait evidence."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_calendars import briefing, call, create, window

from app import identity
from app.manage import set_scope
from app.models import AuthSession, CalendarRevision, CalendarSource, User

pytestmark = pytest.mark.integration


def test_runtime_reconcile_history_and_scrub(scenario):
    client, h, _, admin, _ = scenario
    response = create(client, h)
    assert response.status_code == 201
    row = call(client, h, response.json(), "import", window=window()).json()
    assert row["revision"] == 2
    assert briefing(client, h).json()["events"][0]["uid"] == "synthetic-event"
    assert len(call(client, h, row, "history").json()["items"]) == 2
    row = call(client, h, row, "forget").json()
    with admin() as db:
        assert db.get(CalendarSource, UUID(row["id"])).data is None
        assert (
            list(
                db.scalars(
                    select(CalendarRevision.snapshot).where(
                        CalendarRevision.source_id == UUID(row["id"])
                    )
                )
            )
            == [None] * 3
        )
    assert call(client, h, row, "import", window=window()).status_code == 410


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM calendar_sources WHERE id=:id",
        "TRUNCATE calendar_sources CASCADE",
        "UPDATE calendar_sources SET revision=revision+2 WHERE id=:id",
        "UPDATE calendar_sources SET owner_id=:other,revision=revision+1 WHERE id=:id",
        "UPDATE calendar_sources SET scope_key='member_a_private',revision=revision+1 WHERE id=:id",
        "UPDATE calendar_sources SET data='{}',revision=revision+1 WHERE id=:id",
        "UPDATE calendar_revisions SET snapshot=NULL WHERE source_id=:id",
        "DELETE FROM calendar_revisions WHERE source_id=:id",
        "TRUNCATE calendar_revisions",
        "UPDATE calendar_revisions SET revision=2 WHERE source_id=:id",
    ],
)
def test_raw_mutation_and_history_seals(scenario, runtime_engine, statement):
    client, h, _, _, _ = scenario
    row = create(client, h).json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(statement), {"id": UUID(row["id"]), "other": uuid4()})
    assert call(client, h, row, "read").json()["revision"] == 1


def wait_for_lock(admin):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with admin() as db:
            if db.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%calendar_sources%FOR %'"
                )
            ):
                return
        time.sleep(0.02)
    raise AssertionError("Calendar request did not reach actual row wait")


@pytest.mark.parametrize("operation", ["read", "import", "briefing", "history", "export"])
def test_session_expiry_after_actual_row_wait(scenario, monkeypatch, operation):
    client, h, _, admin, uid = scenario
    row = create(client, h).json()
    with admin() as db:
        expiry = db.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == uid))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(
                select(CalendarSource).where(CalendarSource.id == UUID(row["id"])).with_for_update()
            )
            if operation == "briefing":
                pending = pool.submit(briefing, client, h)
            else:
                payload = (
                    {"window": window()}
                    if operation == "import"
                    else {"acknowledge_copy_limits": True}
                    if operation == "export"
                    else {}
                )
                pending = pool.submit(call, client, h, row, operation, **payload)
            wait_for_lock(admin)
            monkeypatch.setattr(
                identity, "now_utc", lambda: identity.aware(expiry) + timedelta(seconds=1)
            )
        assert pending.result(timeout=5).status_code == 401
    with admin() as db:
        assert db.get(CalendarSource, UUID(row["id"])).revision == 1


def test_actual_concurrent_stale_import_and_scope_pinning(scenario):
    client, h, _, admin, uid = scenario
    row = create(client, h).json()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            locked = db.scalar(
                select(CalendarSource).where(CalendarSource.id == UUID(row["id"])).with_for_update()
            )
            pending = pool.submit(call, client, h, row, "import", window=window())
            wait_for_lock(admin)
            with admin.begin() as revoker, pytest.raises(DBAPIError) as error:
                revoker.execute(text("SET LOCAL lock_timeout='100ms'"))
                revoker.execute(text("DELETE FROM user_scopes WHERE user_id=:id"), {"id": uid})
            assert error.value.orig.sqlstate == "55P03"
            locked.revision += 1
            locked.data = {
                **locked.data,
                "status": "offline",
                "attempt_at": identity.now_utc().isoformat(),
            }
            locked.updated_at = identity.now_utc()
            db.flush()
            db.add(
                CalendarRevision(
                    source_id=locked.id,
                    revision=locked.revision,
                    actor_id=uid,
                    snapshot=locked.data,
                    created_at=locked.updated_at,
                )
            )
        assert pending.result(timeout=5).status_code == 409
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "household_shared", False)
    assert briefing(client, h).status_code == 403


def test_audit_failure_atomic_import_and_briefing_release(scenario, runtime_engine):
    client, h, _, admin, _ = scenario
    row = create(client, h).json()

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic calendar audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        assert call(client, h, row, "import", window=window()).status_code == 503
        assert briefing(client, h).status_code == 503
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert db.get(CalendarSource, UUID(row["id"])).revision == 1
        assert (
            len(
                list(
                    db.scalars(
                        select(CalendarRevision).where(
                            CalendarRevision.source_id == UUID(row["id"])
                        )
                    )
                )
            )
            == 1
        )


def test_forged_history_and_tombstone_resurrection_denied(scenario, runtime_engine):
    client, h, _, _, uid = scenario
    row = create(client, h).json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "INSERT INTO calendar_revisions(id,source_id,revision,actor_id,snapshot,created_at) VALUES(:new,:id,2,:actor,'{}',now())"
            ),
            {"new": uuid4(), "id": UUID(row["id"]), "actor": uid},
        )
    call(client, h, row, "forget")
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "UPDATE calendar_sources SET state='active',data=:data,revision=revision+1 WHERE id=:id"
            ),
            {
                "id": UUID(row["id"]),
                "data": '{"label":"Synthetic","status":"setup_required","window":null}',
            },
        )
