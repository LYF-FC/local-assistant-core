from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin

from app import identity, memory
from app.manage import set_scope
from app.models import AuditEvent, MemoryRecord, MemoryRevision, User


def content(**changes):
    value = {
        "title": "Synthetic preference",
        "content": {"value": "synthetic-only"},
        "source_type": "feedback",
        "source_reference": "synthetic-source-1",
        "assessment": "confirmed",
        "expires_at": None,
    }
    value.update(changes)
    return value


def create(client, headers, **changes):
    body = dict(scope="household_shared", kind="preference", **content())
    body.update(changes)
    return client.post("/api/v1/memory", headers=headers, json=body)


def patch(client, headers, record, expected=1, **changes):
    return client.patch(
        "/api/v1/memory/" + record["id"],
        headers=headers,
        json=dict(expected_revision=expected, **content(**changes)),
    )


def test_explicit_create_correct_history_and_stale_conflict(auth_client):
    headers = signin(auth_client)
    response = create(auth_client, headers)
    assert response.status_code == 201
    record = response.json()
    assert record["assessment"] == "confirmed"
    assert record["revision"] == 1
    response = patch(
        auth_client,
        headers,
        record,
        content={"value": "corrected"},
        source_reference="synthetic-source-2",
    )
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert patch(auth_client, headers, record).status_code == 409
    history = auth_client.get("/api/v1/memory/" + record["id"] + "/history").json()["items"]
    assert [row["revision"] for row in history] == [1, 2]
    assert history[0]["historical"] is True
    assert history[0]["snapshot"]["content"] == {"value": "synthetic-only"}
    assert history[1]["snapshot"]["content"] == {"value": "corrected"}


def test_private_records_require_owner_even_with_same_scope(auth_client, auth_store):
    bob_headers = signin(auth_client, "bob")
    record = create(auth_client, bob_headers, scope="finance_private").json()
    with auth_store.begin() as db:
        alice = db.scalar(select(User).where(User.slug == "alice"))
        set_scope(db, alice, "finance_private", True)
    signin(auth_client)
    for identifier in (record["id"], str(uuid4())):
        response = auth_client.get("/api/v1/memory/" + identifier)
        assert response.status_code == 404
        assert response.json() == {"detail": "Access denied"}
    assert auth_client.get("/api/v1/memory").json()["items"] == []
    assert auth_client.get("/api/v1/memory/export").json()["items"] == []


def test_shared_reader_cannot_edit_forget_or_read_history(auth_client, auth_store):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, bob, "household_shared", True)
    bob_headers = signin(auth_client, "bob")
    assert auth_client.get("/api/v1/memory/" + record["id"]).status_code == 200
    assert patch(auth_client, bob_headers, record).status_code == 403
    assert (
        auth_client.post(
            "/api/v1/memory/" + record["id"] + "/forget",
            headers=bob_headers,
            json={"expected_revision": 1},
        ).status_code
        == 403
    )
    assert auth_client.get("/api/v1/memory/" + record["id"] + "/history").status_code == 403


def test_scope_revocation_and_no_admin_or_work_content(auth_client, auth_store):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    with auth_store.begin() as db:
        alice = db.scalar(select(User).where(User.slug == "alice"))
        set_scope(db, alice, "household_shared", False)
        set_scope(db, alice, "technical_admin", True)
    assert auth_client.get("/api/v1/memory/" + record["id"]).status_code == 404
    assert create(auth_client, headers, scope="technical_admin").status_code == 403
    assert create(auth_client, headers, scope="work_private").status_code == 403


def test_forget_scrubs_current_and_every_snapshot(auth_client, auth_store):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    assert (
        patch(
            auth_client,
            headers,
            record,
            title="Synthetic revised",
            source_reference="second-source",
        ).status_code
        == 200
    )
    response = auth_client.post(
        "/api/v1/memory/" + record["id"] + "/forget", headers=headers, json={"expected_revision": 2}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "forgotten"
    assert "content" not in response.json()
    assert patch(auth_client, headers, record, expected=3).status_code == 410
    assert auth_client.get("/api/v1/memory/" + record["id"]).status_code == 410
    assert auth_client.get("/api/v1/memory").json()["items"] == []
    exported = auth_client.get("/api/v1/memory/export?include_forgotten=true").json()["items"]
    assert len(exported) == 1 and "content" not in exported[0]
    with auth_store() as db:
        row = db.get(MemoryRecord, UUID(record["id"]))
        assert all(
            getattr(row, key) is None
            for key in (
                "title",
                "content",
                "source_type",
                "source_reference",
                "assessment",
                "expires_at",
            )
        )
        assert list(db.scalars(select(MemoryRevision.snapshot))) == [None, None, None]
        events = db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "memory")).all()
        assert "synthetic-only" not in str(
            [(e.before_json, e.after_json, e.metadata_json) for e in events]
        )
        assert "second-source" not in str(
            [(e.before_json, e.after_json, e.metadata_json) for e in events]
        )


def test_expiry_excluded_but_owner_can_explicitly_inspect(auth_client, auth_store, monkeypatch):
    now = identity.now_utc()
    headers = signin(auth_client)
    record = create(
        auth_client, headers, kind="context", expires_at=(now + timedelta(seconds=60)).isoformat()
    ).json()
    monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(seconds=61))
    response = auth_client.get("/api/v1/memory/" + record["id"])
    assert response.status_code == 410 and "content" not in response.json()
    assert auth_client.get("/api/v1/memory").json()["items"] == []
    result = auth_client.get("/api/v1/memory/" + record["id"] + "?include_expired=true").json()
    assert result["expired"] is True and result["eligible_for_context"] is False
    assert len(auth_client.get("/api/v1/memory/export?include_expired=true").json()["items"]) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "context"},
        {"expires_at": "2020-01-01T00:00:00Z"},
        {"expires_at": "2030-01-01T00:00:00"},
        {"content": {"value": "x" * 17000}},
        {"content": {"x": [[[[[[[[[1]]]]]]]]]}},
        {"owner_id": str(uuid4())},
        {"assessment": "automatically_confirmed"},
        {"source_reference": ""},
    ],
)
def test_invalid_or_unbounded_content_rejected(auth_client, changes):
    headers = signin(auth_client)
    assert create(auth_client, headers, **changes).status_code == 422


def test_requires_csrf_and_cannot_move_owner_scope_or_kind(auth_client):
    headers = signin(auth_client)
    assert create(auth_client, {}).status_code == 403
    record = create(auth_client, headers).json()
    assert patch(auth_client, {}, record).status_code == 403
    for field, value in [
        ("owner_id", str(uuid4())),
        ("scope", "finance_private"),
        ("kind", "profile"),
    ]:
        response = auth_client.patch(
            "/api/v1/memory/" + record["id"],
            headers=headers,
            json=dict(expected_revision=1, **content(), **{field: value}),
        )
        assert response.status_code == 422


def test_export_and_history_are_bounded_cursor_pages(auth_client):
    headers = signin(auth_client)
    identifiers = {create(auth_client, headers).json()["id"] for _ in range(3)}
    first = auth_client.get("/api/v1/memory/export?limit=2")
    assert "attachment" in first.headers["content-disposition"]
    assert first.json()["schema_version"] == 1
    cursor = first.json()["next_cursor"]
    second = auth_client.get("/api/v1/memory/export?limit=2&after=" + cursor).json()
    assert {row["id"] for row in first.json()["items"] + second["items"]} == identifiers
    assert second["next_cursor"] is None
    assert auth_client.get("/api/v1/memory?limit=51").status_code == 422
    record = first.json()["items"][0]
    patch(auth_client, headers, record)
    one = auth_client.get("/api/v1/memory/" + record["id"] + "/history?limit=1").json()
    assert one["next_cursor"] == 1
    two = auth_client.get("/api/v1/memory/" + record["id"] + "/history?after=1&limit=1").json()
    assert two["items"][0]["revision"] == 2 and two["next_cursor"] is None


@pytest.mark.parametrize("operation", ["create", "correct", "forget"])
@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_memory_failure_is_atomic(auth_client, auth_store, monkeypatch, operation, failure):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()

    def fail(*args, **kwargs):
        raise SQLAlchemyError("synthetic failure")

    if failure == "audit":
        monkeypatch.setattr(memory, "audit", fail)
    else:
        event.listen(auth_store, "before_commit", fail)
    try:
        if operation == "create":
            response = create(auth_client, headers)
        elif operation == "correct":
            response = patch(auth_client, headers, record)
        else:
            response = auth_client.post(
                "/api/v1/memory/" + record["id"] + "/forget",
                headers=headers,
                json={"expected_revision": 1},
            )
        assert response.status_code == 503 and "content" not in response.json()
    finally:
        if failure == "commit":
            event.remove(auth_store, "before_commit", fail)
    with auth_store() as db:
        row = db.get(MemoryRecord, UUID(record["id"]))
        assert row.revision == 1 and row.content == {"value": "synthetic-only"}
        assert len(db.scalars(select(MemoryRecord)).all()) == 1
        assert len(db.scalars(select(MemoryRevision)).all()) == 1
