"""Actual restricted runtime, JSON history, concurrent writers and rollback for staged ideas."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from test_discovery import proposal

from app import discovery, identity
from app.manage import set_scope
from app.models import AuthSession, MemoryRecord, MemoryRevision, User

pytestmark = pytest.mark.integration


def create(scenario):
    client, headers, _, admin, user_id = scenario
    with admin.begin() as db:
        set_scope(db, db.get(User, user_id), "member_a_private", True)
    result = client.post(
        "/api/v1/discovery/ideas",
        headers=headers,
        json={
            "scope": "member_a_private",
            "title": "Synthetic runtime idea",
            "summary": "Synthetic unknowns",
        },
    )
    assert result.status_code == 201
    return result.json()


def details(row):
    body = proposal()
    body.pop("scope")
    body["expected_revision"] = row["revision"]
    return body


def test_runtime_idea_enrichment_history_export_and_redaction(scenario):
    client, headers, _, admin, _ = scenario
    row = create(scenario)
    assert row["content"]["stage"] == "idea" and not row["content"]["evidence"]
    updated = client.put(
        f"/api/v1/discovery/{row['id']}/details", headers=headers, json=details(row)
    )
    assert updated.status_code == 200 and updated.json()["content"]["stage"] == "proposal"
    assert client.get("/api/v1/discovery").json()["items"][0]["id"] == row["id"]
    history = client.get(f"/api/v1/memory/{row['id']}/history").json()["items"]
    assert [item["snapshot"]["content"]["stage"] for item in history] == ["idea", "proposal"]
    assert (
        client.post(
            f"/api/v1/memory/{row['id']}/forget", headers=headers, json={"expected_revision": 2}
        ).status_code
        == 200
    )
    with admin() as db:
        assert db.get(MemoryRecord, UUID(row["id"])).content is None
        assert (
            list(
                db.scalars(
                    select(MemoryRevision.snapshot).where(
                        MemoryRevision.memory_id == UUID(row["id"])
                    )
                )
            )
            == [None] * 3
        )


def test_real_concurrent_detail_and_feedback_writers_do_not_overwrite(scenario, runtime_engine):
    row = create(scenario)
    _, _, _, admin, user_id = scenario
    contexts = []
    with admin.begin() as db:
        for index in range(4):
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
            contexts.append((index, token, csrf))
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    body = proposal()
    body.pop("title")
    body.pop("scope")
    parsed = discovery.Proposal.model_validate(body)

    def compete(context):
        index, token, csrf = context
        with maker.begin() as db:
            kwargs = (
                {"details": parsed, "title": "Synthetic enriched"}
                if index % 2
                else {"choice": "later"}
            )
            return discovery.operate(db, token, csrf, UUID(row["id"]), expected=1, **kwargs).status

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(compete, contexts))
    assert sorted(results) == [200, 409, 409, 409]
    with admin() as db:
        record = db.get(MemoryRecord, UUID(row["id"]))
        assert record.revision == 2
        assert (record.content["stage"] == "proposal") == (record.content["feedback"] is None)
        assert (
            len(
                list(
                    db.scalars(select(MemoryRevision).where(MemoryRevision.memory_id == record.id))
                )
            )
            == 2
        )


def test_real_details_audit_failure_rolls_back_snapshot_and_history(scenario, monkeypatch):
    client, headers, _, admin, _ = scenario
    row = create(scenario)
    original = identity.audit

    def fail(db, event, *args, **kwargs):
        if event == "discovery.details":
            raise SQLAlchemyError("Synthetic details audit refusal")
        return original(db, event, *args, **kwargs)

    monkeypatch.setattr(identity, "audit", fail)
    assert (
        client.put(
            f"/api/v1/discovery/{row['id']}/details", headers=headers, json=details(row)
        ).status_code
        == 503
    )
    with admin() as db:
        record = db.get(MemoryRecord, UUID(row["id"]))
        assert record.revision == 1 and record.content["stage"] == "idea"
        assert (
            len(
                list(
                    db.scalars(select(MemoryRevision).where(MemoryRevision.memory_id == record.id))
                )
            )
            == 1
        )


def test_real_revoked_scope_refuses_idea_and_enrichment(scenario):
    client, headers, _, admin, user_id = scenario
    row = create(scenario)
    with admin.begin() as db:
        set_scope(db, db.get(User, user_id), "member_a_private", False)
    assert (
        client.put(
            f"/api/v1/discovery/{row['id']}/details", headers=headers, json=details(row)
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/discovery/ideas",
            headers=headers,
            json={"scope": "member_a_private", "title": "Synthetic denied", "summary": "Unknown"},
        ).status_code
        == 403
    )
    with admin() as db:
        assert db.get(MemoryRecord, UUID(row["id"])).revision == 1
