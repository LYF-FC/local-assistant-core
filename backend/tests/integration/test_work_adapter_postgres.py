"""Actual protected-file activation through current identity and managed login."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import event, select
from work_credential_helpers import FIRST, SECOND, apply
from work_storage_helpers import connect

from app import identity
from app import work_adapter as adapter
from app.config import settings
from app.models import AuthSession, User
from app.work_manage import administer

pytestmark = pytest.mark.integration


@pytest.fixture
def active_adapter(credential_case, scenario, tmp_path, monkeypatch):
    case = credential_case
    apply(case)
    with connect() as db:
        bundle = adapter.prepare(db, case["slug"], FIRST)
    tmp_path.chmod(0o700)
    adapter.publish(tmp_path, bundle)
    client, headers, _, maker, user_id = scenario
    with maker.begin() as db:
        user = db.get(User, user_id)
        administer(db, "grant", case["slug"], user.slug)
        administer(db, "enable", case["slug"])
    monkeypatch.setattr(settings, "work_synthetic_adapter_enabled", True)
    monkeypatch.setattr(settings, "work_synthetic_secret_directory", tmp_path)
    return dict(
        case, client=client, headers=headers, maker=maker, directory=tmp_path, bundle=bundle
    )


def read(case):
    return case["client"].post(
        f"/api/v1/work/workspaces/{case['workspace']}/validation-read",
        json={"limit": 2},
        headers=case["headers"],
    )


def sessions(case):
    with connect() as db:
        return db.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE usename=%s", (case["managed"],)
        ).fetchone()[0]


def test_file_adapter_reads_scoped_markers_audits_and_leaves_no_pooled_session(active_adapter):
    case = active_adapter
    # Existing fixture's independent harness verifies RLS; only synthetic records.
    with connect() as db:
        identifier = uuid4()
        db.execute(
            "INSERT INTO work.validation_records (workspace_id,id,marker) VALUES (%s,%s,'synthetic:active-adapter')",
            (case["workspace"], identifier),
        )
    for _ in range(2):
        response = read(case)
        assert response.status_code == 200
        assert response.json()["items"][0]["id"] == str(identifier)
        assert response.json()["execution_allowed"] is False
        assert sessions(case) == 0
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM work.read_attempts WHERE workspace_id=%s AND event_type='validation.read_prepared'",
                (case["workspace"],),
            ).fetchone()[0]
            == 2
        )
        assert db.execute(
            "SELECT source_context,metadata_json,result_status FROM audit_events WHERE entity_id=%s AND event_type='admin.work_secret_prepared'",
            (str(case["workspace"]),),
        ).fetchall() == [({}, {}, "prepared")]


@pytest.mark.parametrize("fault", ["removed", "expired", "wrong_secret", "wrong_oid"])
def test_changed_file_fails_closed_without_cached_connection(active_adapter, fault):
    case = active_adapter
    assert read(case).status_code == 200 and sessions(case) == 0
    path = case["directory"] / adapter.FILE
    path.unlink()
    if fault != "removed":
        bundle = case["bundle"].model_copy(deep=True)
        if fault == "wrong_secret":
            bundle.password = adapter.SecretStr(SECOND)
        elif fault == "wrong_oid":
            bundle.database_oid += 1
        adapter.publish(case["directory"], bundle)
        if fault == "expired":
            import json

            content = json.loads(path.read_text())
            content["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
            path.write_text(json.dumps(content))
    response = read(case)
    assert response.status_code == 503 and "items" not in response.json()
    assert sessions(case) == 0


@pytest.mark.parametrize("action", ["rotate", "revoke"])
def test_disable_fences_requests_then_credential_change_cannot_reuse_old_session(
    active_adapter, action
):
    case = active_adapter
    assert read(case).status_code == 200 and sessions(case) == 0
    with case["maker"].begin() as db:
        administer(db, "disable", case["slug"])
    assert read(case).status_code == 404
    apply(case, action, SECOND)
    with case["maker"].begin() as db:
        administer(db, "enable", case["slug"])
    assert read(case).status_code == 503 and sessions(case) == 0
    if action == "rotate":
        with case["maker"].begin() as db:
            administer(db, "disable", case["slug"])
        with connect() as db:
            bundle = adapter.prepare(db, case["slug"], SECOND)
        (case["directory"] / adapter.FILE).unlink()
        adapter.publish(case["directory"], bundle)
        with case["maker"].begin() as db:
            administer(db, "enable", case["slug"])
        assert read(case).status_code == 200 and sessions(case) == 0


def test_preparation_wrong_password_or_active_workspace_makes_no_prepared_audit(credential_case):
    case = credential_case
    apply(case)
    with pytest.raises(psycopg.Error), connect() as db:
        adapter.prepare(db, case["slug"], SECOND)
    with connect() as db:
        db.execute("UPDATE work_workspaces SET is_active=true WHERE id=%s", (case["workspace"],))
    with pytest.raises(ValueError), connect() as db:
        adapter.prepare(db, case["slug"], FIRST)
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE entity_id=%s AND event_type='admin.work_secret_prepared'",
                (str(case["workspace"]),),
            ).fetchone()[0]
            == 0
        )


def test_audit_failure_prevents_preparation_result(credential_case):
    case = credential_case
    apply(case)
    constraint = "synthetic_file_audit_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE audit_events ADD CONSTRAINT {} CHECK(event_type<>'admin.work_secret_prepared') NOT VALID"
            ).format(sql.Identifier(constraint))
        )
    try:
        with pytest.raises(psycopg.Error), connect() as db:
            adapter.prepare(db, case["slug"], FIRST)
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE audit_events DROP CONSTRAINT {}").format(
                    sql.Identifier(constraint)
                )
            )


def test_expiry_during_pool_disposal_releases_no_items(active_adapter, monkeypatch):
    case = active_adapter
    now = identity.now_utc()
    clock = [now]
    with case["maker"].begin() as db:
        session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash
                == identity.digest(case["client"].cookies.get(identity.COOKIE))
            )
        )
        session.expires_at = now + timedelta(seconds=1)
    monkeypatch.setattr(identity, "now_utc", lambda: clock[0])
    factory = adapter.workspace_engine

    def build(url):
        engine = factory(url)

        def expire(disposed):
            clock[0] = now + timedelta(seconds=2)

        event.listen(engine, "engine_disposed", expire)
        return engine

    monkeypatch.setattr(adapter, "workspace_engine", build)
    response = read(case)
    assert response.status_code == 401 and "items" not in response.json()
    assert sessions(case) == 0
