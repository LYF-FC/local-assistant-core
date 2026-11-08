"""Real dual-connection broker with separate restricted workspace logins, synthetic only."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import UUID

import psycopg
import pytest
from conftest import client_for
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from test_work_authority_postgres import wait_for_advisory
from work_storage_helpers import PASSWORD, connect, insert

from app import identity, work_read
from app.config import settings
from app.main import app
from app.models import AuthSession, User
from app.work_manage import administer

pytestmark = pytest.mark.integration


@pytest.fixture
def broker_case(scenario, storage_case, runtime_engine):
    client, headers, _, admin, user_id = scenario
    with admin.begin() as db:
        slug = db.get(User, user_id).slug
        administer(db, "grant", storage_case["a"]["slug"], slug)
    engines = {
        storage_case[letter]["workspace"]: work_read.workspace_engine(
            make_url(settings.database_url).set(
                username=storage_case[letter]["login"], password=PASSWORD
            )
        )
        for letter in ("a", "b")
    }
    mapping = work_read.WorkspaceEngines(engines)
    app.dependency_overrides[work_read.get_work_engines] = lambda: mapping
    case = {
        "client": client,
        "headers": headers,
        "admin": admin,
        "user_id": user_id,
        "user_slug": slug,
        "storage": storage_case,
        "engines": engines,
        "identity_maker": sessionmaker(bind=runtime_engine, expire_on_commit=False),
    }
    try:
        yield case
    finally:
        app.dependency_overrides.pop(work_read.get_work_engines, None)
        for engine in engines.values():
            engine.dispose()


def request(case, workspace=None, limit=10, client=None):
    identifier = workspace or case["storage"]["a"]["workspace"]
    return (client or case["client"]).post(
        f"/api/v1/work/workspaces/{identifier}/validation-read",
        headers=case["headers"],
        json={"limit": limit},
    )


def attempts(case):
    with connect() as db:
        return db.execute(
            "SELECT requested_by,session_id,event_type,record_count,record_ids,reason_code FROM work.read_attempts WHERE workspace_id=%s ORDER BY occurred_at,id",
            (case["storage"]["a"]["workspace"],),
        ).fetchall()


def test_broker_reads_only_current_workspace_bounds_and_audits_without_markers(broker_case):
    case = broker_case
    ids = [insert(case["storage"], marker=f"synthetic:item-{n}") for n in range(3)]
    insert(case["storage"], "b", marker="synthetic:peer-secret")
    response = request(case, limit=2)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["has_more"] is True and len(data["items"]) == 2
    assert {UUID(row["id"]) for row in data["items"]} <= set(ids)
    assert "peer-secret" not in response.text
    assert data["mode"] == "synthetic_storage_preview" and data["ingestion_allowed"] is False
    rows = attempts(case)
    assert (
        len(rows) == 1
        and rows[0][0] == case["user_id"]
        and rows[0][2:4] == ("validation.read_prepared", 2)
    )
    assert rows[0][4] == [row["id"] for row in data["items"]]
    assert "synthetic:item" not in str(rows)
    with case["engines"][case["storage"]["a"]["workspace"]].connect() as connection:
        assert (
            connection.execute(text("SELECT session_user,current_user")).one()
            == (case["storage"]["a"]["login"],) * 2
        )


def test_unassigned_workspace_never_checks_out_its_connection(broker_case):
    case = broker_case
    engine = case["engines"][case["storage"]["b"]["workspace"]]
    called = []
    event.listen(engine, "checkout", lambda *args: called.append(True))
    assert request(case, workspace=case["storage"]["b"]["workspace"]).status_code == 404
    assert called == [] and attempts(case) == []


@pytest.mark.parametrize(
    "kind",
    [
        "peer_mapping",
        "family",
        "administrator",
        "different_database",
        "repeatable_read",
        "unbounded_pool",
    ],
)
def test_mislabeled_privileged_or_wrong_target_connection_fails_closed(
    broker_case, runtime_engine, postgres_engine, kind
):
    case = broker_case
    target = case["storage"]["a"]["workspace"]
    extra = None
    if kind == "peer_mapping":
        engine = case["engines"][case["storage"]["b"]["workspace"]]
    elif kind == "family":
        extra = work_read.workspace_engine(runtime_engine.url)
        engine = extra
    elif kind == "administrator":
        extra = work_read.workspace_engine(postgres_engine.url)
        engine = extra
    elif kind == "repeatable_read":
        engine = case["engines"][target].execution_options(isolation_level="REPEATABLE READ")
    elif kind == "unbounded_pool":
        extra = create_engine(case["engines"][target].url)
        engine = extra
    else:
        extra = create_engine(
            make_url(settings.database_url).set(database="butler_test_wrong_target")
        )
        engine = extra
    app.dependency_overrides[work_read.get_work_engines] = lambda: work_read.WorkspaceEngines(
        {target: engine}
    )
    try:
        response = request(case)
        assert response.status_code == 503 and "items" not in response.json()
        assert attempts(case) == []
    finally:
        if extra is not None:
            extra.dispose()


def test_work_audit_failure_rolls_back_and_releases_no_rows(broker_case):
    case = broker_case
    insert(case["storage"])
    with connect() as db:
        db.execute(
            "ALTER TABLE work.read_attempts ADD CONSTRAINT synthetic_fail_read_audit CHECK(false) NOT VALID"
        )
    try:
        assert request(case).status_code == 503
        assert attempts(case) == []
    finally:
        with connect() as db:
            db.execute("ALTER TABLE work.read_attempts DROP CONSTRAINT synthetic_fail_read_audit")


def test_work_commit_failure_releases_no_rows(broker_case):
    case = broker_case
    engine = case["engines"][case["storage"]["a"]["workspace"]]

    def fail(connection):
        raise SQLAlchemyError("synthetic commit failure")

    event.listen(engine, "commit", fail)
    try:
        response = request(case)
        assert response.status_code == 503 and "items" not in response.json()
    finally:
        event.remove(engine, "commit", fail)
    assert attempts(case) == []


def test_identity_commit_failure_can_leave_prepared_audit_but_no_payload(broker_case):
    case = broker_case
    maker = case["identity_maker"]

    def fail(session):
        raise SQLAlchemyError("synthetic identity commit failure")

    event.listen(maker, "before_commit", fail)
    try:
        with client_for(maker) as client:
            client.cookies.update(case["client"].cookies)
            response = request(case, client=client)
        assert response.status_code == 503 and "items" not in response.json()
        rows = attempts(case)
        assert len(rows) == 1 and rows[0][2] == "validation.read_prepared"
    finally:
        event.remove(maker, "before_commit", fail)


def test_expiry_after_storage_query_is_denied_and_audited(broker_case, monkeypatch):
    case = broker_case
    now = identity.now_utc()
    clock = [now]
    token = case["client"].cookies.get(identity.COOKIE)
    with case["admin"].begin() as db:
        session = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == identity.digest(token))
        )
        session.expires_at = now + timedelta(seconds=1)
    monkeypatch.setattr(identity, "now_utc", lambda: clock[0])
    engine = case["engines"][case["storage"]["a"]["workspace"]]

    def advance(connection, cursor, statement, parameters, context, executemany):
        if "SELECT id,marker,created_at FROM work.validation_records" in statement:
            clock[0] = now + timedelta(seconds=2)

    event.listen(engine, "after_cursor_execute", advance)
    try:
        response = request(case)
        assert response.status_code == 401 and "items" not in response.json()
        assert attempts(case)[0][2:] == ("validation.read_denied", 0, [], "authority_expired")
    finally:
        event.remove(engine, "after_cursor_execute", advance)


def test_reader_retains_grant_until_work_and_identity_audit_commit(broker_case, postgres_engine):
    case = broker_case
    work_ready, release_work, identity_ready, release_identity, writer_started = (
        Event() for _ in range(5)
    )
    engine = case["engines"][case["storage"]["a"]["workspace"]]
    maker = case["identity_maker"]
    pid = []

    def hold_work(connection):
        work_ready.set()
        assert release_work.wait(5)

    def hold_identity(session):
        identity_ready.set()
        assert release_identity.wait(5)

    event.listen(engine, "commit", hold_work)
    event.listen(maker, "before_commit", hold_identity)

    def revoke():
        with case["admin"].begin() as db:
            pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            writer_started.set()
            administer(db, "revoke", case["storage"]["a"]["slug"], case["user_slug"])

    try:
        with client_for(maker) as client:
            client.cookies.update(case["client"].cookies)
            with ThreadPoolExecutor(max_workers=2) as pool:
                reader = pool.submit(request, case, client=client)
                assert work_ready.wait(5)
                writer = pool.submit(revoke)
                try:
                    assert writer_started.wait(5)
                    wait_for_advisory(postgres_engine, pid[0])
                    release_work.set()
                    assert identity_ready.wait(5)
                    wait_for_advisory(postgres_engine, pid[0])
                    assert not writer.done()
                finally:
                    release_work.set()
                    release_identity.set()
                assert reader.result(timeout=5).status_code == 200
                writer.result(timeout=5)
            assert request(case, client=client).status_code == 404
    finally:
        release_work.set()
        release_identity.set()
        event.remove(engine, "commit", hold_work)
        event.remove(maker, "before_commit", hold_identity)


def test_expiry_during_connection_checks_never_reads_markers(broker_case, monkeypatch):
    case = broker_case
    now = identity.now_utc()
    clock = [now]
    with case["admin"].begin() as db:
        row = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash
                == identity.digest(case["client"].cookies.get(identity.COOKIE))
            )
        )
        row.expires_at = now + timedelta(seconds=1)
    monkeypatch.setattr(identity, "now_utc", lambda: clock[0])
    engine = case["engines"][case["storage"]["a"]["workspace"]]
    reads = []

    def expire(connection, cursor, statement, parameters, context, executemany):
        if "SELECT id FROM work.active_workspace" in statement:
            clock[0] = now + timedelta(seconds=2)
        if "SELECT id,marker,created_at FROM work.validation_records" in statement:
            reads.append(True)

    event.listen(engine, "after_cursor_execute", expire)
    try:
        assert request(case).status_code == 401
        assert reads == [] and attempts(case)[0][2] == "validation.read_denied"
    finally:
        event.remove(engine, "after_cursor_execute", expire)


def test_pooled_session_role_residue_is_rejected_and_connection_discarded(broker_case):
    case = broker_case
    target = case["storage"]["a"]
    engine = case["engines"][target["workspace"]]
    with engine.begin() as connection:
        connection.exec_driver_sql("SET ROLE " + target["role"])
    response = request(case)
    assert response.status_code == 503 and attempts(case) == []
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT session_user,current_user")).one()
            == (target["login"],) * 2
        )


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
def test_read_audit_is_immutable_to_operator(broker_case, operation):
    assert request(broker_case).status_code == 200
    statement = {
        "UPDATE": "UPDATE work.read_attempts SET record_count=record_count",
        "DELETE": "DELETE FROM work.read_attempts",
        "TRUNCATE": "TRUNCATE work.read_attempts",
    }[operation]
    with pytest.raises(psycopg.Error), connect() as db:
        db.execute(statement)


def test_login_with_family_column_grant_is_rejected(broker_case):
    case = broker_case
    login = case["storage"]["a"]["login"]
    from psycopg import sql

    with connect() as db:
        db.execute(
            sql.SQL("GRANT SELECT(content) ON public.memory_records TO {}").format(
                sql.Identifier(login)
            )
        )
    try:
        response = request(case)
        assert response.status_code == 503 and attempts(case) == []
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("REVOKE SELECT(content) ON public.memory_records FROM {}").format(
                    sql.Identifier(login)
                )
            )


def test_each_authorized_workspace_keeps_its_own_read_audit(broker_case):
    case = broker_case
    assert request(case).status_code == 200
    with case["admin"].begin() as db:
        administer(db, "grant", case["storage"]["b"]["slug"], case["user_slug"])
    assert request(case, workspace=case["storage"]["b"]["workspace"]).status_code == 200
    for letter in ("a", "b"):
        with case["storage"]["session"](letter) as db:
            assert db.execute(
                "SELECT workspace_id,requested_by,event_type FROM work.read_attempts"
            ).fetchall() == [
                (case["storage"][letter]["workspace"], case["user_id"], "validation.read_prepared")
            ]


def test_expiry_at_work_commit_leaves_prepared_attempt_but_no_rows(broker_case, monkeypatch):
    case = broker_case
    insert(case["storage"])
    now = identity.now_utc()
    clock = [now]
    with case["admin"].begin() as db:
        row = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash
                == identity.digest(case["client"].cookies.get(identity.COOKIE))
            )
        )
        row.expires_at = now + timedelta(seconds=1)
    monkeypatch.setattr(identity, "now_utc", lambda: clock[0])
    engine = case["engines"][case["storage"]["a"]["workspace"]]

    def expire(connection):
        clock[0] = now + timedelta(seconds=2)

    event.listen(engine, "commit", expire)
    try:
        response = request(case)
        assert response.status_code == 401 and "items" not in response.json()
        rows = attempts(case)
        assert len(rows) == 1 and rows[0][2:4] == ("validation.read_prepared", 1)
    finally:
        event.remove(engine, "commit", expire)
