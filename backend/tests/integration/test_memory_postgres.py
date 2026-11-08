"""Scope ownership, concurrent revision fencing and scrub-all history on PostgreSQL."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app import identity, memory
from app.models import AuthSession, MemoryRecord, MemoryRevision

pytestmark = pytest.mark.integration


def values():
    return {
        "title": "Synthetic PG memory",
        "content": {"value": "synthetic-pg-only"},
        "source_type": "manual",
        "source_reference": "synthetic-pg-ref",
        "assessment": "confirmed",
        "expires_at": None,
    }


def create(scenario):
    client, headers, _, _, _ = scenario
    response = client.post(
        "/api/v1/memory",
        headers=headers,
        json={"scope": "household_shared", "kind": "preference", **values()},
    )
    assert response.status_code == 201
    return response.json()


def test_runtime_memory_revision_and_forgetting(scenario, runtime_engine):
    client, headers, _, admin, _ = scenario
    record = create(scenario)
    response = client.patch(
        "/api/v1/memory/" + record["id"],
        headers=headers,
        json={"expected_revision": 1, **values(), "content": {"value": "synthetic-correction"}},
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/v1/memory/" + record["id"] + "/forget",
            headers=headers,
            json={"expected_revision": 2},
        ).status_code
        == 200
    )
    with admin() as db:
        assert db.get(MemoryRecord, UUID(record["id"])).content is None
        assert list(
            db.scalars(
                select(MemoryRevision.snapshot).where(
                    MemoryRevision.memory_id == UUID(record["id"])
                )
            )
        ) == [None, None, None]
    assert client.get("/api/v1/memory/" + record["id"]).status_code == 410


def test_distinct_session_edit_race_has_one_winner(scenario, runtime_engine):
    _, _, _, admin, user_id = scenario
    record = create(scenario)
    contexts = []
    with admin.begin() as db:
        for _ in range(8):
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
            contexts.append((token, csrf))
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)

    def compete(context):
        with maker.begin() as db:
            return memory.operate(
                db, *context, UUID(record["id"]), operation="correct", expected=1, values=values()
            ).status

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(compete, contexts))
    assert sorted(outcomes) == [200] + [409] * 7
    with admin() as db:
        assert db.get(MemoryRecord, UUID(record["id"])).revision == 2
        assert (
            len(
                db.scalars(
                    select(MemoryRevision).where(MemoryRevision.memory_id == UUID(record["id"]))
                ).all()
            )
            == 2
        )


def test_runtime_cannot_rewrite_context_history_or_administer(
    scenario, runtime_engine, postgres_engine
):
    record = create(scenario)
    for statement in (
        "UPDATE memory_records SET scope_key='finance_private',revision=revision+1 WHERE id=:id",
        "UPDATE memory_records SET title='unversioned' WHERE id=:id",
        "UPDATE memory_revisions SET snapshot=NULL WHERE memory_id=:id",
        "UPDATE memory_revisions SET revision=revision+1 WHERE memory_id=:id",
        "DELETE FROM memory_revisions WHERE memory_id=:id",
        "DELETE FROM memory_records WHERE id=:id",
        "ALTER TABLE memory_records DISABLE TRIGGER ALL",
        "TRUNCATE memory_revisions",
    ):
        with pytest.raises(DBAPIError), runtime_engine.begin() as db:
            db.execute(text(statement), {"id": UUID(record["id"])})
    # Ordinary owner DML is guarded too; privileged DDL/restore is separate.
    with pytest.raises(DBAPIError), postgres_engine.begin() as db:
        db.execute(text("TRUNCATE memory_revisions"))
