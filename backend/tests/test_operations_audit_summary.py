"""Spec 072 request validation and authority. Counts need PostgreSQL (see the integration suite)."""

import pytest
from sqlalchemy import select
from test_approvals import signin
from test_installation import admin_headers

from app.manage import set_scope
from app.models import AuditEvent, User

URL = "/api/v1/operations/audit-summary"


def post(client, headers, **body):
    return client.post(
        URL, headers=headers, json={"scope": "technical_admin", "window": "24h", **body}
    )


@pytest.mark.parametrize(
    "body",
    [
        {"window": "30d"},
        {"window": "1h"},
        {"window": 24},
        {"window": None},
        {"extra": True},
        {"scope": "household_shared"},
        {"scope": "finance_private"},
    ],
)
def test_unsupported_requests_are_rejected_without_a_payload(auth_client, auth_store, body):
    h = admin_headers(auth_client, auth_store)
    response = post(auth_client, h, **body)
    assert response.status_code == 422 and "categories" not in response.text


def test_missing_window_and_scope_are_rejected(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    assert auth_client.post(URL, headers=h, json={"scope": "technical_admin"}).status_code == 422
    assert auth_client.post(URL, headers=h, json={"window": "24h"}).status_code == 422
    assert auth_client.post(URL, headers=h, json={}).status_code == 422


def test_current_grant_session_csrf_and_origin_are_required(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    assert post(auth_client, {}).status_code == 403
    assert post(auth_client, {**h, "Origin": "https://invalid.example"}).status_code == 403
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "technical_admin", False)
    assert post(auth_client, h).status_code == 403


def test_non_postgres_never_fabricates_counts_and_does_not_audit_success(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    response = post(auth_client, h)
    assert response.status_code == 503
    assert "categories" not in response.text and "totals" not in response.text
    with auth_store() as db:
        assert (
            db.query(AuditEvent).filter(AuditEvent.event_type == "operations.audit_summary").count()
            == 0
        )


def test_household_member_without_the_grant_is_denied(auth_client, auth_store):
    h = signin(auth_client)
    response = post(auth_client, h)
    assert response.status_code == 403 and "categories" not in response.text
