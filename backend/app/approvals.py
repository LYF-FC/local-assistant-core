"""Bounded approval records. No external executor or tool side effects."""

import hmac
import json
from datetime import UTC, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import identity, manual_tasks
from app.models import Approval, User

POLICY = "v0.1-record-only-1"
ACTION = "validation.noop"


def canonical(value) -> str:
    def bounded(item, depth=0):
        if depth > 8:
            raise ValueError("Payload nesting exceeds limit")
        if isinstance(item, dict):
            if len(item) > 256 or any(not isinstance(key, str) for key in item):
                raise ValueError("Invalid object")
            return {key: bounded(child, depth + 1) for key, child in item.items()}
        elif isinstance(item, list):
            if len(item) > 256:
                raise ValueError("List exceeds limit")
            return [bounded(child, depth + 1) for child in item]
        return 0 if isinstance(item, float) and item == 0 else item

    normalized = bounded(value)
    result = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    if len(result.encode()) > 16384:
        raise ValueError("Payload exceeds limit")
    return result


def binding(record: Approval) -> str:
    return identity.digest(
        canonical(
            {
                "action": record.action_type,
                "scope": record.scope_key,
                "requester": record.requested_by,
                "payload": record.request_payload,
                "policy": record.policy_version,
                "expires_at": identity.aware(record.expires_at)
                .astimezone(UTC)
                .isoformat(timespec="microseconds"),
            }
        )
    )


def event(db: Session, record: Approval, user: User, name: str, result="success", before=None):
    identity.audit(
        db,
        "approval." + name,
        result,
        user=user,
        scope=record.scope_key,
        entity_type="approval",
        entity=str(record.id),
        approval_id=record.id,
        before={"status": before} if before else None,
        after={"status": record.status},
        metadata={"payload_hash": record.payload_hash, "policy_version": record.policy_version},
    )


def actor(db: Session, token: str | None, csrf: str | None, unsafe: bool):
    identity_record = identity.resolve(db, token)
    if identity_record is None:
        return identity.denied(db, 401, "approval.session_denied")
    user, session = identity_record
    if unsafe and (
        not csrf
        or len(csrf) > 128
        or not hmac.compare_digest(session.csrf_hash, identity.digest(csrf))
    ):
        return identity.denied(db, 403, "approval.csrf_denied", user=user)
    return user, session, identity.memberships(db, user)


def document(record: Approval) -> dict:
    return {
        "id": str(record.id),
        "scope": record.scope_key,
        "action_type": record.action_type,
        "payload": record.request_payload,
        "payload_hash": record.payload_hash,
        "policy_version": record.policy_version,
        "status": record.status,
        "requested_by": record.requested_by,
        "approved_by": str(record.approved_by) if record.approved_by else None,
        "expires_at": identity.aware(record.expires_at).isoformat() if record.expires_at else None,
    }


def create(
    db: Session, token, csrf, scope: str, payload: dict, lifetime: int, action: str
) -> identity.Result:
    current = actor(db, token, csrf, True)
    if isinstance(current, identity.Result):
        return current
    user, session, scopes = current
    if scope not in identity.SCOPES or scope not in scopes:
        return identity.denied(db, 403, "approval.scope_denied", user=user)
    try:
        canonical(payload)
        if action != ACTION or not 60 <= lifetime <= 3600:
            raise ValueError("Unsupported action or lifetime")
        now = identity.now_utc()
        record = Approval(
            scope_key=scope,
            action_type=action,
            requested_by=str(user.id),
            request_payload=payload,
            policy_version=POLICY,
            requested_at=now,
            expires_at=now + timedelta(seconds=lifetime),
            status="pending",
        )
        record.payload_hash = binding(record)
    except (ValueError, TypeError):
        return identity.denied(db, 422, "approval.invalid_payload", user=user, scope=scope)
    db.add(record)
    db.flush()
    session.last_seen_at = now
    event(db, record, user, "created")
    return identity.Result(201, document(record))


def operate(
    db: Session, token, csrf, identifier: UUID, operation="read", expected_hash=None, policy=None
) -> identity.Result:
    current = actor(db, token, csrf, operation != "read")
    if isinstance(current, identity.Result):
        return current
    user, session, scopes = current
    # Do not fetch private records then decide whether to return them.
    record = db.scalar(
        select(Approval)
        .where(Approval.id == identifier, Approval.scope_key.in_(scopes))
        .with_for_update()
    )
    if record is None:
        return identity.denied(db, 404, "approval.not_found", user=user)
    session.last_seen_at = identity.now_utc()
    bound = bool(record.payload_hash and record.policy_version and record.expires_at)
    if (
        bound
        and record.status in {"pending", "approved"}
        and identity.aware(record.expires_at) <= identity.now_utc()
    ):
        before = record.status
        record.status = "expired"
        if record.resolved_at is None:
            record.resolved_at = identity.now_utc()
        event(db, record, user, "expired", before=before)
    if operation == "read":
        event(db, record, user, "read")
        return identity.Result(200, document(record))
    try:
        intact = bound and record.payload_hash == binding(record)
    except (ValueError, TypeError):
        intact = False
    if (
        not intact
        or record.policy_version != POLICY
        or expected_hash != record.payload_hash
        or policy != POLICY
    ):
        event(db, record, user, "binding_denied", result="denied")
        return identity.Result(409, {"detail": "Approval is stale or does not match"})
    if operation in {"cancel", "consume"} and record.requested_by != str(user.id):
        event(db, record, user, "owner_denied", result="denied")
        return identity.Result(403, {"detail": "Access denied"})
    allowed = (
        {"approve", "reject", "cancel"}
        if record.status == "pending"
        else {"consume", "cancel"}
        if record.status == "approved"
        else set()
    )
    if operation not in allowed:
        event(db, record, user, "transition_denied", result="denied")
        return identity.Result(409, {"detail": "Approval transition is not allowed"})
    if operation == "consume":
        approver = db.get(User, record.approved_by) if record.approved_by else None
        if (
            record.action_type != ACTION
            or approver is None
            or not approver.is_active
            or record.scope_key not in identity.memberships(db, approver)
        ):
            event(db, record, user, "authority_denied", result="denied")
            return identity.Result(409, {"detail": "Approval authority is no longer valid"})
    before = record.status
    record.status = {
        "approve": "approved",
        "reject": "rejected",
        "cancel": "cancelled",
        "consume": "consumed",
    }[operation]
    if operation == "approve":
        record.approved_by = user.id
    if record.resolved_at is None:
        record.resolved_at = identity.now_utc()
    if operation == "consume":
        record.consumed_at = identity.now_utc()
    event(db, record, user, record.status, before=before)
    return identity.Result(200, document(record))


PAGE = 25


def listing(db: Session, token, csrf, scope: str, after: UUID | None = None) -> identity.Result:
    """Read-only page of pending, unexpired, bound approvals for one granted scope.

    Writes no approval row and applies no lazy expiry; it records exactly one metadata-only
    audit event. The payload, hash, policy version and every other person's identifier are
    deliberately not selected into the response.
    """
    current = manual_tasks.authority(db, token, csrf, scope, event_prefix="approval")
    if isinstance(current, identity.Result):
        return current
    user, session = current
    now = identity.now_utc()
    query = select(Approval).where(
        Approval.scope_key == scope,
        Approval.status == "pending",
        Approval.expires_at.is_not(None),
        Approval.expires_at > now,
        Approval.payload_hash.is_not(None),
        Approval.policy_version.is_not(None),
    )
    if after is not None:
        query = query.where(Approval.id > after)
    rows = list(
        db.scalars(
            query.order_by(Approval.id)
            .limit(PAGE + 1)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "approval.session_denied", user=user)
    session.last_seen_at = identity.now_utc()
    # One event per request, committed before release; a failure here withholds the page.
    identity.audit(
        db,
        "approval.query",
        "success",
        user=user,
        scope=scope,
        entity_type="approval",
        metadata={"returned": min(len(rows), PAGE)},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "mode": "approval_page",
            "checked_at": now.isoformat(),
            "page_limit": PAGE,
            "items": [
                {
                    "id": str(row.id),
                    "scope": row.scope_key,
                    "action_type": row.action_type,
                    "status": row.status,
                    "requested_at": identity.aware(row.requested_at).isoformat(),
                    "expires_at": identity.aware(row.expires_at).isoformat(),
                    "requested_by_you": row.requested_by == str(user.id),
                }
                for row in rows[:PAGE]
            ],
            "next_cursor": str(rows[PAGE - 1].id) if len(rows) > PAGE else None,
        },
    )
