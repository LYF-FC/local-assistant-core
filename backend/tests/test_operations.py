from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_installation import admin_headers

from app import identity, operations
from app.config import settings
from app.manage import set_scope
from app.models import AuditEvent, User


def read(client, headers, **extra):
    return client.post(
        "/api/v1/operations/read", headers=headers, json={"scope": "technical_admin", **extra}
    )


def seed_events(db, uid, *, scope="technical_admin", n=1, age=1, result="success"):
    for i in range(n):
        db.add(
            AuditEvent(
                environment="test",
                initiator_type="human",
                initiator_id=str(uid),
                scope_key=scope,
                event_type="installation.synthetic-private-text",
                result_status=result,
                occurred_at=identity.now_utc() - timedelta(seconds=age + i),
                entity_id="synthetic-private-entity",
                metadata_json={"secret": "synthetic-private-body"},
                source_context={"body": "synthetic-private-source"},
                before_json={"finance": "synthetic-private-before"},
            )
        )


def test_observations_are_allowlisted_and_configuration_is_not_health(
    auth_client, auth_store, monkeypatch
):
    h = admin_headers(auth_client, auth_store)
    monkeypatch.setattr(settings, "document_archive_directory", Path("/synthetic/private/archive"))
    monkeypatch.setattr(settings, "pdf_socket_directory", Path("/synthetic/private/socket"))
    monkeypatch.setattr(settings, "document_answers_enabled", True)
    response = read(auth_client, h)
    assert response.status_code == 200
    body = response.json()
    assert response.headers["cache-control"] == "no-store"
    states = {r["key"]: r["state"] for r in body["components"]}
    assert states["api"] == states["database"] == "observed"
    assert (
        states["archive"]
        == states["pdf_parser"]
        == states["local_answers"]
        == "configured_unverified"
    )
    assert all(
        states[k] == "unknown"
        for k in [
            "workers",
            "backup_restore",
            "storage_capacity",
            "certificates",
            "remote_hardware",
            "independent_observer",
        ]
    )
    assert [r["key"] for r in body["software"]] == ["api_build", "python", *operations.PACKAGES]
    assert all(r["assessment"] == "not_assessed" for r in body["software"])
    assert "/synthetic/private" not in response.text and "localhost" not in response.text
    with auth_store() as db:
        row = db.scalar(select(AuditEvent).where(AuditEvent.event_type == "operations.read"))
        assert row and set(row.metadata_json) == {"jobs_sampled"} and row.before_json is None


def test_own_technical_activity_is_bounded_without_raw_payloads(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    with auth_store.begin() as db:
        alice = db.scalar(select(User).where(User.slug == "alice"))
        bob = db.scalar(select(User).where(User.slug == "bob"))
        seed_events(db, alice.id, n=26)
        seed_events(db, bob.id, n=30, result="error")
        seed_events(db, alice.id, scope="finance_private", n=30, result="error")
        seed_events(db, alice.id, n=3, age=90000, result="error")
    body = read(auth_client, h).json()
    assert body["activity"] == {"state": "not_available"}
    assert "synthetic-private" not in str(body)
    assert body["jobs"] == {
        "sampled": 0,
        "has_more": False,
        "counts": dict.fromkeys([*operations.JOB_STATES, "other"], 0),
    }


@pytest.mark.parametrize(
    "body",
    [
        {"scope": "finance_private"},
        {"scope": "technical_admin", "actor_id": str(uuid4())},
        {"scope": "technical_admin", "limit": 100},
        {"scope": "technical_admin", "probe": True},
    ],
)
def test_unsupported_requests_never_enable_probes(auth_client, auth_store, body):
    h = admin_headers(auth_client, auth_store)
    assert auth_client.post("/api/v1/operations/read", headers=h, json=body).status_code == 422


def test_current_grant_session_csrf_and_origin_are_required(auth_client, auth_store):
    assert read(auth_client, {}).status_code == 401
    h = signin(auth_client)
    assert read(auth_client, h).status_code == 403
    h = admin_headers(auth_client, auth_store)
    assert read(auth_client, {}).status_code == 403
    assert read(auth_client, {**h, "Origin": "https://invalid.example"}).status_code == 403
    assert read(auth_client, {**h, "Host": "invalid.example"}).status_code == 403
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "technical_admin", False)
    assert read(auth_client, h).status_code == 403
    assert auth_client.post("/api/v1/auth/logout", headers=h, json={}).status_code == 200
    assert read(auth_client, h).status_code == 401


def test_audit_failure_withholds_all_observations(auth_client, auth_store, auth_engine):
    h = admin_headers(auth_client, auth_store)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("synthetic-private-error")

    event.listen(auth_engine, "before_cursor_execute", fail)
    try:
        result = read(auth_client, h)
        assert (
            result.status_code == 503
            and "components" not in result.text
            and "synthetic-private" not in result.text
        )
    finally:
        event.remove(auth_engine, "before_cursor_execute", fail)


def test_missing_or_unsafe_version_metadata_is_unknown(monkeypatch):
    def missing(_):
        raise operations.PackageNotFoundError()

    monkeypatch.setattr(operations, "version", missing)
    monkeypatch.setattr(settings, "app_version", "/synthetic/private/version")
    assert operations.inventory()[0]["version"] is None
    assert all(row["version"] is None for row in operations.inventory()[2:])
    assert operations.safe_version("1.2.3+dev") == "1.2.3+dev"
    assert operations.safe_version("secret\n1") is None


def test_session_expiry_during_observation_withholds_snapshot(
    auth_client, auth_store, auth_engine, monkeypatch
):
    h = admin_headers(auth_client, auth_store)
    now = identity.now_utc()

    def clock(conn, cursor, statement, parameters, context, executemany):
        if "FROM durable_jobs" in statement:
            monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(hours=24))

    event.listen(auth_engine, "after_cursor_execute", clock)
    try:
        assert read(auth_client, h).status_code == 401
    finally:
        event.remove(auth_engine, "after_cursor_execute", clock)


def enqueue_technical(client, headers, key, scope="technical_admin"):
    from test_approvals import create, decide
    from test_jobs import enqueue

    response = create(client, headers, scope=scope)
    assert response.status_code == 201, response.text
    record = response.json()
    assert decide(client, headers, record).status_code == 200
    response = enqueue(client, headers, record, key)
    assert response.status_code == 201, response.text
    return response.json()


def test_job_sample_is_bounded_and_excludes_other_scopes(auth_client, auth_store, auth_engine):
    h = admin_headers(auth_client, auth_store)
    for i in range(26):
        enqueue_technical(auth_client, h, f"synthetic-operations-{i:04}")
    enqueue_technical(auth_client, h, "synthetic-household-0001", "household_shared")
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(auth_engine, "before_cursor_execute", observe)
    try:
        body = read(auth_client, h).json()
    finally:
        event.remove(auth_engine, "before_cursor_execute", observe)
    assert (
        body["jobs"]["sampled"] == 25
        and body["jobs"]["has_more"] is True
        and body["jobs"]["counts"]["queued"] == 25
    )
    assert not any("FROM audit_events" in s for s in statements)
    assert not any("request_payload" in s or "result_code" in s for s in statements)
