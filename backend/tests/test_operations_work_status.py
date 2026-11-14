"""Spec 073 test 20: request validation, authority and real states on SQLite.

The observation queries are portable, so SQLite development returns real states; the lock and
statement timeouts apply only on PostgreSQL (see the integration suite for all semantics).
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from test_approvals import signin
from test_installation import admin_headers

from app import identity, operations
from app.manage import set_scope
from app.models import AuditEvent, JobOutbox, User

URL = "/api/v1/operations/work-status"


def post(client, headers, **body):
    return client.post(URL, headers=headers, json={"scope": "technical_admin", **body})


@pytest.mark.parametrize(
    "body",
    [
        {"extra": True},
        {"window": "24h"},
        {"scope": "household_shared"},
        {"scope": "finance_private"},
        {"scope": None},
    ],
)
def test_strict_request_is_rejected_without_a_payload_or_echo(auth_client, auth_store, body):
    h = admin_headers(auth_client, auth_store)
    response = post(auth_client, h, **body)
    assert response.status_code == 422
    assert "queues" not in response.text and "finance_private" not in response.text


def test_missing_scope_is_rejected(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    assert auth_client.post(URL, headers=h, json={}).status_code == 422


def test_current_grant_session_csrf_and_origin_are_required(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    assert post(auth_client, {}).status_code == 403
    assert post(auth_client, {**h, "Origin": "https://invalid.example"}).status_code == 403
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "technical_admin", False)
    response = post(auth_client, h)
    assert response.status_code == 403 and "queues" not in response.text


def test_household_member_without_the_grant_is_denied(auth_client):
    h = signin(auth_client)
    response = post(auth_client, h)
    assert response.status_code == 403 and "queues" not in response.text


def test_sqlite_returns_real_states_and_one_metadata_free_audit(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    response = post(auth_client, h)
    assert response.status_code == 200
    body = response.json()
    assert body["queues"] == [
        {"key": key, "state": "none_observed"} for key in operations.WORK_QUEUES
    ]
    assert body["not_observed"] == ["calendar_sync", "routines", "work"]
    assert body["excludes"] == list(operations.WORK_EXCLUDES)
    with auth_store() as db:
        events = db.query(AuditEvent).filter(AuditEvent.event_type == "operations.work_status")
        assert [(e.result_status, e.metadata_json) for e in events] == [("success", {})]


def test_sqlite_reports_an_overdue_approved_job(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    approval = auth_client.post(
        "/api/v1/approvals",
        headers=h,
        json={"scope": "technical_admin", "payload": {"note": "synthetic"}},
    ).json()
    binding = {
        "payload_hash": approval["payload_hash"],
        "policy_version": approval["policy_version"],
    }
    decided = auth_client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        headers=h,
        json=dict(binding, decision="approve"),
    )
    assert decided.status_code == 200, decided.text
    queued = auth_client.post(
        "/api/v1/jobs",
        headers=h,
        json=dict(binding, approval_id=approval["id"], idempotency_key="synthetic-sqlite-job"),
    )
    assert queued.status_code == 201, queued.text
    assert post(auth_client, h).json()["queues"][0] == {
        "key": "approved_jobs",
        "state": "none_observed",
    }
    with auth_store.begin() as db:
        row = db.scalar(select(JobOutbox))
        row.available_at = identity.now_utc() - operations.WORK_GRACE - timedelta(seconds=1)
    assert post(auth_client, h).json()["queues"][0] == {"key": "approved_jobs", "state": "overdue"}
