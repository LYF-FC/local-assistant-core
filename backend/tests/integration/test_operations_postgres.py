"""Real restricted-role observations; audit reads remain deliberately forbidden."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import SYNTHETIC_PASSWORD, client_for
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_operations import enqueue_technical, read

from app import identity
from app.manage import provision, set_scope
from app.models import AuditEvent, User

pytestmark = pytest.mark.integration


def ready(scenario):
    client, h, _, admin, uid = scenario
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "technical_admin", True)
    return client, h, admin, uid


def test_runtime_snapshot_with_audit_select_still_forbidden(scenario, runtime_engine):
    client, h, admin, uid = ready(scenario)
    result = read(client, h)
    assert result.status_code == 200, result.text
    assert result.json()["actor_id"] == str(uid) and result.json()["activity"] == {
        "state": "not_available"
    }
    with pytest.raises(DBAPIError), runtime_engine.begin() as db:
        db.execute(text("SELECT occurred_at FROM public.audit_events LIMIT 1"))
    with admin() as db:
        row = db.scalar(
            select(AuditEvent).where(
                AuditEvent.initiator_id == str(uid), AuditEvent.event_type == "operations.read"
            )
        )
        assert row and row.metadata_json == {"jobs_sampled": 0}


def test_runtime_job_boundaries_other_admin_and_other_scope(scenario, runtime_engine):
    from sqlalchemy.orm import sessionmaker

    client, h, admin, _uid = ready(scenario)
    slug = "synthetic-operations-" + uuid4().hex
    with admin.begin() as db:
        provision(db, slug, "Synthetic other admin", SYNTHETIC_PASSWORD, {"technical_admin"})
    # Exercise real runtime grants and API savepoints without leaving queued jobs
    # for unrelated global worker tests (or a subsequent verification run).
    with runtime_engine.connect() as connection:
        transaction = connection.begin()
        maker = sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            with client_for(maker) as isolated:
                isolated.cookies.update(client.cookies)
                for i in range(26):
                    enqueue_technical(isolated, h, f"synthetic-operations-{i:04}")
                enqueue_technical(isolated, h, "synthetic-operations-household", "household_shared")
                body = read(isolated, h).json()
                assert (
                    body["jobs"]["sampled"] == 25
                    and body["jobs"]["has_more"]
                    and body["jobs"]["counts"]["queued"] == 25
                )
                r = isolated.post(
                    "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
                )
                assert r.status_code == 200
                response = read(isolated, {"X-CSRF-Token": r.json()["csrf_token"]})
                assert response.status_code == 200 and response.json()["jobs"]["sampled"] == 0
        finally:
            transaction.rollback()


def test_runtime_denials_and_audit_commit_failure(scenario, runtime_engine):
    client, h, _, admin, uid = scenario
    assert read(client, h).status_code == 403
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "technical_admin", True)
    assert read(client, {}).status_code == 403
    assert read(client, {**h, "Origin": "https://invalid.example"}).status_code == 403

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("synthetic-private-error")

    with admin() as db:
        before = db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "operations.read", AuditEvent.initiator_id == str(uid))
        )
    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        r = read(client, h)
        assert (
            r.status_code == 503 and "software" not in r.text and "synthetic-private" not in r.text
        )
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "operations.read", AuditEvent.initiator_id == str(uid)
                )
            )
            == before
        )
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "technical_admin", False)
    assert read(client, h).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=h, json={}).status_code == 200
    assert read(client, h).status_code == 401


def test_actual_user_lock_wait_rechecks_session_expiry(scenario, monkeypatch):
    client, h, admin, uid = ready(scenario)
    now = identity.now_utc()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(select(User).where(User.id == uid).with_for_update())
            future = pool.submit(read, client, h)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with admin() as observer:
                    blocked = observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%FROM users%FOR SHARE%'"
                        )
                    )
                if blocked:
                    break
                time.sleep(0.02)
            else:
                raise AssertionError("Did not reach actual user lock wait")
            monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(hours=24))
        result = future.result(timeout=5)
        assert result.status_code == 401 and "components" not in result.text
