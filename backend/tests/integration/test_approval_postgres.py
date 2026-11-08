"""PostgreSQL guards, restricted runtime and distinct-session races."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app import identity
from app.models import Approval, AuditEvent, AuthSession
from app.runtime_role import ROLE, configure

pytestmark = pytest.mark.integration
RUNTIME_PASSWORD = "synthetic-runtime-password-only-0123456789"


def reviewed(record):
    return {"payload_hash": record["payload_hash"], "policy_version": record["policy_version"]}


def test_restricted_role_identity_approval_and_noop_consumption(scenario, runtime_engine):
    client, headers, record, admin, _ = scenario
    with runtime_engine.connect() as db:
        assert db.execute(text("SELECT current_user")).scalar_one() == ROLE
    assert client.get("/api/v1/auth/me").status_code == 200
    bootstrap = client.post("/api/v1/auth/session", json={})
    assert bootstrap.status_code == 200
    headers["X-CSRF-Token"] = bootstrap.json()["csrf_token"]
    response = client.post(
        f"/api/v1/approvals/{record['id']}/decide",
        headers=headers,
        json=dict(reviewed(record), decision="approve"),
    )
    assert response.status_code == 200
    assert (
        client.post(
            f"/api/v1/approvals/{record['id']}/consume", headers=headers, json=reviewed(record)
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/approvals/{record['id']}/consume", headers=headers, json=reviewed(record)
        ).status_code
        == 409
    )
    with admin() as db:
        assert db.get(Approval, UUID(record["id"])).status == "consumed"
        assert (
            len(
                db.scalars(
                    select(AuditEvent).where(
                        AuditEvent.approval_id == UUID(record["id"]),
                        AuditEvent.event_type == "approval.consumed",
                    )
                ).all()
            )
            == 1
        )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET result_status='tampered'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
        "UPDATE users SET is_active=false",
        "DELETE FROM user_scopes",
        "DROP TABLE audit_events",
        "ALTER TABLE audit_events DISABLE TRIGGER ALL",
        "CREATE TABLE public.untrusted_test (id integer)",
    ],
)
def test_runtime_cannot_tamper_or_administer(scenario, runtime_engine, statement):
    with pytest.raises(DBAPIError), runtime_engine.begin() as db:
        db.execute(text(statement))


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET result_status='tampered'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ],
)
def test_audit_guard_also_blocks_ordinary_owner_dml(scenario, postgres_engine, statement):
    with pytest.raises(DBAPIError), postgres_engine.begin() as db:
        db.execute(text(statement))


def test_postgres_seals_payload_and_decision_shape(scenario, runtime_engine):
    _, _, record, _, _ = scenario
    statements = [
        "UPDATE approvals SET request_payload='{}'::jsonb WHERE id=:id",
        "UPDATE approvals SET expires_at=expires_at+interval '1 day' WHERE id=:id",
        "UPDATE approvals SET payload_hash=repeat('0',64) WHERE id=:id",
        "UPDATE approvals SET status='consumed' WHERE id=:id",
        "UPDATE approvals SET status='approved' WHERE id=:id",
    ]
    for statement in statements:
        with pytest.raises(DBAPIError), runtime_engine.begin() as db:
            db.execute(text(statement), {"id": UUID(record["id"])})


@pytest.mark.parametrize("operation", ["decide", "consume"])
def test_distinct_session_race_has_exactly_one_winner(scenario, runtime_engine, operation):
    client, headers, record, admin, user_id = scenario
    if operation == "consume":
        assert (
            client.post(
                f"/api/v1/approvals/{record['id']}/decide",
                headers=headers,
                json=dict(reviewed(record), decision="approve"),
            ).status_code
            == 200
        )
    contexts = []
    with admin.begin() as db:
        for _ in range(8):
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            now = identity.now_utc()
            db.add(
                AuthSession(
                    user_id=user_id,
                    token_hash=identity.digest(token),
                    csrf_hash=identity.digest(csrf),
                    created_at=now,
                    last_seen_at=now,
                    expires_at=now + timedelta(hours=1),
                )
            )
            contexts.append((token, csrf))

    def compete(context):
        token, csrf = context
        body = reviewed(record)
        if operation == "decide":
            body = dict(body, decision="approve")
        return client.post(
            f"/api/v1/approvals/{record['id']}/{operation}",
            headers={"Cookie": f"{identity.COOKIE}={token}", "X-CSRF-Token": csrf},
            json=body,
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(compete, contexts))
    assert outcomes.count(200) == 1
    assert outcomes.count(409) == 7
    with admin() as db:
        state = "approved" if operation == "decide" else "consumed"
        assert (
            len(
                db.scalars(
                    select(AuditEvent).where(
                        AuditEvent.approval_id == UUID(record["id"]),
                        AuditEvent.event_type == "approval." + state,
                    )
                ).all()
            )
            == 1
        )


@pytest.mark.parametrize("unsafe", ["membership", "schema_ownership"])
def test_role_setup_refuses_inherited_or_owner_authority(postgres_engine, runtime_engine, unsafe):
    from psycopg import sql

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            cursor = connection.connection.driver_connection.cursor()
            name = "synthetic_role_guard_" + uuid4().hex
            if unsafe == "membership":
                cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(name)))
                cursor.execute(
                    sql.SQL("GRANT {} TO {}").format(sql.Identifier(name), sql.Identifier(ROLE))
                )
            else:
                cursor.execute(
                    sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                        sql.Identifier(name), sql.Identifier(ROLE)
                    )
                )
            with pytest.raises(ValueError):
                configure(connection.connection.driver_connection, RUNTIME_PASSWORD)
            cursor.close()
        finally:
            transaction.rollback()
