"""Trusted credential lifecycle against actual PostgreSQL authentication, synthetic only."""

from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url
from work_credential_helpers import FIRST, SECOND, apply, audits
from work_storage_helpers import connect

from app import work_credentials as credentials
from app.config import settings
from app.work_read import restricted_identity, workspace_engine

pytestmark = pytest.mark.integration


def test_bootstrap_rotation_uses_real_password_auth_and_secret_free_audit(credential_case):
    case = credential_case
    assert apply(case) is None
    with connect(case["managed"], FIRST) as db:
        db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(case["role"])))
        assert db.execute("SELECT id FROM work.active_workspace").fetchall() == []
        assert db.execute("SELECT marker FROM work.validation_records").fetchall() == []
    apply(case, "rotate", SECOND)
    with pytest.raises(psycopg.OperationalError):
        connect(case["managed"], FIRST)
    with connect(case["managed"], SECOND) as db:
        assert db.execute("SELECT session_user").fetchone()[0] == case["managed"]
    with connect() as db:
        verifier, remaining = db.execute(
            "SELECT rolpassword,rolvaliduntil-clock_timestamp() FROM pg_authid WHERE rolname=%s",
            (case["managed"],),
        ).fetchone()
        assert verifier.startswith("SCRAM-SHA-256$")
        assert 23 * 3600 < remaining.total_seconds() <= 24 * 3600
    assert audits(case) == [
        ("admin.work_credential_bootstrap", {}, {}),
        ("admin.work_credential_rotate", {}, {}),
    ]


def test_new_login_matches_broker_profile_and_cannot_reach_peer_or_family(credential_case):
    case = credential_case
    apply(case)
    with connect() as db:
        db.execute("UPDATE work_workspaces SET is_active=true WHERE id=%s", (case["workspace"],))
    engine = workspace_engine(
        make_url(settings.database_url).set(username=case["managed"], password=FIRST)
    )
    try:
        with engine.begin() as db:
            restricted_identity(db, case["oid"], case["workspace"])
            assert db.exec_driver_sql("SELECT id FROM work.active_workspace").all() == [
                (case["workspace"],)
            ]
    finally:
        engine.dispose()
    for query in ["SELECT * FROM public.auth_credentials", "SELECT * FROM public.memory_records"]:
        with pytest.raises(psycopg.Error), connect(case["managed"], FIRST) as db:
            db.execute(query)
    with pytest.raises(psycopg.Error), connect(case["managed"], FIRST) as db:
        db.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(case["peer_role"])))


def test_revoke_is_repeatable_clears_password_and_membership_without_enabling(credential_case):
    case = credential_case
    apply(case)
    apply(case, "revoke")
    apply(case, "revoke")
    with connect() as db:
        assert db.execute(
            "SELECT rolcanlogin,rolpassword FROM pg_authid WHERE rolname=%s", (case["managed"],)
        ).fetchone() == (False, None)
        assert (
            db.execute(
                "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)",
                (case["managed"],),
            ).fetchone()[0]
            == 0
        )
        assert db.execute(
            "SELECT is_active FROM work_workspaces WHERE id=%s", (case["workspace"],)
        ).fetchone() == (False,)
    with pytest.raises(psycopg.OperationalError):
        connect(case["managed"], FIRST)
    with pytest.raises(ValueError):
        apply(case, "rotate", SECOND)


@pytest.mark.parametrize("action", ["bootstrap", "rotate", "revoke"])
def test_active_workspace_refuses_credential_changes(credential_case, action):
    case = credential_case
    if action != "bootstrap":
        apply(case)
    before = audits(case)
    with connect() as db:
        db.execute("UPDATE work_workspaces SET is_active=true WHERE id=%s", (case["workspace"],))
    with pytest.raises(ValueError, match="Disabled synthetic"):
        apply(case, action)
    assert audits(case) == before


@pytest.mark.parametrize("action", ["rotate", "revoke"])
def test_existing_session_refuses_change_and_inactive_workspace_blocks_cached_role(
    credential_case, action
):
    case = credential_case
    apply(case)
    with connect(case["managed"], FIRST) as session:
        session.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(case["role"])))
        with pytest.raises(ValueError, match="Drain"):
            apply(case, action, SECOND)
        assert session.execute("SELECT marker FROM work.validation_records").fetchall() == []
    assert len(audits(case)) == 1


@pytest.mark.parametrize("drift", ["inherit", "membership", "table", "column", "settings"])
def test_role_drift_is_refused_without_repair(credential_case, drift):
    case = credential_case
    apply(case)
    role = sql.Identifier(case["managed"])
    statements = {
        "inherit": sql.SQL("ALTER ROLE {} INHERIT").format(role),
        "membership": sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
            sql.Identifier(case["peer_role"]), role
        ),
        "table": sql.SQL("GRANT SELECT ON work.validation_records TO {}").format(role),
        "column": sql.SQL("GRANT SELECT (password_hash) ON public.auth_credentials TO {}").format(
            role
        ),
        "settings": sql.SQL("ALTER ROLE {} SET role TO {}").format(
            role, sql.Identifier(case["role"])
        ),
    }
    with connect() as db:
        db.execute(statements[drift])
    for action in ("rotate", "revoke"):
        with pytest.raises(ValueError, match="Unreviewed"):
            apply(case, action, SECOND)
    assert len(audits(case)) == 1


@pytest.mark.parametrize("action", ["bootstrap", "rotate", "revoke"])
def test_audit_failure_rolls_back_credential_ddl(credential_case, action):
    case = credential_case
    if action != "bootstrap":
        apply(case)
    constraint = "synthetic_credential_audit_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE audit_events ADD CONSTRAINT {} CHECK (event_type NOT LIKE 'admin.work_credential_%') NOT VALID"
            ).format(sql.Identifier(constraint))
        )
    try:
        with pytest.raises(psycopg.Error):
            apply(case, action, SECOND)
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE audit_events DROP CONSTRAINT {}").format(
                    sql.Identifier(constraint)
                )
            )
    if action == "bootstrap":
        with connect() as db:
            assert (
                db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (case["managed"],)).fetchone()
                is None
            )
    else:
        with connect(case["managed"], FIRST) as db:
            assert db.execute("SELECT 1").fetchone() == (1,)
        with pytest.raises(psycopg.OperationalError):
            connect(case["managed"], SECOND)


def test_reserved_collision_never_overwrites_existing_login(credential_case):
    case = credential_case
    apply(case)
    with pytest.raises(ValueError, match="already exists"):
        apply(case, "bootstrap", SECOND)
    with connect(case["managed"], FIRST) as db:
        assert db.execute("SELECT 1").fetchone() == (1,)
    assert len(audits(case)) == 1


def test_plaintext_secret_never_enters_executed_sql(credential_case):
    statements = []

    class RecordingCursor(psycopg.Cursor):
        def execute(self, query, params=None, **kwargs):
            statements.append(
                query.as_string(self.connection) if isinstance(query, sql.Composable) else query
            )
            assert params is None or FIRST not in repr(params)
            return super().execute(query, params, **kwargs)

    with connect() as db:
        db.cursor_factory = RecordingCursor
        credentials.administer(db, "bootstrap", credential_case["slug"], FIRST)
    assert all(FIRST not in statement for statement in statements)
    assert any("PASSWORD 'SCRAM-SHA-256$" in statement for statement in statements)


def test_expired_password_refuses_new_authentication(credential_case):
    case = credential_case
    apply(case)
    with connect() as db:
        db.execute(
            sql.SQL("ALTER ROLE {} VALID UNTIL '2000-01-01'").format(
                sql.Identifier(case["managed"])
            )
        )
    with pytest.raises(psycopg.OperationalError):
        connect(case["managed"], FIRST)
