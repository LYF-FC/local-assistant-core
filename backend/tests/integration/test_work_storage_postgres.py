"""Real restricted login sessions: schema/role/RLS/workspace isolation, synthetic only."""

from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from work_storage_helpers import connect, insert

from app.config import settings
from app.models import WorkWorkspace
from app.work_storage import provision

pytestmark = pytest.mark.integration


def test_same_record_id_is_independent_and_reads_audit_are_workspace_bound(storage_case):
    case = storage_case
    identifier = uuid4()
    insert(case, "a", identifier, "synthetic:alpha")
    insert(case, "b", identifier, "synthetic:bravo")
    with case["session"]() as db:
        assert db.execute("SELECT session_user,current_user").fetchone() == (
            case["a"]["login"],
            case["a"]["role"],
        )
        assert db.execute("SELECT id FROM work.active_workspace").fetchall() == [
            (case["a"]["workspace"],)
        ]
        assert db.execute("SELECT id,marker FROM work.validation_records").fetchall() == [
            (identifier, "synthetic:alpha")
        ]
        assert db.execute(
            "SELECT workspace_id,record_id,initiator_role,event_type FROM work.validation_audit"
        ).fetchall() == [
            (case["a"]["workspace"], identifier, case["a"]["role"], "validation.created")
        ]
        db.execute(
            "SELECT set_config('butler.workspace_id',%s,true)", (str(case["b"]["workspace"]),)
        )
        assert db.execute("SELECT marker FROM work.validation_records").fetchall() == [
            ("synthetic:alpha",)
        ]
    with connect() as db:
        row = db.execute(
            "SELECT rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s",
            (case["a"]["role"],),
        ).fetchone()
        assert row == (False,) * 7


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM public.memory_records",
        "SELECT * FROM public.auth_credentials",
        "SELECT * FROM public.work_access_grants",
        "SELECT * FROM public.work_workspaces",
        "SELECT * FROM public.audit_events",
        "CREATE TABLE public.synthetic_forbidden (id int)",
        "CREATE TABLE work.synthetic_forbidden (id int)",
        "CREATE TEMP TABLE synthetic_forbidden (id int)",
        "ALTER TABLE work.validation_records DISABLE ROW LEVEL SECURITY",
        "TRUNCATE work.validation_records",
        "DELETE FROM work.validation_records",
        "UPDATE work.validation_records SET marker='synthetic:tamper'",
        "INSERT INTO work.validation_audit DEFAULT VALUES",
    ],
)
def test_work_role_cannot_reach_family_admin_or_mutate_history(storage_case, statement):
    with pytest.raises(psycopg.Error), storage_case["session"]() as db:
        db.execute(statement)


def test_family_runtime_cannot_read_write_work_or_assume_role(storage_case, runtime_engine):
    for statement in [
        "SELECT * FROM work.validation_records",
        "SELECT * FROM work.validation_audit",
        "INSERT INTO work.validation_records DEFAULT VALUES",
        "SET ROLE " + storage_case["a"]["role"],
    ]:
        with pytest.raises(DBAPIError), runtime_engine.begin() as db:
            db.execute(text(statement))


def test_actual_login_cannot_switch_workspace_family_or_owner(storage_case):
    case = storage_case
    for role in [case["b"]["role"], "butler_runtime", settings.postgres_user]:
        with pytest.raises(psycopg.Error), case["session"]() as db:
            db.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
    with pytest.raises(psycopg.Error), case["session"]() as db:
        db.execute(
            sql.SQL("SET SESSION AUTHORIZATION {}").format(sql.Identifier(settings.postgres_user))
        )
    with case["session"]() as db:
        db.execute("RESET ROLE")
        assert db.execute("SELECT current_user").fetchone()[0] == case["a"]["login"]
        with pytest.raises(psycopg.Error):
            db.execute("SELECT * FROM work.validation_records")
        db.rollback()


def test_cross_workspace_insert_row_security_off_and_timestamp_forgery_fail(storage_case):
    case = storage_case
    with pytest.raises(psycopg.Error), case["session"]() as db:
        db.execute(
            "INSERT INTO work.validation_records (workspace_id,id,marker) VALUES (%s,%s,'synthetic:cross')",
            (case["b"]["workspace"], uuid4()),
        )
    with pytest.raises(psycopg.Error), case["session"]() as db:
        db.execute("SET LOCAL row_security=off")
        db.execute("SELECT * FROM work.validation_records")
    with pytest.raises(psycopg.Error), case["session"]() as db:
        db.execute(
            "INSERT INTO work.validation_records (workspace_id,id,marker,created_at) VALUES (%s,%s,'synthetic:time',now())",
            (case["a"]["workspace"], uuid4()),
        )


def test_workspace_disablement_applies_to_next_statement(storage_case):
    case = storage_case
    insert(case)
    with case["session"]() as db:
        assert len(db.execute("SELECT id FROM work.validation_records").fetchall()) == 1
        with case["maker"].begin() as admin:
            workspace = admin.get(WorkWorkspace, case["a"]["workspace"])
            workspace.is_active = False
        assert db.execute("SELECT * FROM work.validation_records").fetchall() == []
        assert db.execute("SELECT * FROM work.validation_audit").fetchall() == []
    with pytest.raises(psycopg.Error):
        insert(case)


def test_invalid_marker_and_audit_failure_roll_back_the_record(storage_case):
    case = storage_case
    for marker in ["not-synthetic", "synthetic:" + "x" * 257]:
        with pytest.raises(psycopg.Error):
            insert(case, marker=marker)
    with connect() as admin:
        admin.execute(
            "ALTER TABLE work.validation_audit ADD CONSTRAINT synthetic_audit_failure CHECK(false) NOT VALID"
        )
    identifier = uuid4()
    try:
        with pytest.raises(psycopg.Error):
            insert(case, identifier=identifier)
    finally:
        with connect() as admin:
            admin.execute(
                "ALTER TABLE work.validation_audit DROP CONSTRAINT synthetic_audit_failure"
            )
    with case["session"]() as db:
        assert db.execute("SELECT * FROM work.validation_records").fetchall() == []
        assert db.execute("SELECT * FROM work.validation_audit").fetchall() == []


@pytest.mark.parametrize("table", ["validation_records", "validation_audit"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
def test_append_only_guard_also_applies_to_operator(storage_case, table, operation):
    insert(storage_case)
    field = "marker=marker" if table == "validation_records" else "event_type=event_type"
    statement = {
        "UPDATE": f"UPDATE work.{table} SET {field}",
        "DELETE": f"DELETE FROM work.{table}",
        "TRUNCATE": f"TRUNCATE work.{table}",
    }[operation]
    with pytest.raises(psycopg.Error), connect() as admin:
        admin.execute(statement)


@pytest.mark.parametrize("unsafe", ["login", "membership", "ownership", "database_public"])
def test_provision_rejects_unsafe_role_or_platform(storage_case, unsafe):
    case = storage_case
    with pytest.raises(ValueError), connect() as admin:
        role = sql.Identifier(case["a"]["role"])
        if unsafe == "database_public":
            admin.execute(
                sql.SQL("GRANT TEMPORARY ON DATABASE {} TO PUBLIC").format(
                    sql.Identifier(settings.postgres_db)
                )
            )
        elif unsafe == "login":
            admin.execute(sql.SQL("ALTER ROLE {} LOGIN").format(role))
        elif unsafe == "membership":
            admin.execute(sql.SQL("GRANT butler_runtime TO {}").format(role))
        else:
            admin.execute(
                sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                    sql.Identifier("synthetic_" + uuid4().hex), role
                )
            )
        provision(admin, case["a"]["slug"])


def test_role_reprovision_is_idempotent_and_resets_accidental_column_grants(storage_case):
    case = storage_case
    with connect() as admin:
        admin.execute(
            sql.SQL("GRANT UPDATE(marker) ON work.validation_records TO {}").format(
                sql.Identifier(case["a"]["role"])
            )
        )
        admin.execute(
            sql.SQL("GRANT CREATE,TEMPORARY ON DATABASE {} TO {}").format(
                sql.Identifier(settings.postgres_db), sql.Identifier(case["a"]["role"])
            )
        )
        assert provision(admin, case["a"]["slug"]) == case["a"]["role"]
        assert (
            admin.execute(
                "SELECT has_database_privilege(%s,current_database(),'CREATE,TEMPORARY')",
                (case["a"]["role"],),
            ).fetchone()[0]
            is False
        )
        assert (
            admin.execute(
                "SELECT has_column_privilege(%s,'work.validation_records','marker','UPDATE')",
                (case["a"]["role"],),
            ).fetchone()[0]
            is False
        )
    insert(case)


def test_new_tables_have_no_implicit_storage_grants(storage_case):
    with connect() as admin:
        admin.execute("CREATE TABLE work.synthetic_future_table (id integer)")
    try:
        with pytest.raises(psycopg.Error), storage_case["session"]() as db:
            db.execute("SELECT * FROM work.synthetic_future_table")
    finally:
        with connect() as admin:
            admin.execute("DROP TABLE work.synthetic_future_table")
