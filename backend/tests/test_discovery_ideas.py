from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_discovery import proposal

from app import identity, memory
from app.manage import set_scope
from app.models import (
    Approval,
    AuditEvent,
    AuthSession,
    DurableJob,
    MemoryRecord,
    MemoryRevision,
    User,
)


def idea(client, headers, **changes):
    body = {
        "scope": "member_b_private",
        "title": "Synthetic idea",
        "summary": "Synthetic unassessed idea",
    }
    return client.post("/api/v1/discovery/ideas", headers=headers, json=dict(body, **changes))


def enrich(client, headers, record, **changes):
    body = proposal()
    body.pop("scope")
    return client.put(
        f"/api/v1/discovery/{record['id']}/details",
        headers=headers,
        json=dict(body, expected_revision=record["revision"], **changes),
    )


def test_idea_unknowns_enrichment_feedback_export_history_and_forgetting(auth_client, auth_store):
    headers = signin(auth_client, "bob")
    result = idea(auth_client, headers)
    assert result.status_code == 201
    row = result.json()
    assert row["content"]["stage"] == "idea" and row["content"]["schema_version"] == 2
    assert row["content"]["evidence"] == [] and row["content"]["topic"] == "unclassified"
    assert row["content"]["privacy"] == "Not assessed" and row["assessment"] == "tentative"
    assert row["action_authority"] == "interest_only" and row["priority"] == 0
    feedback = auth_client.put(
        f"/api/v1/discovery/{row['id']}/feedback",
        headers=headers,
        json={"expected_revision": 1, "choice": "later", "note": "Synthetic interest"},
    )
    assert feedback.status_code == 200
    row = feedback.json()
    result = enrich(auth_client, headers, row)
    assert result.status_code == 200
    updated = result.json()
    assert updated["revision"] == 3 and updated["content"]["stage"] == "proposal"
    assert (
        updated["content"]["feedback"] == row["content"]["feedback"] and updated["priority"] == 10
    )
    assert (
        updated["assessment"] == "tentative"
        and "evidence not verified" in updated["source_reference"]
    )
    assert enrich(auth_client, headers, row).status_code == 409
    history = auth_client.get(f"/api/v1/memory/{row['id']}/history").json()["items"]
    assert [item["snapshot"]["content"]["stage"] for item in history] == [
        "idea",
        "idea",
        "proposal",
    ]
    exported = auth_client.get("/api/v1/memory/export").json()["items"]
    assert next(item for item in exported if item["id"] == row["id"])["content"]["evidence"]
    with auth_store() as db:
        assert (
            list(db.scalars(select(Approval))) == [] and list(db.scalars(select(DurableJob))) == []
        )
        audit = db.scalar(select(AuditEvent).where(AuditEvent.event_type == "discovery.details"))
        assert audit and audit.after_json == {"revision": 3}
    assert (
        auth_client.post(
            f"/api/v1/memory/{row['id']}/forget", headers=headers, json={"expected_revision": 3}
        ).status_code
        == 200
    )
    assert auth_client.get(f"/api/v1/discovery/{row['id']}").status_code == 404
    with auth_store() as db:
        assert list(db.scalars(select(MemoryRevision.snapshot))) == [None] * 4


def test_v1_details_preserve_all_evidence_feedback_and_custom_provenance(auth_client):
    headers = signin(auth_client, "bob")
    row = auth_client.post("/api/v1/discovery", headers=headers, json=proposal()).json()
    values = {
        key: row[key]
        for key in [
            "title",
            "content",
            "source_type",
            "source_reference",
            "assessment",
            "expires_at",
        ]
    }
    values.update(
        source_reference="Synthetic owner reference",
        source_type="document",
        assessment="confirmed",
        expected_revision=1,
    )
    row = auth_client.patch(f"/api/v1/memory/{row['id']}", headers=headers, json=values).json()
    evidence = proposal()["evidence"] * 2
    result = enrich(auth_client, headers, row, evidence=evidence)
    assert result.status_code == 200
    updated = result.json()
    assert updated["content"]["schema_version"] == 2 and len(updated["content"]["evidence"]) == 2
    assert (
        updated["source_reference"] == "Synthetic owner reference"
        and updated["source_type"] == "document"
    )
    assert updated["assessment"] == "confirmed"


@pytest.mark.parametrize(
    "changes",
    [
        {"summary": " "},
        {"title": "x" * 161},
        {"topic": "bad topic"},
        {"evidence": []},
        {"feedback": None},
        {"assessment": "confirmed"},
        {"stage": "proposal"},
        {"owner_id": "invented"},
    ],
)
def test_idea_rejects_hidden_evidence_authority_or_invalid_input(auth_client, changes):
    headers = signin(auth_client, "bob")
    assert idea(auth_client, headers, **changes).status_code == 422


@pytest.mark.parametrize(
    "fault", ["empty", "future", "naive", "private", "stage", "revision", "extra"]
)
def test_details_retain_evidence_and_revision_rules(auth_client, fault):
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()
    body = proposal()
    body.pop("scope")
    body["expected_revision"] = 1
    if fault == "empty":
        body["evidence"] = []
    if fault == "future":
        body["evidence"][0]["observed_at"] = "2999-01-01T00:00:00Z"
    if fault == "naive":
        body["evidence"][0]["observed_at"] = "2026-01-01T00:00:00"
    if fault == "private":
        body["evidence"][0]["url"] = "https://127.0.0.1/source"
    if fault == "stage":
        body["stage"] = "proposal"
    if fault == "revision":
        body["expected_revision"] = True
    if fault == "extra":
        body["owner_id"] = "invented"
    assert (
        auth_client.put(
            f"/api/v1/discovery/{row['id']}/details", headers=headers, json=body
        ).status_code
        == 422
    )
    assert auth_client.get(f"/api/v1/discovery/{row['id']}").json()["revision"] == 1


def test_owner_scope_revocation_session_origin_and_csrf(auth_client, auth_store):
    assert idea(auth_client, {}).status_code == 401
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()
    assert idea(auth_client, {}).status_code == 403
    assert idea(auth_client, dict(headers, Origin="https://other.invalid")).status_code == 403
    assert idea(auth_client, headers, scope="household_shared").status_code == 403
    assert enrich(auth_client, {}, row).status_code == 403
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "member_b_private", True)
    other = signin(auth_client)
    assert enrich(auth_client, other, row).status_code == 404
    headers = signin(auth_client, "bob")
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "bob")), "member_b_private", False)
    assert enrich(auth_client, headers, row).status_code == 404
    assert idea(auth_client, headers).status_code == 403


@pytest.mark.parametrize(
    "fault",
    [
        "missing_stage",
        "wrong_stage",
        "idea_with_evidence",
        "proposal_without_evidence",
        "unknown_version",
    ],
)
def test_invalid_v2_envelopes_fail_closed(auth_client, auth_store, fault):
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()
    with auth_store.begin() as db:
        record = db.get(MemoryRecord, UUID(row["id"]))
        content = dict(record.content)
        if fault == "missing_stage":
            content.pop("stage")
        if fault == "wrong_stage":
            content["stage"] = "approved"
        if fault == "idea_with_evidence":
            content["evidence"] = proposal()["evidence"]
        if fault == "proposal_without_evidence":
            content["stage"] = "proposal"
        if fault == "unknown_version":
            content["schema_version"] = 999
        record.content = content
    assert auth_client.get(f"/api/v1/discovery/{row['id']}").status_code == 404
    assert auth_client.get("/api/v1/discovery").status_code == 422


@pytest.mark.parametrize("failure", ["memory_audit", "details_audit", "commit"])
def test_details_failure_rolls_back_content_and_history(
    auth_client, auth_store, monkeypatch, failure
):
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()

    def fail(*args, **kwargs):
        raise SQLAlchemyError("Synthetic failure")

    original = identity.audit

    def audit(*args, **kwargs):
        if len(args) > 1 and args[1] == "discovery.details":
            fail()
        return original(*args, **kwargs)

    if failure == "memory_audit":
        monkeypatch.setattr(memory, "audit", fail)
    if failure == "details_audit":
        monkeypatch.setattr(identity, "audit", audit)
    if failure == "commit":
        event.listen(auth_store, "before_commit", fail)
    try:
        assert enrich(auth_client, headers, row).status_code == 503
    finally:
        if failure == "commit":
            event.remove(auth_store, "before_commit", fail)
    with auth_store() as db:
        record = db.get(MemoryRecord, UUID(row["id"]))
        assert (
            record.revision == 1
            and record.content["stage"] == "idea"
            and record.content["evidence"] == []
        )
        assert len(list(db.scalars(select(MemoryRevision)))) == 1


def test_expired_idea_and_revoked_session_refuse_enrichment(auth_client, auth_store):
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()
    assert (
        enrich(auth_client, dict(headers, Origin="https://other.invalid"), row).status_code == 403
    )
    with auth_store.begin() as db:
        record = db.get(MemoryRecord, UUID(row["id"]))
        record.expires_at = identity.now_utc() - timedelta(seconds=1)
    assert enrich(auth_client, headers, row).status_code == 404
    with auth_store.begin() as db:
        for session in db.scalars(select(AuthSession)):
            session.revoked_at = identity.now_utc()
    assert idea(auth_client, headers).status_code == 401
    assert enrich(auth_client, headers, row).status_code == 401
