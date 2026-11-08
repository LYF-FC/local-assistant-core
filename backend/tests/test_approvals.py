from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from conftest import SYNTHETIC_PASSWORD
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import approvals, identity
from app.manage import set_active, set_scope
from app.models import Approval, AuditEvent, User


def signin(client, slug="alice"):
    result = client.post("/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD})
    assert result.status_code == 200
    return {"X-CSRF-Token": result.json()["csrf_token"]}


def create(client, headers, **changes):
    body = {"scope": "household_shared", "payload": {"note": "synthetic approval"}}
    body.update(changes)
    return client.post("/api/v1/approvals", headers=headers, json=body)


def binding(record):
    return {"payload_hash": record["payload_hash"], "policy_version": record["policy_version"]}


def decide(client, headers, record, decision="approve", **changes):
    body = dict(binding(record), decision=decision, **changes)
    return client.post(f"/api/v1/approvals/{record['id']}/decide", headers=headers, json=body)


def consume(client, headers, record):
    return client.post(
        f"/api/v1/approvals/{record['id']}/consume", headers=headers, json=binding(record)
    )


def test_pending_cannot_consume_and_success_is_at_most_once(auth_client, auth_store):
    headers = signin(auth_client)
    response = create(auth_client, headers)
    assert response.status_code == 201
    record = response.json()
    assert record["status"] == "pending"
    assert consume(auth_client, headers, record).status_code == 409
    assert decide(auth_client, headers, record).json()["status"] == "approved"
    assert consume(auth_client, headers, record).json()["status"] == "consumed"
    assert consume(auth_client, headers, record).status_code == 409
    assert decide(auth_client, headers, record).status_code == 409
    with auth_store() as db:
        names = list(db.scalars(select(AuditEvent.event_type)))
        assert names.count("approval.consumed") == 1
        assert {"approval.created", "approval.approved", "approval.transition_denied"} <= set(names)


@pytest.mark.parametrize("operation", ["reject", "cancel"])
def test_terminal_decisions_cannot_be_replayed(auth_client, operation):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    if operation == "reject":
        result = decide(auth_client, headers, record, "reject")
    else:
        result = auth_client.post(
            f"/api/v1/approvals/{record['id']}/cancel", headers=headers, json=binding(record)
        )
    assert result.status_code == 200
    assert result.json()["status"] in {"rejected", "cancelled"}
    assert decide(auth_client, headers, record).status_code == 409
    assert consume(auth_client, headers, record).status_code == 409


@pytest.mark.parametrize("approved", [False, True])
def test_expiry_rejects_decisions_and_consumption(auth_client, monkeypatch, approved):
    headers = signin(auth_client)
    record = create(auth_client, headers, expires_in=60).json()
    if approved:
        assert decide(auth_client, headers, record).status_code == 200
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(seconds=61))
    assert consume(auth_client, headers, record).status_code == 409
    assert auth_client.get(f"/api/v1/approvals/{record['id']}").json()["status"] == "expired"


@pytest.mark.parametrize(
    "change", [{"payload_hash": "0" * 64}, {"policy_version": "obsolete-policy"}]
)
def test_reviewed_hash_and_policy_are_required(auth_client, change):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    body = dict(binding(record), decision="approve")
    body.update(change)
    result = auth_client.post(
        f"/api/v1/approvals/{record['id']}/decide", headers=headers, json=body
    )
    assert result.status_code == 409
    assert auth_client.get(f"/api/v1/approvals/{record['id']}").json()["status"] == "pending"


def test_changed_server_policy_invalidates_old_approval(auth_client, monkeypatch):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    assert decide(auth_client, headers, record).status_code == 200
    monkeypatch.setattr(approvals, "POLICY", "new-policy")
    assert consume(auth_client, headers, record).status_code == 409


def test_payload_tampering_is_detected_even_without_postgres_guard(auth_client, auth_store):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    with auth_store.begin() as db:
        item = db.get(Approval, UUID(record["id"]))
        item.request_payload = {"note": "tampered"}
    assert decide(auth_client, headers, record).status_code == 409


def test_cross_scope_id_is_indistinguishable_from_missing(auth_client):
    bob = signin(auth_client, "bob")
    private = create(
        auth_client, bob, scope="finance_private", payload={"private": "must not leak"}
    ).json()
    signin(auth_client)
    denied = auth_client.get(f"/api/v1/approvals/{private['id']}")
    absent = auth_client.get(f"/api/v1/approvals/{uuid4()}")
    assert denied.status_code == absent.status_code == 404
    assert denied.json() == absent.json() == {"detail": "Access denied"}
    assert "must not leak" not in denied.text


def test_unknown_scope_and_unassigned_scope_are_denied(auth_client):
    headers = signin(auth_client)
    assert create(auth_client, headers, scope="finance_private").status_code == 403
    assert create(auth_client, headers, scope="invented").status_code == 403


def test_csrf_origin_and_authentication_remain_required(auth_client):
    assert create(auth_client, {}).status_code == 401
    headers = signin(auth_client)
    assert create(auth_client, {}).status_code == 403
    assert create(auth_client, {"X-CSRF-Token": "wrong"}).status_code == 403
    assert create(auth_client, dict(headers, Origin="https://evil.example")).status_code == 403


def test_different_scope_member_can_approve_but_only_requester_can_consume(auth_client, auth_store):
    alice = signin(auth_client)
    record = create(auth_client, alice).json()
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "bob")), "household_shared", True)
    bob = signin(auth_client, "bob")
    assert decide(auth_client, bob, record).status_code == 200
    assert consume(auth_client, bob, record).status_code == 403
    assert (
        auth_client.post(
            f"/api/v1/approvals/{record['id']}/cancel", headers=bob, json=binding(record)
        ).status_code
        == 403
    )
    alice = signin(auth_client)
    assert consume(auth_client, alice, record).status_code == 200


@pytest.mark.parametrize("revoke", ["scope", "user"])
def test_revoked_approver_cannot_authorize_later_consumption(auth_client, auth_store, revoke):
    alice = signin(auth_client)
    record = create(auth_client, alice).json()
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "bob")), "household_shared", True)
    bob = signin(auth_client, "bob")
    assert decide(auth_client, bob, record).status_code == 200
    with auth_store.begin() as db:
        user = db.scalar(select(User).where(User.slug == "bob"))
        if revoke == "scope":
            set_scope(db, user, "household_shared", False)
        else:
            set_active(db, user, False)
    alice = signin(auth_client)
    assert consume(auth_client, alice, record).status_code == 409


@pytest.mark.parametrize("phase", ["flush", "commit"])
def test_approval_and_audit_are_atomic(auth_client, auth_store, phase):
    headers = signin(auth_client)

    def fail(*args):
        raise SQLAlchemyError("synthetic internal failure")

    target, name = (AuditEvent, "before_insert") if phase == "flush" else (Session, "before_commit")
    event.listen(target, name, fail)
    try:
        response = create(auth_client, headers)
    finally:
        event.remove(target, name, fail)
    assert response.status_code == 503
    with auth_store() as db:
        assert db.scalar(select(func.count()).select_from(Approval)) == 0


def test_no_external_action_type_can_be_approved(auth_client):
    headers = signin(auth_client)
    for action in ("email.send", "investment.transfer", "shell.run"):
        assert create(auth_client, headers, action_type=action).status_code == 422


@pytest.mark.parametrize(
    "payload", [{"large": "x" * 17000}, {"deep": [[[[[[[[[[1]]]]]]]]]]}, {"long": list(range(257))}]
)
def test_payload_resource_limits(auth_client, payload):
    headers = signin(auth_client)
    assert create(auth_client, headers, payload=payload).status_code == 422


def test_raw_payload_is_not_duplicated_in_audit(auth_client, auth_store):
    headers = signin(auth_client)
    secret = "synthetic-private-payload"
    record = create(auth_client, headers, payload={"note": secret}).json()
    with auth_store() as db:
        rows = db.scalars(
            select(AuditEvent).where(AuditEvent.approval_id == UUID(record["id"]))
        ).all()
        assert rows
        assert secret not in repr([(x.before_json, x.after_json, x.metadata_json) for x in rows])


def test_unbound_legacy_record_is_never_consumed(auth_client, auth_store):
    headers = signin(auth_client)
    with auth_store.begin() as db:
        user = db.scalar(select(User).where(User.slug == "alice"))
        item = Approval(
            scope_key="household_shared",
            action_type="validation.noop",
            requested_by=str(user.id),
            request_payload={},
            status="approved",
        )
        db.add(item)
        db.flush()
        identifier = str(item.id)
    result = auth_client.post(
        f"/api/v1/approvals/{identifier}/consume",
        headers=headers,
        json={"payload_hash": "0" * 64, "policy_version": approvals.POLICY},
    )
    assert result.status_code == 409
