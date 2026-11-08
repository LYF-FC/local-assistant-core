"""Real PostgreSQL API and multi-connection rate-limit verification."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from conftest import SYNTHETIC_PASSWORD
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from app import identity
from app.manage import set_scope
from app.models import AuditEvent, AuthRateWindow, AuthSession, User

pytestmark = pytest.mark.integration


@pytest.fixture
def auth_engine(postgres_engine):
    return postgres_engine


def test_real_database_identity_audit_and_current_scope_revocation(auth_client, auth_store):
    response = auth_client.post(
        "/api/v1/auth/login", json={"slug": "alice", "password": SYNTHETIC_PASSWORD}
    )
    assert response.status_code == 200
    assert auth_client.get("/api/v1/auth/me").json()["display_name"] == "Synthetic Alice"
    assert auth_client.get("/api/v1/auth/scopes/household_shared").status_code == 200
    assert auth_client.get("/api/v1/auth/scopes/finance_private").status_code == 403
    with auth_store.begin() as db:
        set_scope(
            db, db.scalar(select(User).where(User.slug == "alice")), "household_shared", False
        )
    assert auth_client.get("/api/v1/auth/scopes/household_shared").status_code == 403
    token_hash = identity.digest(auth_client.cookies.get(identity.COOKIE))
    csrf = response.json()["csrf_token"]
    assert (
        auth_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    )
    with auth_store() as db:
        assert (
            db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash)).revoked_at
            is not None
        )
        assert "auth.scope_denied" in set(
            db.scalars(
                select(AuditEvent.event_type).where(
                    AuditEvent.initiator_id
                    == str(db.scalar(select(User.id).where(User.slug == "alice")))
                )
            )
        )


def test_atomic_rate_budget_across_connections(auth_engine):
    auth_store = sessionmaker(bind=auth_engine)
    key = "synthetic-concurrency-" + uuid4().hex

    def consume(_):
        with auth_store.begin() as db:
            return identity.attempt(db, key, 5, identity.now_utc())

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(consume, range(16)))
    assert sum(outcomes) == 5
    with auth_store.begin() as db:
        db.execute(delete(AuthRateWindow).where(AuthRateWindow.key == identity.digest(key)))
