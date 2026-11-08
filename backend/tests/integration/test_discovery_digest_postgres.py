"""Restricted-runtime receipts and real row waits for selected Discovery copies."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app import identity
from app.manage import set_scope
from app.models import AuditEvent, AuthSession, MemoryRecord, User

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
            "title": "Synthetic 100%_digest",
            "summary": "Synthetic private review",
            "topic": "synthetic-review",
        },
    )
    assert result.status_code == 201
    return result.json()


def request(row, reviewed=None):
    body = {
        "scope": "member_a_private",
        "selections": [{"id": row["id"], "expected_revision": row["revision"]}],
        "purpose": "preview",
    }
    if reviewed:
        body.update(
            purpose="download",
            review_id=reviewed["review_id"],
            reviewed_hash=reviewed["reviewed_hash"],
            acknowledge_copy_limits=True,
        )
    return body


def test_runtime_inbox_and_exact_receipts(scenario):
    client, headers, _, admin, _ = scenario
    row = create(scenario)
    inbox = client.post(
        "/api/v1/discovery/inbox",
        headers=headers,
        json={"q": "%_", "stage": "idea", "topic": "synthetic-review"},
    )
    assert inbox.status_code == 200 and [r["id"] for r in inbox.json()["items"]] == [row["id"]]
    reviewed = client.post("/api/v1/discovery/digest", headers=headers, json=request(row)).json()
    fresh = client.post("/api/v1/discovery/digest", headers=headers, json=request(row, reviewed))
    assert (
        fresh.status_code == 200
        and fresh.json()["bundle"]["export_id"] != reviewed["bundle"]["export_id"]
    )
    with admin() as db:
        receipts = db.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == reviewed["review_id"])
        ).all()
        assert len(receipts) == 2 and all(r.metadata_json["selected_count"] == 1 for r in receipts)
        assert "Synthetic" not in str([r.metadata_json for r in receipts])


def test_runtime_changed_or_forgotten_record_does_not_release_a_subset(scenario):
    client, headers, _, _, _ = scenario
    row = create(scenario)
    reviewed = client.post("/api/v1/discovery/digest", headers=headers, json=request(row)).json()
    assert (
        client.put(
            f"/api/v1/discovery/{row['id']}/feedback",
            headers=headers,
            json={"expected_revision": 1, "choice": "later"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/discovery/digest", headers=headers, json=request(row, reviewed)
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/memory/{row['id']}/forget", headers=headers, json={"expected_revision": 2}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/discovery/digest", headers=headers, json=request(row, reviewed)
        ).status_code
        == 404
    )


def test_real_preparation_audit_failure_does_not_commit_a_receipt(scenario, monkeypatch):
    client, headers, _, admin, _ = scenario
    row = create(scenario)
    original = identity.audit

    def fail(db, event, *args, **kwargs):
        if event == "discovery.digest_preview":
            raise SQLAlchemyError("Synthetic digest audit refusal")
        return original(db, event, *args, **kwargs)

    monkeypatch.setattr(identity, "audit", fail)
    response = client.post("/api/v1/discovery/digest", headers=headers, json=request(row))
    assert response.status_code == 503 and "bundle" not in response.json()
    with admin() as db:
        assert not list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.event_type == "discovery.digest_preview",
                    AuditEvent.initiator_id == row["owner_id"],
                )
            )
        )


def wait_for_record_lock(admin):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        with admin() as db:
            waiting = db.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%memory_records%FOR UPDATE%'"
                ).execution_options(autocommit=True)
            )
        if waiting:
            return
        time.sleep(0.02)
    raise AssertionError("Synthetic digest did not reach the actual record lock wait")


def test_review_expiry_is_rechecked_after_a_real_record_lock_wait(scenario, monkeypatch):
    client, headers, _, admin, _ = scenario
    row = create(scenario)
    reviewed = client.post("/api/v1/discovery/digest", headers=headers, json=request(row)).json()
    now = identity.now_utc()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(
                select(MemoryRecord).where(MemoryRecord.id == UUID(row["id"])).with_for_update()
            )
            pending = pool.submit(
                client.post,
                "/api/v1/discovery/digest",
                headers=headers,
                json=request(row, reviewed),
            )
            wait_for_record_lock(admin)
            monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(seconds=61))
        response = pending.result(timeout=5)
    assert response.status_code == 409 and "bundle" not in response.json()
    with admin() as db:
        assert not list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.event_type == "discovery.digest_download",
                    AuditEvent.initiator_id == row["owner_id"],
                )
            )
        )


def test_session_expiry_is_rechecked_after_a_real_record_lock_wait(scenario, monkeypatch):
    client, headers, _, admin, user_id = scenario
    row = create(scenario)
    with admin() as db:
        expiry = db.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == user_id))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(
                select(MemoryRecord).where(MemoryRecord.id == UUID(row["id"])).with_for_update()
            )
            pending = pool.submit(
                client.post, "/api/v1/discovery/digest", headers=headers, json=request(row)
            )
            wait_for_record_lock(admin)
            monkeypatch.setattr(
                identity, "now_utc", lambda: identity.aware(expiry) + timedelta(seconds=1)
            )
        response = pending.result(timeout=5)
    assert response.status_code == 401 and "bundle" not in response.json()


def test_runtime_revocation_refuses_saved_review(scenario):
    client, headers, _, admin, user_id = scenario
    row = create(scenario)
    reviewed = client.post("/api/v1/discovery/digest", headers=headers, json=request(row)).json()
    with admin.begin() as db:
        set_scope(db, db.get(User, user_id), "member_a_private", False)
    assert (
        client.post(
            "/api/v1/discovery/digest", headers=headers, json=request(row, reviewed)
        ).status_code
        == 403
    )


def test_runtime_has_only_bound_sql_helpers_not_audit_read_or_scope_write(scenario, runtime_engine):
    from sqlalchemy.exc import DBAPIError

    client, headers, _, admin, user_id = scenario
    row = create(scenario)
    reviewed = client.post("/api/v1/discovery/digest", headers=headers, json=request(row)).json()
    with admin() as db:
        receipt = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == reviewed["review_id"]))
        session_id = UUID(receipt.metadata_json["session_id"])
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM pg_proc p, LATERAL aclexplode(p.proacl) acl WHERE p.proname IN ('butler_lock_discovery_scope','butler_discovery_review_deadline') AND acl.grantee=0"
                )
            )
            == 0
        )
        assert db.scalar(
            text(
                "SELECT bool_and(prosecdef AND proconfig @> ARRAY['search_path=pg_catalog']) FROM pg_proc WHERE proname IN ('butler_lock_discovery_scope','butler_discovery_review_deadline')"
            )
        )
    parameters = {
        "review": UUID(reviewed["review_id"]),
        "actor": user_id,
        "session": session_id,
        "scope": "member_a_private",
        "hash": reviewed["reviewed_hash"],
        "count": 1,
    }
    statement = text(
        "SELECT public.butler_discovery_review_deadline(:review,:actor,:session,:scope,:hash,:count)"
    )
    with runtime_engine.connect() as db:
        assert db.scalar(statement, parameters) == reviewed["valid_until"]
        for change in (
            {"actor": UUID(int=1)},
            {"session": UUID(int=1)},
            {"scope": "household_shared"},
            {"hash": "f" * 64},
            {"count": 2},
        ):
            assert db.scalar(statement, dict(parameters, **change)) is None
    for statement in (
        "SELECT metadata_json FROM public.audit_events",
        "UPDATE public.user_scopes SET created_at=created_at",
    ):
        with runtime_engine.connect() as db, pytest.raises(DBAPIError):
            db.execute(text(statement))


def test_scope_and_user_revocation_cannot_race_the_prepared_copy(scenario):
    from sqlalchemy.exc import DBAPIError

    client, headers, _, admin, user_id = scenario
    row = create(scenario)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(
                select(MemoryRecord).where(MemoryRecord.id == UUID(row["id"])).with_for_update()
            )
            pending = pool.submit(
                client.post, "/api/v1/discovery/digest", headers=headers, json=request(row)
            )
            wait_for_record_lock(admin)
            for command in (
                "DELETE FROM public.user_scopes WHERE user_id=:actor",
                "UPDATE public.users SET is_active=false WHERE id=:actor",
            ):
                with pytest.raises(DBAPIError) as error, admin.begin() as competing:
                    competing.execute(text("SET LOCAL lock_timeout='100ms'"))
                    competing.execute(text(command), {"actor": user_id})
                assert getattr(error.value.orig, "sqlstate", None) == "55P03"
        assert pending.result(timeout=5).status_code == 200
    with admin.begin() as db:
        set_scope(db, db.get(User, user_id), "member_a_private", False)
    assert (
        client.post("/api/v1/discovery/digest", headers=headers, json=request(row)).status_code
        == 403
    )
