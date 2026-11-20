"""Disposable PostgreSQL checks; no restored target is activated."""

from uuid import uuid4

import pytest
from conftest import require_disposable_postgres
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url

from app.config import settings
from app.recovery_staging_binding import inspect_restored_binding

pytestmark = pytest.mark.integration
INSTALLATION = "11111111-1111-4111-8111-111111111111"
HEAD = "0038_work_status_audit_category"


@pytest.fixture
def restored_engine():
    require_disposable_postgres()
    name = "butler_test_staging_" + uuid4().hex
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = create_engine(make_url(settings.database_url).set(database=name))
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        admin.dispose()


def metadata(engine):
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE installation_config (id integer, installation_id uuid)")
        )
        connection.execute(text("CREATE TABLE alembic_version (version_num text)"))
        connection.execute(
            text("INSERT INTO installation_config VALUES (1, :installation)"),
            {"installation": INSTALLATION},
        )
        connection.execute(text("INSERT INTO alembic_version VALUES (:head)"), {"head": HEAD})


def inspect(engine, **kwargs):
    with engine.connect() as connection:
        return inspect_restored_binding(
            connection,
            installation_id=kwargs.get("installation_id", INSTALLATION),
            schema_head=kwargs.get("schema_head", HEAD),
        )


def test_exact_singleton_binding_only_reads_and_never_releases_quarantine(restored_engine):
    metadata(restored_engine)
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(restored_engine, "before_cursor_execute", record)
    try:
        report = inspect(restored_engine)
    finally:
        event.remove(restored_engine, "before_cursor_execute", record)
    assert report.binding_valid and report.reasons == ()
    assert report.quarantined and not report.restore_eligible
    assert all(
        statement.upper().startswith(("SELECT ", "SAVEPOINT ", "RELEASE SAVEPOINT "))
        for statement in statements
    )


@pytest.mark.parametrize(
    ("expectations", "reason"),
    [
        (
            {"installation_id": "22222222-2222-4222-8222-222222222222"},
            "restored_installation_mismatch",
        ),
        ({"schema_head": "0037_wrong_expected_head"}, "restored_schema_head_mismatch"),
    ],
)
def test_restored_mismatch_is_blocked(restored_engine, expectations, reason):
    metadata(restored_engine)
    report = inspect(restored_engine, **expectations)
    assert not report.binding_valid and report.reasons == (reason,)
    assert report.quarantined and not report.restore_eligible


@pytest.mark.parametrize(
    "change",
    [
        "DELETE FROM installation_config",
        "UPDATE installation_config SET id=2",
        "INSERT INTO installation_config SELECT * FROM installation_config",
        "DELETE FROM alembic_version",
        "INSERT INTO alembic_version SELECT * FROM alembic_version",
    ],
)
def test_empty_or_multiple_identity_or_heads_never_bind(restored_engine, change):
    metadata(restored_engine)
    with restored_engine.begin() as connection:
        connection.execute(text(change))
    report = inspect(restored_engine)
    assert report.reasons == ("binding_metadata_shape_invalid",)
    assert not report.binding_valid and not report.restore_eligible


@pytest.mark.parametrize("remaining", [None, "installation_config", "alembic_version"])
def test_missing_metadata_is_not_success(restored_engine, remaining):
    if remaining:
        metadata(restored_engine)
        missing = "alembic_version" if remaining == "installation_config" else "installation_config"
        with restored_engine.begin() as connection:
            connection.execute(text(f"DROP TABLE {missing}"))
    report = inspect(restored_engine)
    assert not report.binding_valid and report.reasons == ("binding_metadata_missing",)
    assert report.quarantined and not report.restore_eligible


def test_malformed_metadata_does_not_poison_callers_transaction(restored_engine):
    with restored_engine.begin() as connection:
        connection.execute(text("CREATE TABLE installation_config (wrong integer)"))
        connection.execute(text("CREATE TABLE alembic_version (version_num text)"))
    with restored_engine.begin() as connection:
        report = inspect_restored_binding(
            connection, installation_id=INSTALLATION, schema_head=HEAD
        )
        assert report.reasons == ("binding_metadata_unreadable",)
        assert not report.binding_valid and not report.restore_eligible
        assert connection.scalar(text("SELECT 1")) == 1


@pytest.mark.parametrize(
    "expectations",
    [{"installation_id": "not-a-uuid"}, {"schema_head": "head; DROP TABLE x"}],
)
def test_malformed_expectations_rejected_before_queries(restored_engine, expectations):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(restored_engine, "before_cursor_execute", record)
    try:
        with pytest.raises(ValueError, match="canonical binding expectations"):
            inspect(restored_engine, **expectations)
    finally:
        event.remove(restored_engine, "before_cursor_execute", record)
    assert statements == []


def test_hostile_search_path_cannot_shadow_public_metadata(restored_engine):
    metadata(restored_engine)
    with restored_engine.begin() as connection:
        connection.execute(text("CREATE TEMP TABLE installation_config (wrong text)"))
        connection.execute(text("CREATE TEMP TABLE alembic_version (wrong text)"))
        connection.execute(text("SET LOCAL search_path=pg_temp, public"))
        report = inspect_restored_binding(
            connection, installation_id=INSTALLATION, schema_head=HEAD
        )
        assert report.binding_valid and not report.restore_eligible


@pytest.mark.parametrize("opt_out", ["environment", "database_tests"])
def test_explicit_test_environment_and_database_opt_in_required(
    restored_engine, monkeypatch, opt_out
):
    if opt_out == "environment":
        monkeypatch.setattr(settings, "env", "production")
    else:
        monkeypatch.delenv("BUTLER_RUN_DB_TESTS")
    with pytest.raises(ValueError, match="disposable PostgreSQL test connection"):
        inspect(restored_engine)


def test_non_postgres_connection_is_refused():
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as connection, pytest.raises(ValueError, match="PostgreSQL"):
            inspect_restored_binding(connection, installation_id=INSTALLATION, schema_head=HEAD)
    finally:
        engine.dispose()


def test_non_disposable_database_is_refused(restored_engine, monkeypatch):
    with restored_engine.connect() as connection:
        monkeypatch.setattr(connection, "scalar", lambda statement: "synthetic_wrong_target")
        with pytest.raises(ValueError, match="Disposable test database required"):
            inspect_restored_binding(connection, installation_id=INSTALLATION, schema_head=HEAD)


def test_boolean_identity_id_is_not_integer_one(restored_engine):
    with restored_engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE installation_config (id boolean, installation_id uuid)")
        )
        connection.execute(text("CREATE TABLE alembic_version (version_num text)"))
        connection.execute(
            text("INSERT INTO installation_config VALUES (true, :installation)"),
            {"installation": INSTALLATION},
        )
        connection.execute(text("INSERT INTO alembic_version VALUES (:head)"), {"head": HEAD})
    assert inspect(restored_engine).reasons == ("binding_metadata_shape_invalid",)
