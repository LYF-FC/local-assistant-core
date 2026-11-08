"""Local deterministic queue. Call each operation within one DB transaction."""

import hmac
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import approvals, identity
from app.config import settings
from app.models import Approval, AuditEvent, DurableJob, JobOutbox, User

MAX_ATTEMPTS = 3
LEASE = timedelta(seconds=60)


def audit(db, job, name, *, user=None, code=None):
    db.add(
        AuditEvent(
            environment=settings.env,
            initiator_type="human" if user else "worker",
            initiator_id=str(user.id) if user else "local-noop-worker",
            scope_key=job.scope_key,
            event_type="job." + name,
            entity_type="job",
            entity_id=str(job.id),
            approval_id=job.approval_id,
            result_status=job.status,
            metadata_json={"code": code} if code else {},
            source_context={},
        )
    )
    db.flush()


def document(job):
    return {
        "id": str(job.id),
        "approval_id": str(job.approval_id),
        "scope": job.scope_key,
        "action_type": job.action_type,
        "status": job.status,
        "result_code": job.result_code,
        "reviewed": job.reviewed_at is not None,
    }


def enqueue(db, token, csrf, approval_id, expected_hash, policy, key):
    current = approvals.actor(db, token, csrf, True)
    if isinstance(current, identity.Result):
        return current
    user, _, scopes = current
    # Serialize per-requester keys, including different approvals with one key.
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    key_hash = identity.digest(key)
    existing = db.scalar(
        select(DurableJob).where(
            DurableJob.requested_by == user.id, DurableJob.idempotency_hash == key_hash
        )
    )
    if existing:
        if existing.scope_key not in scopes:
            return identity.denied(db, 404, "job.not_found", user=user)
        if (
            existing.approval_id != approval_id
            or existing.payload_hash != expected_hash
            or policy != approvals.POLICY
        ):
            return identity.denied(db, 409, "job.idempotency_conflict", user=user)
        audit(db, existing, "replayed", user=user)
        return identity.Result(200, document(existing))
    outcome = approvals.operate(db, token, csrf, approval_id, "consume", expected_hash, policy)
    if outcome.status != 200:
        return outcome
    approval = db.get(Approval, approval_id)
    job = DurableJob(
        approval_id=approval.id,
        requested_by=user.id,
        scope_key=approval.scope_key,
        action_type=approval.action_type,
        payload_hash=approval.payload_hash,
        idempotency_hash=key_hash,
        status="queued",
    )
    db.add(job)
    db.flush()
    db.add(JobOutbox(job_id=job.id))
    audit(db, job, "enqueued", user=user)
    return identity.Result(201, document(job))


def inspect_job(db, token, csrf, identifier, review=False):
    current = approvals.actor(db, token, csrf, review)
    if isinstance(current, identity.Result):
        return current
    user, session, scopes = current
    job = db.scalar(
        select(DurableJob)
        .where(DurableJob.id == identifier, DurableJob.scope_key.in_(scopes))
        .with_for_update()
    )
    if job is None:
        return identity.denied(db, 404, "job.not_found", user=user)
    if review:
        if job.requested_by != user.id:
            return identity.denied(db, 403, "job.owner_denied", user=user)
        if job.status != "dead_letter":
            return identity.denied(db, 409, "job.review_denied", user=user)
        job.reviewed_at = identity.now_utc()
    session.last_seen_at = identity.now_utc()
    audit(db, job, "reviewed" if review else "read", user=user)
    return identity.Result(200, document(job))


@dataclass(frozen=True)
class Claim:
    delivery_id: UUID
    token: str = field(repr=False)


def terminal(db, delivery, job, code):
    delivery.state = "dead_letter"
    delivery.lease_hash = delivery.lease_until = None
    job.status, job.result_code, job.finished_at = "dead_letter", code, identity.now_utc()
    audit(db, job, "dead_letter", code=code)


def claim(db: Session) -> Claim | None:
    now = identity.now_utc()
    delivery = db.scalar(
        select(JobOutbox)
        .where(
            or_(
                (JobOutbox.state == "pending") & (JobOutbox.available_at <= now),
                (JobOutbox.state == "leased") & (JobOutbox.lease_until <= now),
            )
        )
        .order_by(JobOutbox.available_at, JobOutbox.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if delivery is None:
        return None
    job = db.get(DurableJob, delivery.job_id)
    if delivery.attempts >= MAX_ATTEMPTS:
        terminal(db, delivery, job, "attempts_exhausted")
        return None
    token = secrets.token_urlsafe(32)
    delivery.state, delivery.attempts = "leased", delivery.attempts + 1
    delivery.lease_hash, delivery.lease_until = identity.digest(token), now + LEASE
    job.status = "running"
    audit(db, job, "claimed")
    return Claim(delivery.id, token)


def authorized(db, job):
    record = db.get(Approval, job.approval_id)
    if not record or record.status != "consumed" or record.action_type != approvals.ACTION:
        return False
    if (
        record.policy_version != approvals.POLICY
        or record.payload_hash != job.payload_hash
        or record.scope_key != job.scope_key
        or record.requested_by != str(job.requested_by)
        or job.action_type != approvals.ACTION
        or record.expires_at is None
        or identity.aware(record.expires_at) <= identity.now_utc()
    ):
        return False
    try:
        if record.payload_hash != approvals.binding(record):
            return False
    except (ValueError, TypeError):
        return False
    for identifier in (job.requested_by, record.approved_by):
        user = db.get(User, identifier) if identifier else None
        if (
            user is None
            or not user.is_active
            or job.scope_key not in identity.memberships(db, user)
        ):
            return False
    return True


def finish(db: Session, lease: Claim, *, retryable_failure=False) -> bool:
    delivery = db.scalar(
        select(JobOutbox).where(JobOutbox.id == lease.delivery_id).with_for_update()
    )
    now = identity.now_utc()
    if (
        delivery is None
        or delivery.state != "leased"
        or not delivery.lease_hash
        or not hmac.compare_digest(delivery.lease_hash, identity.digest(lease.token))
        or identity.aware(delivery.lease_until) <= now
    ):
        return False
    job = db.get(DurableJob, delivery.job_id)
    if not authorized(db, job):
        terminal(db, delivery, job, "authority_invalid")
    elif retryable_failure:
        if delivery.attempts >= MAX_ATTEMPTS:
            terminal(db, delivery, job, "attempts_exhausted")
        else:
            delivery.state, job.status = "pending", "queued"
            delivery.lease_hash = delivery.lease_until = None
            delivery.available_at = now + timedelta(seconds=5 * 2**delivery.attempts)
            audit(db, job, "retry_scheduled", code="local_transient_failure")
    else:
        # Registered handler: structured local no-op only. No provider boundary.
        delivery.state, job.status, job.result_code = "done", "succeeded", "noop_completed"
        delivery.lease_hash = delivery.lease_until = None
        job.finished_at = now
        audit(db, job, "succeeded")
    return True
