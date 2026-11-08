from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin

from app import identity, memory
from app.manage import set_scope
from app.models import Approval, AuditEvent, DurableJob, MemoryRecord, MemoryRevision, User


def proposal(**changes):
    body = {
        "scope": "member_b_private",
        "title": "Synthetic local tagging research",
        "topic": "synthetic-tagging",
        "summary": "Investigate synthetic metadata only",
        "evidence": [
            {
                "title": "Synthetic primary source",
                "url": "https://example.org/research",
                "observed_at": "2026-01-01T00:00:00Z",
            }
        ],
    }
    body.update(changes)
    return body


def create(client, headers, **changes):
    return client.post("/api/v1/discovery", headers=headers, json=proposal(**changes))


def feedback(
    client,
    headers,
    record,
    choice="very_interested",
    expected=1,
    note="Synthetic explicit feedback",
):
    return client.put(
        f"/api/v1/discovery/{record['id']}/feedback",
        headers=headers,
        json={"choice": choice, "note": note, "expected_revision": expected},
    )


def test_manual_unknowns_feedback_history_and_clear(auth_client, auth_store):
    headers = signin(auth_client, "bob")
    result = create(auth_client, headers)
    assert result.status_code == 201
    record = result.json()
    assert record["priority"] == 0 and record["assessment"] == "tentative"
    assert record["content"]["privacy"] == "Not assessed"
    assert record["content"]["feedback"] is None
    result = feedback(auth_client, headers, record)
    assert result.status_code == 200
    assert result.json()["revision"] == 2 and result.json()["priority"] == 100
    assert result.json()["action_authority"] == "interest_only"
    assert feedback(auth_client, headers, record).status_code == 409
    result = feedback(auth_client, headers, record, None, 2, "")
    assert result.status_code == 200 and result.json()["priority"] == 0
    assert result.json()["content"]["feedback"] is None
    history = auth_client.get(f"/api/v1/memory/{record['id']}/history").json()["items"]
    assert [row["revision"] for row in history] == [1, 2, 3]
    assert history[1]["snapshot"]["content"]["feedback"]["choice"] == "very_interested"
    with auth_store() as db:
        assert list(db.scalars(select(Approval))) == []
        assert list(db.scalars(select(DurableJob))) == []
        events = db.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "discovery.feedback")
        ).all()
        assert len(events) == 2
        assert "Synthetic explicit feedback" not in str([e.after_json for e in events])


def test_ranking_cursor_dismissed_and_reordering(auth_client):
    headers = signin(auth_client, "bob")
    records = [
        create(auth_client, headers, title=f"Synthetic proposal {i}").json() for i in range(5)
    ]
    for record, choice in zip(
        records, ["not_relevant", "covered", None, "later", "very_interested"]
    ):
        if choice:
            assert feedback(auth_client, headers, record, choice).status_code == 200
    first = auth_client.get("/api/v1/discovery?limit=2").json()
    assert [r["priority"] for r in first["items"]] == [100, 10]
    cursor = first["next_cursor"]
    second = auth_client.get(
        f"/api/v1/discovery?limit=2&after={cursor['id']}&after_priority={cursor['priority']}"
    ).json()
    assert [r["priority"] for r in second["items"]] == [0] and second["next_cursor"] is None
    all_items = auth_client.get("/api/v1/discovery?include_dismissed=true").json()["items"]
    assert [r["priority"] for r in all_items] == [100, 10, 0, -10, -20]
    assert feedback(auth_client, headers, records[0], "very_interested", 2).status_code == 200
    assert len(auth_client.get("/api/v1/discovery").json()["items"]) == 4


def test_private_owner_even_same_scope_and_revocation(auth_client, auth_store):
    headers = signin(auth_client, "bob")
    record = create(auth_client, headers).json()
    with auth_store.begin() as db:
        alice = db.scalar(select(User).where(User.slug == "alice"))
        set_scope(db, alice, "member_b_private", True)
    other = signin(auth_client)
    assert auth_client.get("/api/v1/discovery").json()["items"] == []
    assert auth_client.get(f"/api/v1/discovery/{record['id']}").status_code == 404
    assert feedback(auth_client, other, record).status_code == 404
    signin(auth_client, "bob")
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, bob, "member_b_private", False)
    assert auth_client.get("/api/v1/discovery").json()["items"] == []
    assert auth_client.get(f"/api/v1/discovery/{record['id']}").status_code == 404


@pytest.mark.parametrize(
    "scope",
    ["household_shared", "finance_private", "technical_admin", "work_private", "member_a_private"],
)
def test_forbidden_or_unassigned_scopes(auth_client, scope):
    headers = signin(auth_client, "bob")
    assert create(auth_client, headers, scope=scope).status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"topic": "invalid topic"},
        {"summary": " "},
        {"evidence": []},
        {"title": "x" * 161},
        {"owner_id": str(uuid4())},
        {"feedback": {"choice": "very_interested"}},
        {"experiment": "x" * 1001},
    ],
)
def test_invalid_proposals(auth_client, changes):
    headers = signin(auth_client, "bob")
    assert create(auth_client, headers, **changes).status_code == 422


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org",
        "https://127.0.0.1/a",
        "https://192.168.1.1/a",
        "https://a.local/a",
        "https://user:secret@example.org/a",
        "javascript:alert(1)",
    ],
)
def test_inert_source_validation(auth_client, url):
    headers = signin(auth_client, "bob")
    evidence = proposal()["evidence"]
    evidence[0]["url"] = url
    assert create(auth_client, headers, evidence=evidence).status_code == 422


def test_future_and_naive_source_dates(auth_client):
    headers = signin(auth_client, "bob")
    for value in ["2026-01-01T00:00:00", (identity.now_utc() + timedelta(days=1)).isoformat()]:
        evidence = proposal()["evidence"]
        evidence[0]["observed_at"] = value
        assert create(auth_client, headers, evidence=evidence).status_code == 422


def test_csrf_origin_and_session_and_invalid_feedback(auth_client):
    assert auth_client.get("/api/v1/discovery").status_code == 401
    headers = signin(auth_client, "bob")
    assert create(auth_client, {}).status_code == 403
    record = create(auth_client, headers).json()
    assert feedback(auth_client, {}, record).status_code == 403
    assert create(auth_client, dict(headers, Origin="https://other.example")).status_code == 403
    assert feedback(auth_client, headers, record, "approve_install").status_code == 422
    assert feedback(auth_client, headers, record, expected=True).status_code == 422
    assert auth_client.get("/api/v1/discovery?limit=51").status_code == 422
    assert auth_client.get("/api/v1/discovery?after_priority=0").status_code == 422
    assert (
        auth_client.get(f"/api/v1/discovery?after={record['id']}&after_priority=999").status_code
        == 422
    )


def test_generic_mutation_cannot_bypass_typed_validation_and_forget(auth_client, auth_store):
    headers = signin(auth_client, "bob")
    record = create(auth_client, headers).json()
    with auth_store.begin() as db:
        row = db.get(MemoryRecord, UUID(record["id"]))
        row.content = dict(row.content, schema_version=999)
    assert auth_client.get("/api/v1/discovery").status_code == 422
    assert feedback(auth_client, headers, record).status_code == 404
    assert (
        auth_client.post(
            f"/api/v1/memory/{record['id']}/forget", headers=headers, json={"expected_revision": 1}
        ).status_code
        == 200
    )
    assert auth_client.get("/api/v1/discovery").json()["items"] == []
    assert feedback(auth_client, headers, record).status_code == 404
    with auth_store() as db:
        assert list(db.scalars(select(MemoryRevision.snapshot))) == [None, None]


@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_feedback_failure_rolls_back_content_and_revision(
    auth_client, auth_store, monkeypatch, failure
):
    headers = signin(auth_client, "bob")
    record = create(auth_client, headers).json()

    def fail(*args, **kwargs):
        raise SQLAlchemyError("synthetic failure")

    if failure == "audit":
        monkeypatch.setattr(memory, "audit", fail)
    else:
        event.listen(auth_store, "before_commit", fail)
    try:
        assert feedback(auth_client, headers, record).status_code == 503
    finally:
        if failure == "commit":
            event.remove(auth_store, "before_commit", fail)
    with auth_store() as db:
        row = db.get(MemoryRecord, UUID(record["id"]))
        assert row.revision == 1 and row.content["feedback"] is None
        assert len(list(db.scalars(select(MemoryRevision)))) == 1
