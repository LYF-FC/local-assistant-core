"""Spec 071: read-only pending-approval list used by the unified attention inbox."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from conftest import SYNTHETIC_PASSWORD
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError

from app import identity
from app.manage import provision
from app.models import Approval, AuditEvent

ITEM_KEYS = {
    "id",
    "scope",
    "action_type",
    "status",
    "requested_at",
    "expires_at",
    "requested_by_you",
}
SECRET = "synthetic secret payload must never reach the inbox"


def signin(client, slug="alice"):
    result = client.post("/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD})
    assert result.status_code == 200
    return {"X-CSRF-Token": result.json()["csrf_token"]}


def create(client, headers, **changes):
    body = {"scope": "household_shared", "payload": {"note": SECRET}}
    body.update(changes)
    response = client.post("/api/v1/approvals", headers=headers, json=body)
    assert response.status_code == 201
    return response.json()


def query(client, headers, scope="household_shared", **body):
    return client.post("/api/v1/approvals/query", headers=headers, json=dict(scope=scope, **body))


def post(client, headers, path, body):
    response = client.post("/api/v1/approvals/" + path, headers=headers, json=body)
    assert response.status_code == 200


def binding(record):
    return {"payload_hash": record["payload_hash"], "policy_version": record["policy_version"]}


def audit_rows(auth_store, name="approval.query"):
    with auth_store() as db:
        return list(db.scalars(select(AuditEvent).where(AuditEvent.event_type == name)))


@pytest.fixture
def second_member(auth_store):
    with auth_store.begin() as db:
        provision(db, "carol", "Synthetic Carol", SYNTHETIC_PASSWORD, {"household_shared"})


def test_lists_pending_with_only_allow_listed_fields(auth_client):
    headers = signin(auth_client)
    record = create(auth_client, headers)
    response = query(auth_client, headers)
    assert response.status_code == 200
    page = response.json()
    assert set(page) == {
        "schema_version",
        "mode",
        "checked_at",
        "page_limit",
        "items",
        "next_cursor",
    }
    assert page["mode"] == "approval_page" and page["page_limit"] == 25
    assert page["next_cursor"] is None
    (item,) = page["items"]
    assert set(item) == ITEM_KEYS
    assert item["id"] == record["id"] and item["status"] == "pending"
    assert item["action_type"] == "validation.noop"
    assert item["requested_by_you"] is True
    for forbidden in (SECRET, record["payload_hash"], record["policy_version"]):
        assert forbidden not in response.text


def test_other_member_sees_pending_request_without_requester_identity(
    auth_client, auth_store, second_member
):
    alice = signin(auth_client)
    record = create(auth_client, alice)
    with auth_store() as db:
        requester = db.get(Approval, UUID(record["id"])).requested_by
    carol = signin(auth_client, "carol")
    response = query(auth_client, carol)
    (item,) = response.json()["items"]
    assert item["id"] == record["id"] and item["requested_by_you"] is False
    assert requester not in response.text
    assert set(item) == ITEM_KEYS


def test_non_member_and_unknown_scope_are_refused(auth_client):
    create(auth_client, signin(auth_client))
    bob = signin(auth_client, "bob")
    refused = query(auth_client, bob)
    assert refused.status_code == 403
    assert refused.json() == {"detail": "Access denied"}
    assert query(auth_client, bob, scope="finance_private").status_code == 422
    assert query(auth_client, bob, scope="technical_admin").status_code == 422


def test_only_pending_unexpired_bound_records_are_listed(auth_client, auth_store, monkeypatch):
    headers = signin(auth_client)
    pending = create(auth_client, headers)
    rejected = create(auth_client, headers)
    cancelled = create(auth_client, headers)
    approved = create(auth_client, headers)
    consumed = create(auth_client, headers)
    post(
        auth_client, headers, rejected["id"] + "/decide", dict(binding(rejected), decision="reject")
    )
    post(auth_client, headers, cancelled["id"] + "/cancel", binding(cancelled))
    post(
        auth_client,
        headers,
        approved["id"] + "/decide",
        dict(binding(approved), decision="approve"),
    )
    post(
        auth_client,
        headers,
        consumed["id"] + "/decide",
        dict(binding(consumed), decision="approve"),
    )
    post(auth_client, headers, consumed["id"] + "/consume", binding(consumed))
    soon = identity.now_utc() + timedelta(hours=1)
    unbound = [  # partially bound legacy rows can never authorize anything either
        {"expires_at": None},
        {"expires_at": soon, "policy_version": "legacy"},
        {"expires_at": soon, "payload_hash": "a" * 64},
    ]
    with auth_store.begin() as db:
        for fields in unbound:
            db.add(
                Approval(
                    scope_key="household_shared",
                    action_type="validation.noop",
                    requested_by=str(uuid4()),
                    request_payload={},
                    status="pending",
                    **fields,
                )
            )
    listed = query(auth_client, headers).json()["items"]
    assert [item["id"] for item in listed] == [pending["id"]]
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(seconds=901))
    assert query(auth_client, headers).json()["items"] == []


def test_expired_but_still_pending_is_excluded_without_any_write(
    auth_client, auth_store, monkeypatch
):
    headers = signin(auth_client)
    record = create(auth_client, headers, expires_in=60)
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(seconds=61))
    with auth_store() as db:
        before = db.get(Approval, UUID(record["id"]))
        snapshot = (before.status, before.resolved_at, before.approved_by, before.consumed_at)
    assert query(auth_client, headers).json()["items"] == []
    with auth_store() as db:
        after = db.get(Approval, UUID(record["id"]))
        assert (after.status, after.resolved_at, after.approved_by, after.consumed_at) == snapshot
        assert after.status == "pending"  # the list never applies the lazy expiry transition
    assert audit_rows(auth_store, "approval.expired") == []
    assert audit_rows(auth_store, "approval.read") == []


def test_paging_uses_a_26th_row_sentinel_and_audits_each_page(auth_client, auth_store):
    headers = signin(auth_client)
    created = {create(auth_client, headers, expires_in=3600)["id"] for _ in range(26)}
    first = query(auth_client, headers).json()
    assert len(first["items"]) == 25 and first["next_cursor"] == first["items"][-1]["id"]
    second = query(auth_client, headers, after=first["next_cursor"]).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    seen = [item["id"] for item in first["items"] + second["items"]]
    assert len(set(seen)) == 26 and set(seen) == created
    assert seen == sorted(seen)
    assert "total" not in first and "count" not in first
    events = audit_rows(auth_store)
    assert sorted(row.metadata_json["returned"] for row in events) == [1, 25]


def test_exactly_one_metadata_only_audit_event_per_request(auth_client, auth_store):
    headers = signin(auth_client)
    record = create(auth_client, headers)
    for _ in range(3):
        assert query(auth_client, headers).status_code == 200
    events = audit_rows(auth_store)
    assert len(events) == 3
    for row in events:
        assert row.result_status == "success" and row.scope_key == "household_shared"
        assert row.entity_type == "approval" and row.metadata_json == {"returned": 1}
        assert row.entity_id is None and row.approval_id is None and row.task_id is None
        assert row.before_json is None and row.after_json is None and row.source_context == {}
        rendered = repr(row.metadata_json)
        for forbidden in (record["id"], record["payload_hash"], SECRET):
            assert forbidden not in rendered


def test_list_does_not_change_any_approval_row(auth_client, auth_store):
    headers = signin(auth_client)
    record = create(auth_client, headers)
    with auth_store() as db:
        before = db.get(Approval, UUID(record["id"]))
        snapshot = {
            column.name: getattr(before, column.name) for column in Approval.__table__.columns
        }
    assert query(auth_client, headers).status_code == 200
    with auth_store() as db:
        after = db.get(Approval, UUID(record["id"]))
        assert {c.name: getattr(after, c.name) for c in Approval.__table__.columns} == snapshot


def test_audit_failure_withholds_the_page_and_records_nothing(auth_client, auth_store, auth_engine):
    headers = signin(auth_client)
    create(auth_client, headers)

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic audit failure")

    event.listen(auth_engine, "before_cursor_execute", fail)
    try:
        response = query(auth_client, headers)
    finally:
        event.remove(auth_engine, "before_cursor_execute", fail)
    assert response.status_code == 503
    assert "items" not in response.text and "checked_at" not in response.text
    assert audit_rows(auth_store) == []
    assert query(auth_client, headers).status_code == 200  # a later request works normally


def test_session_csrf_and_input_boundaries(auth_client, auth_store):
    anonymous = auth_client.post("/api/v1/approvals/query", json={"scope": "household_shared"})
    assert anonymous.status_code == 401
    headers = signin(auth_client)
    missing = auth_client.post("/api/v1/approvals/query", json={"scope": "household_shared"})
    assert missing.status_code == 403
    wrong = query(auth_client, {"X-CSRF-Token": "wrong"})
    assert wrong.status_code == 403
    assert query(auth_client, headers, extra=True).status_code == 422
    assert query(auth_client, headers, after="not-a-uuid").status_code == 422
    assert audit_rows(auth_store) == []  # refusals record denial events, never a success event


def test_other_approval_routes_are_unaffected(auth_client):
    headers = signin(auth_client)
    record = create(auth_client, headers)
    assert auth_client.get(f"/api/v1/approvals/{record['id']}").status_code == 200
    assert query(auth_client, headers).status_code == 200


def test_a_member_of_two_scopes_sees_only_the_requested_scope(auth_client, auth_store):
    with auth_store.begin() as db:
        provision(
            db,
            "dana",
            "Synthetic Dana",
            SYNTHETIC_PASSWORD,
            {"household_shared", "member_b_private"},
        )
    shared = create(auth_client, signin(auth_client))
    private = create(
        auth_client, signin(auth_client, "bob"), scope="member_b_private", payload={"p": "x"}
    )
    dana = signin(auth_client, "dana")
    assert [i["id"] for i in query(auth_client, dana).json()["items"]] == [shared["id"]]
    only = query(auth_client, dana, scope="member_b_private").json()["items"]
    assert [i["id"] for i in only] == [private["id"]]
    assert only[0]["scope"] == "member_b_private"
    carol_less = signin(auth_client)
    assert private["id"] not in query(auth_client, carol_less).text
