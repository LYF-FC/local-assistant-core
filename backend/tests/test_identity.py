from datetime import timedelta
from unittest.mock import patch

import pytest
from conftest import SYNTHETIC_PASSWORD
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import identity
from app.manage import provision, replace_password, set_active, set_scope
from app.models import AuditEvent, AuthRateWindow, AuthSession, Credential, User


def login(client, slug="alice", password=SYNTHETIC_PASSWORD, **kwargs):
    return client.post("/api/v1/auth/login", json={"slug": slug, "password": password}, **kwargs)


def test_cookie_and_server_records_do_not_store_bearer_secrets(auth_client, auth_store):
    response = login(auth_client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert "Path=/" in cookie and "Domain=" not in cookie
    token, csrf = auth_client.cookies.get(identity.COOKIE), response.json()["csrf_token"]
    assert len(token) >= 40
    with auth_store() as db:
        record = db.scalar(select(AuthSession))
        assert record.token_hash == identity.digest(token) and token not in record.token_hash
        assert record.csrf_hash == identity.digest(csrf)
        assert db.scalar(select(Credential)).password_hash.startswith("$argon2id$")
    assert auth_client.get("/api/v1/auth/me").json()["display_name"] == "Synthetic Alice"


@pytest.mark.parametrize("slug,password", [("alice", "wrong"), ("unknown", SYNTHETIC_PASSWORD)])
def test_wrong_and_unknown_logins_are_indistinguishable(auth_client, slug, password):
    response = login(auth_client, slug, password)
    assert response.status_code == 401
    assert response.json() == {"detail": "Access denied"}
    assert "set-cookie" not in response.headers


def test_distinct_identities_rotate_previous_session(auth_client):
    first = login(auth_client)
    old = auth_client.cookies.get(identity.COOKIE)
    second = login(auth_client, "bob")
    assert first.json()["user_id"] != second.json()["user_id"]
    assert old != auth_client.cookies.get(identity.COOKIE)
    assert auth_client.get("/api/v1/auth/me").json()["display_name"] == "Synthetic Bob"
    auth_client.cookies.set(identity.COOKIE, old, domain="localhost.local", path="/")
    assert auth_client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invented", "X-User": "admin"}])
def test_no_cookie_or_identity_headers_cannot_authenticate(auth_client, headers):
    assert auth_client.get("/api/v1/auth/me", headers=headers).status_code == 401


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "https://localhost:8443.evil"])
def test_wrong_origin_denied_before_password_verification(auth_client, origin):
    with patch("app.identity._hasher") as hasher:
        hasher.verify.side_effect = AssertionError("hashing attempted")
        response = login(auth_client, headers={"Origin": origin})
    assert response.status_code == 403


def test_absent_origin_and_plain_http_are_rejected(auth_client):
    auth_client.headers.pop("Origin")
    assert login(auth_client).status_code == 403
    assert auth_client.get("http://localhost:8443/api/v1/auth/me").status_code == 400


def test_login_validation_does_not_echo_secrets(auth_client):
    secret = "a-sensitive-password-that-must-not-be-echoed"
    response = auth_client.post(
        "/api/v1/auth/login", json={"slug": "INVALID SLUG", "password": secret}
    )
    assert response.status_code == 422
    assert secret not in response.text


def test_logout_requires_csrf_and_revokes_token(auth_client):
    response = login(auth_client)
    csrf = response.json()["csrf_token"]
    token = auth_client.cookies.get(identity.COOKIE)
    assert auth_client.post("/api/v1/auth/logout").status_code == 403
    assert (
        auth_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    assert auth_client.get("/api/v1/auth/me").status_code == 200
    assert (
        auth_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    )
    # Replay the old bearer explicitly after the deletion cookie.
    assert (
        auth_client.get(
            "/api/v1/auth/me", headers={"Cookie": f"{identity.COOKIE}={token}"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("field,delta", [("expires_at", -1), ("last_seen_at", -1801)])
def test_server_expiry_and_idle_timeout(auth_client, auth_store, field, delta):
    assert login(auth_client).status_code == 200
    with auth_store.begin() as db:
        session = db.scalar(select(AuthSession))
        setattr(session, field, identity.now_utc() + timedelta(seconds=delta))
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_disabling_user_invalidates_active_session_and_future_login(auth_client, auth_store):
    login(auth_client)
    with auth_store.begin() as db:
        set_active(db, db.scalar(select(User).where(User.slug == "alice")), False)
    assert auth_client.get("/api/v1/auth/me").status_code == 401
    assert login(auth_client).status_code == 401


def test_password_replacement_revokes_sessions(auth_client, auth_store):
    login(auth_client)
    with auth_store.begin() as db:
        replace_password(
            db,
            db.scalar(select(User).where(User.slug == "alice")),
            "replacement-synthetic-password-123",
        )
    assert auth_client.get("/api/v1/auth/me").status_code == 401
    assert login(auth_client).status_code == 401
    assert login(auth_client, password="replacement-synthetic-password-123").status_code == 200


def test_scopes_reloaded_and_technical_admin_is_not_a_content_override(auth_client, auth_store):
    login(auth_client)
    assert auth_client.get("/api/v1/auth/scopes/household_shared").status_code == 200
    assert auth_client.get("/api/v1/auth/scopes/finance_private").status_code == 403
    with auth_store.begin() as db:
        user = db.scalar(select(User).where(User.slug == "alice"))
        set_scope(db, user, "household_shared", False)
        set_scope(db, user, "technical_admin", True)
    assert auth_client.get("/api/v1/auth/scopes/household_shared").status_code == 403
    assert auth_client.get("/api/v1/auth/scopes/technical_admin").status_code == 200
    assert auth_client.get("/api/v1/auth/scopes/finance_private").status_code == 403
    assert auth_client.get("/api/v1/auth/scopes/unknown").status_code == 403


def test_account_budget_persists_in_database_and_expires(auth_client, auth_store, monkeypatch):
    for _ in range(5):
        assert login(auth_client, password="wrong").status_code == 401
    assert login(auth_client).status_code == 429
    with auth_store() as db:
        assert (
            db.scalar(
                select(AuthRateWindow.attempts).where(
                    AuthRateWindow.key == identity.digest("account:alice")
                )
            )
            == 6
        )
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(minutes=16))
    assert login(auth_client).status_code == 200


def test_source_budget_cannot_be_bypassed_with_forwarded_headers(auth_client, auth_store):
    # Pre-fill the source budget with atomic database calls, avoiding expensive test hashing.
    with auth_store.begin() as db:
        for _ in range(30):
            assert identity.attempt(db, "source:testclient", 30, identity.now_utc())
    assert login(auth_client, headers={"X-Forwarded-For": "different-source"}).status_code == 429


def test_security_audit_contains_outcomes_without_credentials(auth_client, auth_store):
    response = login(auth_client)
    auth_client.get("/api/v1/auth/scopes/finance_private")
    with auth_store() as db:
        events = list(db.scalars(select(AuditEvent)))
        assert {"auth.login", "auth.scope_denied"} <= {x.event_type for x in events}
        serialized = repr(
            [(x.metadata_json, x.source_context, x.before_json, x.after_json) for x in events]
        )
        assert SYNTHETIC_PASSWORD not in serialized
        assert response.json()["csrf_token"] not in serialized
        assert auth_client.cookies.get(identity.COOKIE) not in serialized


@pytest.mark.parametrize("phase", ["flush", "commit"])
def test_audit_or_commit_failure_issues_no_cookie_and_rolls_back(auth_client, auth_store, phase):
    def fail(*args):
        raise SQLAlchemyError("synthetic internal failure; must not leak")

    target, event_name = (
        (AuditEvent, "before_insert") if phase == "flush" else (Session, "before_commit")
    )
    event.listen(target, event_name, fail)
    try:
        response = login(auth_client)
    finally:
        event.remove(target, event_name, fail)
    assert response.status_code == 503
    assert response.json() == {"detail": "Identity service unavailable"}
    assert "set-cookie" not in response.headers
    with auth_store() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
        assert db.scalar(select(func.count()).select_from(AuthRateWindow)) == 0


@pytest.mark.parametrize("password", ["short", "x" * 1025])
def test_local_provisioning_rejects_invalid_passwords(auth_store, password):
    with auth_store.begin() as db, pytest.raises(ValueError):
        provision(db, "new-user", "Synthetic", password, set())


def test_no_signup_or_permission_administration_api(auth_client):
    assert auth_client.post("/api/v1/auth/signup").status_code == 404
    login(auth_client)
    assert auth_client.post("/api/v1/auth/scopes/finance_private").status_code == 405
    assert auth_client.post("/api/v1/speech/synthesize").status_code == 503


def test_multibyte_password_limit_does_not_echo_input(auth_client):
    secret = "é" * 1024
    response = auth_client.post("/api/v1/auth/login", json={"slug": "alice", "password": secret})
    assert response.status_code == 422
    assert secret not in response.text


def test_local_cli_provisions_and_disables_without_printing_secrets(
    auth_store, monkeypatch, capsys
):
    from app import manage

    monkeypatch.setattr(manage, "SessionLocal", auth_store)
    monkeypatch.setattr(manage, "read_password", lambda: SYNTHETIC_PASSWORD)
    monkeypatch.setattr(
        "sys.argv",
        [
            "manage",
            "--environment",
            "test",
            "create-user",
            "--slug",
            "cli-user",
            "--display-name",
            "Synthetic CLI",
            "--scope",
            "household_shared",
        ],
    )
    manage.main()
    monkeypatch.setattr(
        "sys.argv", ["manage", "--environment", "test", "disable-user", "--slug", "cli-user"]
    )
    manage.main()
    with auth_store() as db:
        assert not db.scalar(select(User).where(User.slug == "cli-user")).is_active
    assert SYNTHETIC_PASSWORD not in capsys.readouterr().out


def test_local_cli_rejects_environment_mismatch(monkeypatch):
    from app import manage

    monkeypatch.setattr(
        "sys.argv", ["manage", "--environment", "development", "disable-user", "--slug", "alice"]
    )
    with pytest.raises(SystemExit):
        manage.main()


def test_noninteractive_password_administration_is_rejected(monkeypatch):
    from app.manage import read_password

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(ValueError, match="interactive"):
        read_password()


def test_session_bootstrap_rotates_csrf_without_extending_absolute_expiry(auth_client, auth_store):
    from sqlalchemy import select

    from app.models import AuthSession

    result = auth_client.post(
        "/api/v1/auth/login", json={"slug": "alice", "password": SYNTHETIC_PASSWORD}
    )
    old_csrf = result.json()["csrf_token"]
    with auth_store() as db:
        expiry = db.scalar(select(AuthSession)).expires_at
    result = auth_client.post("/api/v1/auth/session", json={})
    assert result.status_code == 200
    assert result.json()["user"]["display_name"] == "Synthetic Alice"
    new_csrf = result.json()["csrf_token"]
    assert new_csrf != old_csrf
    assert "set-cookie" not in result.headers
    assert (
        auth_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": old_csrf}).status_code
        == 403
    )
    with auth_store() as db:
        session = db.scalar(select(AuthSession))
        assert session.expires_at == expiry
        assert session.csrf_hash == identity.digest(new_csrf)
    assert (
        auth_client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": new_csrf}).status_code
        == 200
    )


@pytest.mark.parametrize(
    "headers", [{"Origin": "https://other.invalid"}, {"Host": "other.invalid"}, {"Origin": ""}]
)
def test_bootstrap_cannot_cross_origin_or_host(auth_client, headers):
    auth_client.post("/api/v1/auth/login", json={"slug": "alice", "password": SYNTHETIC_PASSWORD})
    assert auth_client.post("/api/v1/auth/session", json={}, headers=headers).status_code == 403


def test_bootstrap_requires_authenticated_current_session(auth_client):
    assert auth_client.post("/api/v1/auth/session", json={}).status_code == 401
    result = auth_client.post(
        "/api/v1/auth/login", json={"slug": "alice", "password": SYNTHETIC_PASSWORD}
    )
    assert (
        auth_client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": result.json()["csrf_token"]}
        ).status_code
        == 200
    )
    assert auth_client.post("/api/v1/auth/session", json={}).status_code == 401


def test_bootstrap_audit_failure_rolls_back_rotation(auth_client, auth_store, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError

    from app.models import AuthSession

    auth_client.post("/api/v1/auth/login", json={"slug": "alice", "password": SYNTHETIC_PASSWORD})
    with auth_store() as db:
        old_hash = db.scalar(select(AuthSession)).csrf_hash

    def failure(*args, **kwargs):
        raise SQLAlchemyError("synthetic audit failure")

    monkeypatch.setattr(identity, "audit", failure)
    response = auth_client.post("/api/v1/auth/session", json={})
    assert response.status_code == 503
    assert "csrf_token" not in response.json()
    with auth_store() as db:
        assert db.scalar(select(AuthSession)).csrf_hash == old_hash


def test_bootstrap_commit_failure_returns_no_csrf(auth_client, auth_store):
    from sqlalchemy import event, select
    from sqlalchemy.exc import SQLAlchemyError

    from app.models import AuthSession

    auth_client.post("/api/v1/auth/login", json={"slug": "alice", "password": SYNTHETIC_PASSWORD})
    with auth_store() as db:
        old_hash = db.scalar(select(AuthSession)).csrf_hash

    def fail(db):
        raise SQLAlchemyError("synthetic commit failure")

    event.listen(auth_store, "before_commit", fail)
    try:
        response = auth_client.post("/api/v1/auth/session", json={})
        assert response.status_code == 503
        assert "csrf_token" not in response.json()
    finally:
        event.remove(auth_store, "before_commit", fail)
    with auth_store() as db:
        assert db.scalar(select(AuthSession)).csrf_hash == old_hash
