import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import RUNTIME_PASSWORD, SYNTHETIC_PASSWORD, client_for
from psycopg import sql
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from test_installation import apply_preview, call, configure, current, preview

from app import identity
from app.auth_routes import get_db
from app.config import settings
from app.main import app
from app.manage import provision, set_scope
from app.models import AuthSession, InstallationConfig, InstallationRevision, User
from app.runtime_role import configure as configure_role

pytestmark = pytest.mark.integration


def authorized(scenario):
    client, h, _, admin, uid = scenario
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "technical_admin", True)
    return client, h, admin, uid


def changed_template(record):
    languages = (
        ["fr"]
        if record["configuration"] and record["configuration"]["defaults"]["languages"] == ["en"]
        else ["en"]
    )
    return {"schema_version": 1, "defaults": {"languages": languages, "timezone": "UTC"}}


def prepare(scenario):
    client, h, admin, uid = authorized(scenario)
    before = current(client, h)
    row = configure(client, h, before, changed_template(before))
    return client, h, admin, uid, row


def test_runtime_configuration_history_preview_and_sanitized_export(scenario):
    client, h, admin, uid, row = prepare(scenario)
    exported = call(client, h, "export", row, acknowledge_copy_limits=True).json()
    assert set(exported["template"]) == {"schema_version", "defaults"} and row[
        "installation_id"
    ] not in str(exported)
    with admin() as db:
        current_row = db.get(InstallationConfig, 1)
        history = db.scalar(
            select(InstallationRevision).where(InstallationRevision.revision == row["revision"])
        )
        assert (
            str(current_row.installation_id) == row["installation_id"]
            and history.snapshot == row
            and history.actor_id == uid
        )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE installation_config SET installation_id=gen_random_uuid(),revision=revision+1,updated_at=now()",
        "UPDATE installation_config SET revision=revision",
        'UPDATE installation_config SET configuration=configuration || \'{"secret":"synthetic"}\'::jsonb,revision=revision+1,updated_at=now()',
        "UPDATE installation_config SET configuration=jsonb_set(configuration,'{defaults,languages}','[\"en\",\"en\"]'),revision=revision+1,updated_at=now()",
        "DELETE FROM installation_config",
        "TRUNCATE installation_config CASCADE",
        "UPDATE installation_revisions SET snapshot='{}'::jsonb",
        "DELETE FROM installation_revisions",
    ],
)
def test_runtime_identity_allowlist_and_history_guards(scenario, runtime_engine, statement):
    prepare(scenario)
    with pytest.raises(DBAPIError), runtime_engine.begin() as db:
        db.execute(text(statement))


def test_owner_sql_cannot_delete_root_or_rewrite_history(scenario):
    _, _, admin, _, _ = prepare(scenario)
    for statement in (
        "DELETE FROM installation_config",
        "UPDATE installation_revisions SET snapshot='{}'::jsonb",
    ):
        with pytest.raises(DBAPIError), admin.begin() as db:
            db.execute(text(statement))


def test_actual_concurrent_apply_has_one_revision_and_one_conflict(scenario):
    client, h, admin, _, row = prepare(scenario)
    p = preview(client, h, row, changed_template(row))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            future.result(timeout=5)
            for future in [pool.submit(apply_preview, client, h, p) for _ in range(2)]
        ]
    assert sorted(r.status_code for r in results) == [200, 409]
    with admin() as db:
        assert db.get(InstallationConfig, 1).revision == row["revision"] + 1


def wait_for_root_lock(admin):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        with admin() as db:
            if db.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%installation_config%FOR %'"
                )
            ):
                return
        time.sleep(0.02)
    raise AssertionError("Request did not reach actual installation lock wait")


@pytest.mark.parametrize("operation", ["read", "preview", "apply", "history", "export"])
def test_session_expiry_after_actual_installation_wait(scenario, monkeypatch, operation):
    client, h, admin, uid, row = prepare(scenario)
    p = preview(client, h, row, changed_template(row))
    with admin() as db:
        expiry = db.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == uid))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(
                select(InstallationConfig).where(InstallationConfig.id == 1).with_for_update()
            )
            pending = (
                pool.submit(apply_preview, client, h, p)
                if operation == "apply"
                else pool.submit(
                    call,
                    client,
                    h,
                    operation,
                    row,
                    **(
                        {"template": p["template"]}
                        if operation == "preview"
                        else {"acknowledge_copy_limits": True}
                        if operation == "export"
                        else {}
                    ),
                )
            )
            wait_for_root_lock(admin)
            monkeypatch.setattr(
                identity, "now_utc", lambda: identity.aware(expiry) + timedelta(seconds=1)
            )
        assert pending.result(timeout=5).status_code == 401
    with admin() as db:
        assert db.get(InstallationConfig, 1).revision == row["revision"]


def test_actual_audit_failure_rolls_back_current_and_history(scenario, runtime_engine):
    client, h, admin, _, row = prepare(scenario)
    p = preview(client, h, row, changed_template(row))

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic config audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        assert apply_preview(client, h, p).status_code == 503
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert db.get(InstallationConfig, 1).revision == row["revision"]
        assert (
            db.scalar(
                select(InstallationRevision).where(
                    InstallationRevision.revision == row["revision"] + 1
                )
            )
            is None
        )


def test_two_actual_configuration_databases_mint_distinct_identity_and_refuse_foreign_session(
    scenario, postgres_engine
):
    client, h, _, _, first = prepare(scenario)
    first_cookie = client.cookies.get(identity.COOKIE)
    template = call(client, h, "export", first, acknowledge_copy_limits=True).json()["template"]
    assert (
        settings.env == "test"
        and settings.postgres_db.startswith("butler_test")
        and settings.postgres_user == "postgres"
    )
    name = "butler_test_installation_" + uuid4().hex[:8]

    def database(command):
        with postgres_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            statement = (
                sql.SQL(command + " {}")
                .format(sql.Identifier(name))
                .as_string(connection.connection.driver_connection)
            )
            connection.exec_driver_sql(statement)

    database("CREATE DATABASE")
    owner_engine = runtime_engine = None
    previous_override = app.dependency_overrides.get(get_db)
    try:
        migrated = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "BUTLER_POSTGRES_DB": name},
            capture_output=True,
            text=True,
            check=False,
        )
        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        url = make_url(settings.database_url).set(database=name)
        owner_engine = create_engine(url)
        with owner_engine.begin() as connection:
            configure_role(connection.connection.driver_connection, RUNTIME_PASSWORD)
        maker = sessionmaker(bind=owner_engine, expire_on_commit=False)
        slug = "synthetic-installation-" + uuid4().hex
        with maker.begin() as db:
            provision(
                db, slug, "Synthetic separate installation", SYNTHETIC_PASSWORD, {"technical_admin"}
            )
        runtime_engine = create_engine(
            url.set(username="butler_runtime", password=RUNTIME_PASSWORD)
        )
        runtime = sessionmaker(bind=runtime_engine, expire_on_commit=False)
        with client_for(runtime) as other:
            login = other.post(
                "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
            )
            assert login.status_code == 200
            oh = {"X-CSRF-Token": login.json()["csrf_token"]}
            empty = current(other, oh)
            assert empty["revision"] == 0 and empty["installation_id"] is None
            second = configure(other, oh, empty, template)
            assert (
                second["installation_id"] != first["installation_id"]
                and second["configuration"] == first["configuration"]
            )
            foreign = preview(other, oh, second, changed_template(second))
            foreign["record"] = first
            assert apply_preview(other, oh, foreign).status_code == 409
            assert (
                call(
                    other, {**h, "Cookie": f"{identity.COOKIE}={first_cookie}"}, "read"
                ).status_code
                == 401
            )
            assert current(other, oh) == second
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        if runtime_engine is not None:
            runtime_engine.dispose()
        if owner_engine is not None:
            owner_engine.dispose()
        # The generated, positively isolated database is ours; terminate only its connections.
        with postgres_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            statement = (
                sql.SQL("DROP DATABASE {} WITH (FORCE)")
                .format(sql.Identifier(name))
                .as_string(connection.connection.driver_connection)
            )
            connection.exec_driver_sql(statement)
    assert current(client, h) == first
