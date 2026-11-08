from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_discovery import create, feedback
from test_discovery_ideas import idea

from app import identity
from app.manage import set_scope
from app.models import AuditEvent, MemoryRecord, User


def preview(client, headers, rows, **changes):
    body = {
        "scope": "member_b_private",
        "purpose": "preview",
        "selections": [{"id": r["id"], "expected_revision": r["revision"]} for r in rows],
    }
    return client.post("/api/v1/discovery/digest", headers=headers, json=dict(body, **changes))


def download(client, headers, rows, reviewed, **changes):
    body = {
        "scope": "member_b_private",
        "purpose": "download",
        "selections": [{"id": r["id"], "expected_revision": r["revision"]} for r in rows],
        "review_id": reviewed["review_id"],
        "reviewed_hash": reviewed["reviewed_hash"],
        "acknowledge_copy_limits": True,
    }
    body.update(changes)
    return client.post("/api/v1/discovery/digest", headers=headers, json=body)


def test_ordered_complete_review_and_fresh_acknowledged_copy_with_minimal_receipt(
    auth_client, auth_store
):
    headers = signin(auth_client, "bob")
    rows = [create(auth_client, headers).json(), idea(auth_client, headers).json()]
    result = preview(auth_client, headers, rows)
    assert result.status_code == 200
    reviewed = result.json()
    assert [r["id"] for r in reviewed["bundle"]["items"]] == [r["id"] for r in rows]
    assert (
        reviewed["bundle"]["retain_until"] is None
        and reviewed["bundle"]["execution_allowed"] is False
    )
    assert (
        0
        < (
            identity.aware(datetime.fromisoformat(reviewed["valid_until"])) - identity.now_utc()
        ).total_seconds()
        <= 60
    )
    fresh = download(auth_client, headers, rows, reviewed)
    assert fresh.status_code == 200
    value = fresh.json()
    assert (
        value["reviewed_hash"] == reviewed["reviewed_hash"]
        and value["review_id"] == reviewed["review_id"]
    )
    assert (
        value["bundle"]["export_id"] != reviewed["bundle"]["export_id"]
        and value["bundle"]["items"] == reviewed["bundle"]["items"]
    )
    # Repeated local copy checks are allowed within the same live review; this is not one-time action authority.
    assert download(auth_client, headers, rows, reviewed).status_code == 200
    with auth_store() as db:
        events = db.scalars(
            select(AuditEvent).where(AuditEvent.event_type.like("discovery.digest_%"))
        ).all()
        assert len(events) == 3
        assert set(events[0].metadata_json) == {
            "schema_version",
            "session_id",
            "reviewed_hash",
            "selected_count",
            "valid_until",
            "export_id",
        }
        assert "Synthetic" not in str([r.metadata_json for r in events])


@pytest.mark.parametrize(
    "change",
    [
        {"selections": []},
        {"selections": [{"id": str(uuid4()), "expected_revision": True}]},
        {"purpose": "send"},
        {"scope": "work_private"},
        {"review_id": str(uuid4())},
        {"reviewed_hash": "a" * 64},
        {"acknowledge_copy_limits": True},
        {"title": "private report title"},
    ],
)
def test_invalid_preview_contract(auth_client, change):
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()
    assert preview(auth_client, headers, [row], **change).status_code == 422


@pytest.mark.parametrize(
    "fault", ["duplicate", "overflow", "ack", "hash", "receipt", "reorder", "revision", "scope"]
)
def test_exact_download_bindings(auth_client, fault):
    headers = signin(auth_client, "bob")
    rows = [idea(auth_client, headers).json(), create(auth_client, headers).json()]
    reviewed = preview(auth_client, headers, rows).json()
    changes = {}
    status = 409
    if fault == "duplicate":
        rows = [rows[0]] * 2
        status = 422
    if fault == "overflow":
        rows = rows * 6
        status = 422
    if fault == "ack":
        changes["acknowledge_copy_limits"] = False
        status = 422
    if fault == "hash":
        changes["reviewed_hash"] = "b" * 64
    if fault == "receipt":
        changes["review_id"] = str(uuid4())
    if fault == "reorder":
        rows = rows[::-1]
    if fault == "revision":
        rows[0]["revision"] = 2
    if fault == "scope":
        changes["scope"] = "member_a_private"
        status = 403
    assert download(auth_client, headers, rows, reviewed, **changes).status_code == status


def test_feedback_change_forgetting_and_other_scope_record_refuse_whole_copy(
    auth_client, auth_store
):
    headers = signin(auth_client, "bob")
    rows = [create(auth_client, headers).json(), idea(auth_client, headers).json()]
    reviewed = preview(auth_client, headers, rows).json()
    assert feedback(auth_client, headers, rows[0], "later").status_code == 200
    assert download(auth_client, headers, rows, reviewed).status_code == 409
    assert (
        auth_client.post(
            f"/api/v1/memory/{rows[1]['id']}/forget", headers=headers, json={"expected_revision": 1}
        ).status_code
        == 200
    )
    assert download(auth_client, headers, rows, reviewed).status_code == 404
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "bob")), "member_a_private", True)
    other = idea(auth_client, headers, scope="member_a_private").json()
    assert preview(auth_client, headers, [rows[0], other]).status_code == 404


def test_owner_scope_session_origin_csrf_and_session_bound_review(auth_client, auth_store):
    assert preview(auth_client, {}, [{"id": str(uuid4()), "revision": 1}]).status_code == 401
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()
    reviewed = preview(auth_client, headers, [row]).json()
    assert preview(auth_client, {}, [row]).status_code == 403
    assert (
        download(
            auth_client, dict(headers, Origin="https://other.invalid"), [row], reviewed
        ).status_code
        == 403
    )
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "member_b_private", True)
    other = signin(auth_client)
    assert preview(auth_client, other, [row]).status_code == 404
    assert download(auth_client, other, [row], reviewed).status_code == 409
    headers = signin(auth_client, "bob")
    assert download(auth_client, headers, [row], reviewed).status_code == 409
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "bob")), "member_b_private", False)
    assert preview(auth_client, headers, [row]).status_code == 403


def test_expiry_deadline_and_payload_budget(auth_client, auth_store, monkeypatch):
    headers = signin(auth_client, "bob")
    row = create(auth_client, headers).json()
    now = identity.now_utc()
    expiry = now + timedelta(seconds=20)
    with auth_store.begin() as db:
        db.get(MemoryRecord, UUID(row["id"])).expires_at = expiry
    reviewed = preview(auth_client, headers, [row]).json()
    assert (
        reviewed["bundle"]["retain_until"] == expiry.isoformat()
        and reviewed["valid_until"] == expiry.isoformat()
    )
    monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(seconds=21))
    assert download(auth_client, headers, [row], reviewed).status_code == 404


def test_stale_review_time_and_oversized_selection(auth_client, monkeypatch):
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()
    reviewed = preview(auth_client, headers, [row]).json()
    now = identity.now_utc()
    with monkeypatch.context() as changed:
        changed.setattr(identity, "now_utc", lambda: now + timedelta(seconds=61))
        assert download(auth_client, headers, [row], reviewed).status_code == 409
    evidence = [
        {
            "title": "x" * 160,
            "url": "https://example.org/" + "x" * 480,
            "observed_at": "2026-01-01T00:00:00Z",
        }
    ] * 5
    rows = [
        create(
            auth_client,
            headers,
            title="x" * 160,
            summary="x" * 1000,
            evidence=evidence,
            benefit="x" * 512,
            privacy="x" * 512,
            maturity_license="x" * 512,
            hardware_cost="x" * 512,
            alternatives_dependencies="x" * 512,
            experiment="x" * 1000,
        ).json()
        for _ in range(10)
    ]
    assert preview(auth_client, headers, rows).status_code == 413


@pytest.mark.parametrize("phase", ["preview", "download"])
@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_no_payload_or_receipt_success_on_audit_or_commit_failure(
    auth_client, auth_store, monkeypatch, phase, failure
):
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()
    reviewed = preview(auth_client, headers, [row]).json()
    original = identity.audit

    def fail(*args, **kwargs):
        raise SQLAlchemyError("Synthetic digest failure")

    def audit(db, event, *args, **kwargs):
        if event == "discovery.digest_" + phase:
            fail()
        return original(db, event, *args, **kwargs)

    if failure == "audit":
        monkeypatch.setattr(identity, "audit", audit)
    else:
        event.listen(auth_store, "before_commit", fail)
    try:
        response = (
            preview(auth_client, headers, [row])
            if phase == "preview"
            else download(auth_client, headers, [row], reviewed)
        )
        assert response.status_code == 503 and "bundle" not in response.json()
    finally:
        if failure == "commit":
            event.remove(auth_store, "before_commit", fail)
    with auth_store() as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(AuditEvent).where(AuditEvent.event_type.like("discovery.digest_%"))
                    )
                )
            )
            == 1
        )


def test_slow_commit_never_releases_an_expired_bundle(auth_client, auth_store, monkeypatch):
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()
    now = identity.now_utc()

    def delay(*args):
        monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(seconds=61))

    event.listen(auth_store, "before_commit", delay)
    try:
        result = preview(auth_client, headers, [row])
        assert result.status_code == 409 and "bundle" not in result.json()
    finally:
        event.remove(auth_store, "before_commit", delay)
    with auth_store() as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(AuditEvent).where(
                            AuditEvent.event_type == "discovery.digest_preview"
                        )
                    )
                )
            )
            == 1
        )
