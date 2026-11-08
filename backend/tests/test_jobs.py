from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import binding, create, decide, signin

from app import identity, jobs
from app.manage import set_active, set_scope
from app.models import Approval, AuditEvent, DurableJob, JobOutbox, User
from app.worker import run_once


def approved(client, headers):
    record = create(client, headers).json()
    assert decide(client, headers, record).status_code == 200
    return record


def enqueue(client, headers, record, key="synthetic-request-0001"):
    return client.post(
        "/api/v1/jobs",
        headers=headers,
        json={**binding(record), "approval_id": record["id"], "idempotency_key": key},
    )


@pytest.fixture
def queued(auth_client, auth_store):
    headers = signin(auth_client)
    record = approved(auth_client, headers)
    response = enqueue(auth_client, headers, record)
    assert response.status_code == 201
    return headers, record, response.json()


def test_atomic_job_delivery_and_replay(auth_client, auth_store, queued):
    headers, record, job = queued
    assert enqueue(auth_client, headers, record).json() == job
    assert enqueue(auth_client, headers, record, "synthetic-other-key").status_code == 409
    other = approved(auth_client, headers)
    assert enqueue(auth_client, headers, other).status_code == 409
    with auth_store() as db:
        assert db.scalar(select(func.count()).select_from(DurableJob)) == 1
        assert db.scalar(select(func.count()).select_from(JobOutbox)) == 1
        assert db.get(Approval, UUID(record["id"])).status == "consumed"
        assert db.get(Approval, UUID(other["id"])).status == "approved"
        assert db.scalar(select(DurableJob)).idempotency_hash != "synthetic-request-0001"


def test_noop_is_independent_of_model_and_terminal(auth_client, auth_store, queued):
    _, _, record = queued
    assert run_once(auth_store)
    assert not run_once(auth_store)
    assert auth_client.get(f"/api/v1/jobs/{record['id']}").json()["status"] == "succeeded"
    with auth_store() as db:
        assert db.scalar(select(DurableJob)).result_code == "noop_completed"
        assert db.scalar(select(JobOutbox)).attempts == 1


def test_worker_death_and_fenced_recovery(auth_store, queued, monkeypatch):
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    with auth_store.begin() as db:
        old = jobs.claim(db)
    assert "token=" not in repr(old)
    with auth_store.begin() as db:
        assert jobs.claim(db) is None
    now += timedelta(seconds=61)
    with auth_store.begin() as db:
        new = jobs.claim(db)
        assert new and new.token != old.token
    with auth_store.begin() as db:
        assert not jobs.finish(db, old)
        assert jobs.finish(db, new)
    with auth_store() as db:
        assert db.scalar(select(JobOutbox)).attempts == 2
        assert list(db.scalars(select(AuditEvent.event_type))).count("job.succeeded") == 1


def test_expired_worker_cannot_finish(auth_store, queued, monkeypatch):
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    with auth_store.begin() as db:
        lease = jobs.claim(db)
    now += timedelta(seconds=60)
    with auth_store.begin() as db:
        assert not jobs.finish(db, lease)


@pytest.mark.parametrize("crash", [False, True])
def test_bounded_retry_or_crash_exhaustion(auth_client, auth_store, queued, monkeypatch, crash):
    headers, _, record = queued
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    for attempt in range(3):
        with auth_store.begin() as db:
            lease = jobs.claim(db)
            assert lease
        if not crash:
            with auth_store.begin() as db:
                assert jobs.finish(db, lease, retryable_failure=True)
            with auth_store.begin() as db:
                assert jobs.claim(db) is None
        now += timedelta(seconds=61)
    with auth_store.begin() as db:
        assert jobs.claim(db) is None
    result = auth_client.get(f"/api/v1/jobs/{record['id']}")
    assert result.json()["status"] == "dead_letter"
    assert result.json()["result_code"] == "attempts_exhausted"
    assert (
        auth_client.post(f"/api/v1/jobs/{record['id']}/review", headers=headers).status_code == 200
    )
    assert not run_once(auth_store)


@pytest.mark.parametrize(
    "revocation", ["requester", "scope", "expiry", "policy", "payload", "handler"]
)
def test_execution_revalidates_authority(auth_store, queued, monkeypatch, revocation):
    _, record, _ = queued
    if revocation == "expiry":
        now = identity.now_utc() + timedelta(seconds=901)
        monkeypatch.setattr(identity, "now_utc", lambda: now)
    else:
        with auth_store.begin() as db:
            user = db.scalar(select(User).where(User.slug == "alice"))
            if revocation == "requester":
                set_active(db, user, False)
            elif revocation == "scope":
                set_scope(db, user, "household_shared", False)
            else:
                approval = db.get(Approval, UUID(record["id"]))
                if revocation == "policy":
                    approval.policy_version = "stale"
                elif revocation == "payload":
                    approval.request_payload = {"tampered": True}
                else:
                    db.scalar(select(DurableJob)).action_type = "unregistered.external"
    assert run_once(auth_store)
    with auth_store() as db:
        assert db.scalar(select(DurableJob)).result_code == "authority_invalid"


def test_scope_privacy_and_review_csrf(auth_client, queued):
    _, _, record = queued
    signin(auth_client, "bob")
    for identifier in (record["id"], str(uuid4())):
        response = auth_client.get(f"/api/v1/jobs/{identifier}")
        assert response.status_code == 404
    signin(auth_client)
    assert auth_client.post(f"/api/v1/jobs/{record['id']}/review").status_code == 403


@pytest.mark.parametrize("approved_state", [False, True])
def test_enqueue_requires_valid_approval_and_csrf(auth_client, approved_state):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    if approved_state:
        decide(auth_client, headers, record)
        record["payload_hash"] = "0" * 64
    assert enqueue(auth_client, headers, record).status_code == 409
    assert enqueue(auth_client, {}, record).status_code == 403


def test_enqueue_audit_failure_rolls_back_consumption(auth_client, auth_store, monkeypatch):
    headers = signin(auth_client)
    record = approved(auth_client, headers)

    def fail(*args, **kwargs):
        raise SQLAlchemyError("synthetic failure")

    monkeypatch.setattr(jobs, "audit", fail)
    assert enqueue(auth_client, headers, record).status_code == 503
    with auth_store() as db:
        assert db.get(Approval, UUID(record["id"])).status == "approved"
        assert db.scalar(select(func.count()).select_from(DurableJob)) == 0
        assert db.scalar(select(func.count()).select_from(JobOutbox)) == 0


def test_worker_audit_failure_rolls_back_completion(auth_store, queued, monkeypatch):
    with auth_store.begin() as db:
        lease = jobs.claim(db)

    def fail(*args, **kwargs):
        raise SQLAlchemyError("synthetic failure")

    monkeypatch.setattr(jobs, "audit", fail)
    with pytest.raises(SQLAlchemyError), auth_store.begin() as db:
        jobs.finish(db, lease)
    with auth_store() as db:
        assert db.scalar(select(DurableJob)).status == "running"
        assert db.scalar(select(JobOutbox)).state == "leased"


def test_review_is_requester_only_and_does_not_replay(auth_client, auth_store, queued):
    _, _, record = queued
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, bob, "household_shared", True)
    headers = signin(auth_client, "bob")
    assert (
        auth_client.post(f"/api/v1/jobs/{record['id']}/review", headers=headers).status_code == 403
    )
    headers = signin(auth_client)
    assert (
        auth_client.post(f"/api/v1/jobs/{record['id']}/review", headers=headers).status_code == 409
    )


def test_enqueue_commit_failure_rolls_back_all_records(auth_client, auth_store):
    from sqlalchemy import event

    headers = signin(auth_client)
    record = approved(auth_client, headers)

    def fail(db):
        raise SQLAlchemyError("synthetic commit failure")

    event.listen(auth_store, "before_commit", fail)
    try:
        assert enqueue(auth_client, headers, record).status_code == 503
    finally:
        event.remove(auth_store, "before_commit", fail)
    with auth_store() as db:
        assert db.get(Approval, UUID(record["id"])).status == "approved"
        assert db.scalar(select(func.count()).select_from(DurableJob)) == 0
        assert db.scalar(select(func.count()).select_from(JobOutbox)) == 0


@pytest.mark.parametrize("disable", [True, False])
def test_distinct_approver_revocation_blocks_execution(auth_client, auth_store, disable):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, bob, "household_shared", True)
    bob_headers = signin(auth_client, "bob")
    assert decide(auth_client, bob_headers, record).status_code == 200
    headers = signin(auth_client)
    assert enqueue(auth_client, headers, record).status_code == 201
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        if disable:
            set_active(db, bob, False)
        else:
            set_scope(db, bob, "household_shared", False)
    assert run_once(auth_store)
    with auth_store() as db:
        assert db.scalar(select(DurableJob)).result_code == "authority_invalid"
