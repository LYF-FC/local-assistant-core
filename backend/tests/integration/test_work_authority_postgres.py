"""Work authority races through real restricted-role and privileged SQL transactions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app import identity, work_access
from app.manage import set_active
from app.models import AuthSession, User, WorkWorkspace
from app.work_manage import administer

pytestmark = pytest.mark.integration


@pytest.fixture
def authority_case(scenario, runtime_engine):
    client, _, _, admin, user_id = scenario
    slug = "synthetic-" + uuid4().hex
    with admin.begin() as db:
        user_slug = db.get(User, user_id).slug
        administer(db, "create-workspace", slug)
        administer(db, "grant", slug, user_slug)
        workspace_id = db.scalar(select(WorkWorkspace.id).where(WorkWorkspace.slug == slug))
    return {
        "client": client,
        "admin": admin,
        "runtime": sessionmaker(bind=runtime_engine),
        "token": client.cookies.get(identity.COOKIE),
        "user_id": user_id,
        "user_slug": user_slug,
        "slug": slug,
        "workspace_id": workspace_id,
    }


def wait_for_advisory(engine, pid):
    deadline = monotonic() + 1.5
    while monotonic() < deadline:
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT wait_event_type,wait_event FROM pg_stat_activity WHERE pid=:pid"),
                {"pid": pid},
            ).one()
        if row == ("Lock", "advisory"):
            return
        Event().wait(0.01)
    raise AssertionError("Expected a real PostgreSQL advisory lock wait")


def mutate(db, case, helper):
    if helper:
        administer(db, "revoke", case["slug"], case["user_slug"])
    else:
        db.execute(
            text("DELETE FROM work_access_grants WHERE user_id=:user AND workspace_id=:workspace"),
            {"user": case["user_id"], "workspace": case["workspace_id"]},
        )


@pytest.mark.parametrize("helper", [False, True])
def test_reader_holds_authority_through_audit_commit_before_revocation(
    authority_case, postgres_engine, helper
):
    case = authority_case
    read_ready, release_read, writer_started = Event(), Event(), Event()
    writer_pid = []

    def read():
        with case["runtime"].begin() as db:
            result = work_access.inspect_work(db, case["token"], case["workspace_id"])
            assert result.status == 200
            read_ready.set()
            assert release_read.wait(5)
        return result

    def revoke():
        with case["admin"].begin() as db:
            writer_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            writer_started.set()
            mutate(db, case, helper)

    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(read)
        assert read_ready.wait(5)
        writer = pool.submit(revoke)
        try:
            assert writer_started.wait(5)
            wait_for_advisory(postgres_engine, writer_pid[0])
            assert not writer.done()
        finally:
            release_read.set()
        assert reader.result(timeout=5).status == 200
        writer.result(timeout=5)
    assert (
        case["client"].get(f"/api/v1/work/workspaces/{case['workspace_id']}/status").status_code
        == 404
    )


@pytest.mark.parametrize("helper", [False, True])
def test_writer_first_committed_revocation_returns_no_workspace(
    authority_case, postgres_engine, helper
):
    case = authority_case
    write_ready, release_write, reader_started = Event(), Event(), Event()
    reader_pid = []

    def revoke():
        with case["admin"].begin() as db:
            mutate(db, case, helper)
            write_ready.set()
            assert release_write.wait(5)

    def read():
        with case["runtime"].begin() as db:
            reader_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            reader_started.set()
            return work_access.inspect_work(db, case["token"], case["workspace_id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(revoke)
        assert write_ready.wait(5)
        reader = pool.submit(read)
        try:
            assert reader_started.wait(5)
            wait_for_advisory(postgres_engine, reader_pid[0])
        finally:
            release_write.set()
        writer.result(timeout=5)
        result = reader.result(timeout=5)
    assert result.status == 404 and "workspace" not in result.payload


@pytest.mark.parametrize("change", ["expiry", "user", "session"])
def test_expiry_or_identity_revocation_during_registry_wait_is_rechecked(
    authority_case, postgres_engine, monkeypatch, change
):
    case = authority_case
    now = identity.now_utc()
    clock = [now]
    monkeypatch.setattr(identity, "now_utc", lambda: clock[0])
    if change == "expiry":
        with case["admin"].begin() as db:
            session = db.scalar(
                select(AuthSession).where(AuthSession.token_hash == identity.digest(case["token"]))
            )
            session.expires_at = now + timedelta(seconds=1)
    write_ready, release_write, reader_started = Event(), Event(), Event()
    reader_pid = []

    def writer():
        with case["admin"].begin() as db:
            db.execute(
                text("UPDATE work_workspaces SET is_active=is_active WHERE id=:id"),
                {"id": case["workspace_id"]},
            )
            write_ready.set()
            assert release_write.wait(5)

    def reader():
        with case["runtime"].begin() as db:
            reader_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            reader_started.set()
            # Retain a pre-wait ORM object to prove work auth refreshes cached identity.
            cached = (
                db.scalar(
                    select(AuthSession).where(
                        AuthSession.token_hash == identity.digest(case["token"])
                    )
                )
                if change == "session"
                else None
            )
            result = work_access.inspect_work(db, case["token"], case["workspace_id"])
            if cached is not None:
                assert cached.revoked_at is not None
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        write_future = pool.submit(writer)
        assert write_ready.wait(5)
        read_future = pool.submit(reader)
        try:
            assert reader_started.wait(5)
            wait_for_advisory(postgres_engine, reader_pid[0])
            if change == "expiry":
                clock[0] = now + timedelta(seconds=2)
            else:
                with case["admin"].begin() as db:
                    if change == "user":
                        user = db.scalar(
                            select(User).where(User.id == case["user_id"]).with_for_update()
                        )
                        set_active(db, user, False)
                    else:
                        db.execute(
                            text(
                                "UPDATE auth_sessions SET revoked_at=now() WHERE token_hash=:hash"
                            ),
                            {"hash": identity.digest(case["token"])},
                        )
        finally:
            release_write.set()
        write_future.result(timeout=5)
        result = read_future.result(timeout=5)
    assert result.status == 401 and "workspace" not in result.payload


def test_lock_timeout_returns_sanitized_unavailability_without_payload(authority_case):
    case = authority_case
    ready, release = Event(), Event()

    def writer():
        with case["admin"].begin() as db:
            mutate(db, case, False)
            ready.set()
            assert release.wait(8)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        assert ready.wait(5)
        try:
            started = monotonic()
            response = case["client"].get(f"/api/v1/work/workspaces/{case['workspace_id']}/status")
            assert response.status_code == 503 and response.json() == {
                "detail": "Identity service unavailable"
            }
            assert monotonic() - started < 5
        finally:
            release.set()
        future.result(timeout=5)


def test_stale_snapshot_isolation_is_rejected(authority_case, runtime_engine):
    maker = sessionmaker(bind=runtime_engine.execution_options(isolation_level="REPEATABLE READ"))
    with pytest.raises(SQLAlchemyError), maker.begin() as db:
        work_access.inspect_work(db, authority_case["token"], authority_case["workspace_id"])


def test_registry_truncate_is_forbidden_and_trigger_not_public(postgres_engine, runtime_engine):
    with pytest.raises(DBAPIError) as failure, postgres_engine.begin() as connection:
        connection.execute(text("TRUNCATE work_access_grants"))
    assert failure.value.orig.sqlstate == "23514"
    with runtime_engine.begin() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT has_function_privilege(current_user,'public.butler_work_registry_barrier()','EXECUTE')"
                )
            )
            is False
        )
