"""Distinct-connection queue delivery and crash recovery with the restricted role."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app import identity, jobs
from app.models import AuthSession, DurableJob, JobOutbox

pytestmark = pytest.mark.integration


def prepare(scenario):
    client, headers, record, _, _ = scenario
    binding = {"payload_hash": record["payload_hash"], "policy_version": record["policy_version"]}
    assert (
        client.post(
            f"/api/v1/approvals/{record['id']}/decide",
            headers=headers,
            json=dict(binding, decision="approve"),
        ).status_code
        == 200
    )
    return binding


def test_duplicate_enqueue_distinct_sessions_and_workers(scenario, runtime_engine):
    _client, _, record, admin, user_id = scenario
    prepare(scenario)
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
    key = "synthetic-key-" + record["id"]

    def enqueue(context):
        with maker.begin() as db:
            result = jobs.enqueue(
                db,
                *context,
                UUID(record["id"]),
                record["payload_hash"],
                record["policy_version"],
                key,
            )
            return result.status, result.payload

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(enqueue, contexts))
    assert sorted(status for status, _ in outcomes) == [200] * 7 + [201]
    identifiers = {payload["id"] for _, payload in outcomes}
    assert len(identifiers) == 1
    job_id = UUID(identifiers.pop())

    def claim(_):
        with maker.begin() as db:
            return jobs.claim(db)

    with ThreadPoolExecutor(max_workers=8) as pool:
        leases = [lease for lease in pool.map(claim, range(8)) if lease]
    assert len(leases) == 1
    with maker.begin() as db:
        assert jobs.finish(db, leases[0])
    with maker.begin() as db:
        assert not jobs.finish(db, leases[0])
    with admin() as db:
        assert db.get(DurableJob, job_id).status == "succeeded"
        assert (
            db.scalar(select(func.count()).select_from(JobOutbox).where(JobOutbox.job_id == job_id))
            == 1
        )


def test_crash_recovery_fences_old_process(scenario, runtime_engine, monkeypatch):
    client, headers, record, admin, _ = scenario
    binding = prepare(scenario)
    result = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={**binding, "approval_id": record["id"], "idempotency_key": "synthetic-crash-key"},
    ).json()
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    with maker.begin() as db:
        abandoned = jobs.claim(db)
    now += timedelta(seconds=61)
    with maker.begin() as db:
        recovered = jobs.claim(db)
    assert abandoned and recovered
    with maker.begin() as db:
        assert not jobs.finish(db, abandoned)
        assert jobs.finish(db, recovered)
    with admin() as db:
        assert db.get(DurableJob, UUID(result["id"])).status == "succeeded"


def test_runtime_queue_grants_and_sealed_context(scenario, runtime_engine):
    client, headers, record, _, _ = scenario
    binding = prepare(scenario)
    response = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={**binding, "approval_id": record["id"], "idempotency_key": "synthetic-grant-key"},
    )
    assert response.status_code == 201
    for statement in (
        "DELETE FROM durable_jobs",
        "DELETE FROM job_outbox",
        "TRUNCATE job_outbox",
        "UPDATE durable_jobs SET action_type='untrusted'",
        "UPDATE job_outbox SET attempts=4",
        "UPDATE job_outbox SET state='leased', lease_hash=NULL",
    ):
        with pytest.raises(DBAPIError), runtime_engine.begin() as db:
            db.execute(text(statement))
