"""Spec 071: the approvals list under the real restricted runtime role on PostgreSQL."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from conftest import SYNTHETIC_PASSWORD
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError

from app import identity
from app.manage import provision
from app.models import Approval, AuditEvent, AuthSession, User

pytestmark = pytest.mark.integration


def reviewed(record):
    return {"payload_hash": record["payload_hash"], "policy_version": record["policy_version"]}


def collect(client, headers, wanted=None, limit=60):
    """Follow cursors; committed synthetic rows from other tests may share the scope."""
    items, after = [], None
    for _ in range(limit):
        body = {"scope": "household_shared"}
        if after:
            body["after"] = after
        response = client.post("/api/v1/approvals/query", headers=headers, json=body)
        assert response.status_code == 200
        page = response.json()
        items += page["items"]
        after = page["next_cursor"]
        if after is None or (wanted and any(i["id"] == wanted for i in items)):
            break
    return items


def own_events(admin, user_id, since):
    with admin() as db:
        return list(
            db.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.event_type == "approval.query",
                    AuditEvent.initiator_id == str(user_id),
                    AuditEvent.occurred_at >= since,
                )
                .order_by(AuditEvent.occurred_at)
            )
        )


def test_runtime_role_lists_pending_and_writes_one_event_per_request(scenario):
    client, headers, record, admin, user_id = scenario
    since = identity.now_utc() - timedelta(seconds=1)
    items = collect(client, headers, wanted=record["id"])
    mine = [item for item in items if item["id"] == record["id"]]
    assert len(mine) == 1 and mine[0]["requested_by_you"] is True
    assert set(mine[0]) == {
        "id",
        "scope",
        "action_type",
        "status",
        "requested_at",
        "expires_at",
        "requested_by_you",
    }
    assert all(
        item["status"] == "pending" and item["scope"] == "household_shared" for item in items
    )
    events = own_events(admin, user_id, since)
    assert events, "the runtime role must be able to append the audit event"
    for row in events:
        assert row.result_status == "success" and row.scope_key == "household_shared"
        assert set(row.metadata_json) == {"returned"} and 0 <= row.metadata_json["returned"] <= 25
        assert row.entity_id is None and row.approval_id is None
        assert row.before_json is None and row.after_json is None


def test_membership_is_enforced_and_denial_is_audited_not_listed(scenario):
    client, _, record, admin, _ = scenario
    slug = "synthetic-outsider-" + secrets.token_hex(4)
    with admin.begin() as db:
        provision(db, slug, "Synthetic Outsider", SYNTHETIC_PASSWORD, {"member_b_private"})
    since = identity.now_utc() - timedelta(seconds=1)
    response = client.post(
        "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
    )
    assert response.status_code == 200
    outsider = {"X-CSRF-Token": response.json()["csrf_token"]}
    refused = client.post(
        "/api/v1/approvals/query", headers=outsider, json={"scope": "household_shared"}
    )
    assert refused.status_code == 403 and record["id"] not in refused.text
    with admin() as db:
        outsider_id = str(db.scalar(select(User.id).where(User.slug == slug)))
        mine = select(AuditEvent).where(
            AuditEvent.initiator_id == outsider_id, AuditEvent.occurred_at >= since
        )
        names = [row.event_type for row in db.scalars(mine)]
    assert "approval.scope_denied" in names and "approval.query" not in names


def test_audit_insert_failure_withholds_the_page_and_leaves_no_event(scenario, runtime_engine):
    client, headers, record, admin, user_id = scenario
    since = identity.now_utc() - timedelta(seconds=1)
    armed = {"on": True}

    def fail(connection, cursor, statement, parameters, context, executemany):
        if armed["on"] and statement.lstrip().startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        response = client.post(
            "/api/v1/approvals/query", headers=headers, json={"scope": "household_shared"}
        )
    finally:
        armed["on"] = False
        event.remove(runtime_engine, "before_cursor_execute", fail)
    assert response.status_code == 503
    assert "items" not in response.text and record["id"] not in response.text
    assert own_events(admin, user_id, since) == []
    assert collect(client, headers, wanted=record["id"])  # the next request works


def test_list_changes_no_approval_row_and_applies_no_lazy_expiry(scenario):
    client, headers, record, admin, _ = scenario
    with admin() as db:
        before = db.get(Approval, UUID(record["id"]))
        snapshot = {c.name: getattr(before, c.name) for c in Approval.__table__.columns}
    collect(client, headers, wanted=record["id"])
    with admin() as db:
        after = db.get(Approval, UUID(record["id"]))
        assert {c.name: getattr(after, c.name) for c in Approval.__table__.columns} == snapshot


def test_decision_racing_list_reads_never_returns_a_non_pending_item(scenario):
    client, headers, record, admin, user_id = scenario
    contexts = []
    with admin.begin() as db:
        for _ in range(3):
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
            contexts.append({"Cookie": f"{identity.COOKIE}={token}", "X-CSRF-Token": csrf})

    def decide(_):
        return client.post(
            f"/api/v1/approvals/{record['id']}/decide",
            headers=contexts[0],
            json=dict(reviewed(record), decision="approve"),
        ).status_code

    def listing(index):
        seen = []
        for _ in range(4):
            response = client.post(
                "/api/v1/approvals/query",
                headers=contexts[index],
                json={"scope": "household_shared"},
            )
            seen.append((response.status_code, [i["status"] for i in response.json()["items"]]))
        return seen

    with ThreadPoolExecutor(max_workers=3) as pool:
        decision = pool.submit(decide, 0)
        readers = [pool.submit(listing, 1), pool.submit(listing, 2)]
        outcome, reads = decision.result(), [r.result() for r in readers]
    assert outcome == 200
    for status, statuses in [pair for batch in reads for pair in batch]:
        assert status == 200 and set(statuses) <= {"pending"}
    after = collect(client, headers)
    assert record["id"] not in {item["id"] for item in after}
