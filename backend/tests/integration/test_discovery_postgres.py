"""Use existing restricted role, guards and real PostgreSQL JSON ordering/locks."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
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
        "/api/v1/discovery", headers=headers, json=proposal(scope="member_a_private")
    )
    assert result.status_code == 201
    return result.json()


def test_runtime_discovery_json_rank_history_and_forgetting(scenario):
    client, headers, _, admin, _ = scenario
    record = create(scenario)
    result = client.put(
        f"/api/v1/discovery/{record['id']}/feedback",
        headers=headers,
        json={"choice": "very_interested", "expected_revision": 1},
    )
    assert result.status_code == 200
    items = client.get("/api/v1/discovery").json()["items"]
    assert any(row["id"] == record["id"] and row["priority"] == 100 for row in items)
    assert (
        client.post(
            f"/api/v1/memory/{record['id']}/forget", headers=headers, json={"expected_revision": 2}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/discovery").json()["items"] == []
    with admin() as db:
        assert db.get(MemoryRecord, UUID(record["id"])).content is None
        assert list(
            db.scalars(
                select(MemoryRevision.snapshot).where(
                    MemoryRevision.memory_id == UUID(record["id"])
                )
            )
        ) == [None, None, None]


def test_distinct_sessions_feedback_race_preserves_one_revision(scenario, runtime_engine):
    record = create(scenario)
    _, _, _, admin, user_id = scenario
    contexts = []
    with admin.begin() as db:
        for _ in range(4):
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
            return discovery.operate(
                db, *context, UUID(record["id"]), expected=1, choice="later"
            ).status

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(compete, contexts))
    assert sorted(results) == [200, 409, 409, 409]
    with admin() as db:
        assert db.get(MemoryRecord, UUID(record["id"])).revision == 2
        assert (
            len(
                list(
                    db.scalars(
                        select(MemoryRevision).where(MemoryRevision.memory_id == UUID(record["id"]))
                    )
                )
            )
            == 2
        )
