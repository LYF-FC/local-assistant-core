"""Restricted-role JSON eligibility and row-lock fencing on real PostgreSQL."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from test_memory import content, create

from app import context_preview, identity, memory
from app.context_routes import Selection
from app.manage import set_scope
from app.models import AuthSession, User

pytestmark = pytest.mark.integration


def test_runtime_catalogue_filters_json_null_namespace_and_builds_reference(scenario):
    client, headers, _, admin, user_id = scenario
    with admin.begin() as db:
        set_scope(db, db.get(User, user_id), "member_a_private", True)
    good = create(client, headers, scope="member_a_private").json()
    for changes in [
        {"content": {"record_type": None}},
        {"content": {"record_type": "discovery_proposal"}},
        {"kind": "experience"},
        {"assessment": "tentative"},
    ]:
        assert create(client, headers, scope="member_a_private", **changes).status_code == 201
    page = client.get("/api/v1/context/candidates?scope=member_a_private").json()
    assert [row["id"] for row in page["items"]] == [good["id"]]
    assert "content" not in page["items"][0]
    result = client.post(
        "/api/v1/context/preview",
        headers=headers,
        json={
            "scope": "member_a_private",
            "selections": [{"id": good["id"], "expected_revision": 1}],
        },
    )
    assert result.status_code == 200
    assert result.json()["model_invoked"] is False
    assert result.json()["items"][0]["content"] == {"value": "synthetic-only"}


def test_preview_waits_for_distinct_session_correction_then_rejects_stale_revision(
    scenario, runtime_engine
):
    client, headers, _, admin, user_id = scenario
    record = create(client, headers).json()
    contexts = []
    with admin.begin() as db:
        for _ in range(2):
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
    changed, release, reading = Event(), Event(), Event()

    def correct():
        with maker.begin() as db:
            result = memory.operate(
                db,
                *contexts[0],
                UUID(record["id"]),
                operation="correct",
                expected=1,
                values=content(content={"text": "Synthetic locked correction"}),
            )
            assert result.status == 200
            changed.set()
            assert release.wait(5)
        return result.status

    def before_execute(connection, cursor, statement, parameters, context, executemany):
        if "FROM memory_records" in statement and "FOR SHARE" in statement:
            reading.set()

    def inspect():
        with maker.begin() as db:
            return context_preview.preview(
                db,
                *contexts[1],
                "household_shared",
                [Selection(id=UUID(record["id"]), expected_revision=1)],
            )

    event.listen(runtime_engine, "before_cursor_execute", before_execute)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(correct)
            try:
                assert changed.wait(2)
                reader = pool.submit(inspect)
                assert reading.wait(2)
                with pytest.raises(TimeoutError):
                    reader.result(timeout=0.1)
            finally:
                release.set()
            assert writer.result(timeout=3) == 200
            outcome = reader.result(timeout=3)
            assert outcome.status == 409 and "items" not in outcome.payload
    finally:
        event.remove(runtime_engine, "before_cursor_execute", before_execute)
