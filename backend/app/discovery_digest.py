"""Explicit selected local copies. Preview metadata is not approval or source verification."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text

from app import discovery, identity
from app.models import AuditEvent, AuthSession, MemoryRecord, User


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    expected_revision: int = Field(strict=True, ge=1)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["member_a_private", "member_b_private"]
    selections: list[Selection] = Field(min_length=1, max_length=10)
    purpose: Literal["preview", "download"]
    review_id: UUID | None = None
    reviewed_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    acknowledge_copy_limits: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def exact_review(self):
        if len({item.id for item in self.selections}) != len(self.selections):
            raise ValueError("Duplicate selections")
        if self.purpose == "preview":
            if (
                self.review_id is not None
                or self.reviewed_hash is not None
                or self.acknowledge_copy_limits
            ):
                raise ValueError("Preview cannot claim reviewed download authority")
        elif (
            self.review_id is None or self.reviewed_hash is None or not self.acknowledge_copy_limits
        ):
            raise ValueError("Download requires the reviewed copy acknowledgement")
        return self


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def authority(db, token, csrf, scope):
    if not token or not 40 <= len(token) <= 128:
        return identity.denied(db, 401, "discovery.digest_session_denied")
    user_id = db.scalar(
        select(AuthSession.user_id).where(AuthSession.token_hash == identity.digest(token))
    )
    if user_id is None:
        return identity.denied(db, 401, "discovery.digest_session_denied")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout='2s'"))
        db.execute(text("SET LOCAL statement_timeout='5s'"))
    # User then session, matching trusted identity administration; refresh after lock waits.
    user = db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    current = identity.resolve(db, token, refresh_session=True) if user and user.is_active else None
    if current is None or current[0].id != user_id:
        return identity.denied(db, 401, "discovery.digest_session_denied")
    session = current[1]
    if (
        not csrf
        or len(csrf) > 128
        or not hmac.compare_digest(session.csrf_hash, identity.digest(csrf))
    ):
        return identity.denied(db, 403, "discovery.digest_csrf_denied", user=user)
    if db.get_bind().dialect.name == "postgresql":
        granted = db.scalar(
            text("SELECT public.butler_lock_discovery_scope(:actor,:scope)"),
            {"actor": user.id, "scope": scope},
        )
    else:  # SQLite is only the unit-test store; PostgreSQL proves the actual row lock.
        granted = scope in identity.memberships(db, user)
    if not granted:
        return identity.denied(db, 403, "discovery.digest_scope_denied", user=user)
    return user, session


def reviewed_deadline(db, request, user, session):
    if db.get_bind().dialect.name == "postgresql":
        return db.scalar(
            text(
                "SELECT public.butler_discovery_review_deadline(:review,:actor,:session,:scope,:hash,:count)"
            ),
            {
                "review": request.review_id,
                "actor": user.id,
                "session": session.id,
                "scope": request.scope,
                "hash": request.reviewed_hash,
                "count": len(request.selections),
            },
        )
    receipt = db.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.event_type == "discovery.digest_preview",
            AuditEvent.result_status == "success",
            AuditEvent.initiator_type == "human",
            AuditEvent.initiator_id == str(user.id),
            AuditEvent.scope_key == request.scope,
            AuditEvent.entity_type == "discovery_digest",
            AuditEvent.entity_id == str(request.review_id),
            AuditEvent.occurred_at >= identity.now_utc() - timedelta(seconds=60),
        )
        .order_by(AuditEvent.occurred_at.desc())
        .limit(1)
    )
    meta = receipt.metadata_json if receipt else {}
    if (
        meta.get("schema_version") != 1
        or meta.get("session_id") != str(session.id)
        or meta.get("reviewed_hash") != request.reviewed_hash
        or meta.get("selected_count") != len(request.selections)
    ):
        return None
    return meta.get("valid_until")


def prepare(db, token, csrf, request):
    current = authority(db, token, csrf, request.scope)
    if isinstance(current, identity.Result):
        return current
    user, session = current
    scope = request.scope
    receipt_deadline = None
    if request.purpose == "download":
        raw = reviewed_deadline(db, request, user, session)
        try:
            receipt_deadline = identity.aware(datetime.fromisoformat(raw))
        except (ValueError, TypeError):
            return identity.denied(
                db, 409, "discovery.digest_review_changed", user=user, scope=scope
            )
    ids = [item.id for item in request.selections]
    rows = db.scalars(
        select(MemoryRecord)
        .where(
            MemoryRecord.id.in_(ids),
            MemoryRecord.owner_id == user.id,
            MemoryRecord.scope_key == scope,
            MemoryRecord.kind == "experience",
            MemoryRecord.state == "active",
        )
        .order_by(MemoryRecord.id)
        .with_for_update()
    ).all()
    if len(rows) != len(ids):
        return identity.denied(db, 404, "discovery.digest_unavailable", user=user, scope=scope)
    by_id = {row.id: row for row in rows}
    items = []
    for selected in request.selections:
        row = by_id[selected.id]
        envelope = discovery.parse(row)
        if envelope is None:
            return identity.denied(db, 404, "discovery.digest_unavailable", user=user, scope=scope)
        if row.revision != selected.expected_revision:
            return identity.denied(
                db, 409, "discovery.digest_revision_changed", user=user, scope=scope
            )
        items.append(discovery.document(row, envelope))
    # Actor/session deadlines and record expiries must be checked after any record-lock wait.
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "discovery.digest_session_denied", user=user)
    now = identity.now_utc()
    if any(row.expires_at is not None and identity.aware(row.expires_at) <= now for row in rows):
        return identity.denied(db, 404, "discovery.digest_unavailable", user=user, scope=scope)
    retention = min(
        (identity.aware(row.expires_at) for row in rows if row.expires_at is not None), default=None
    )
    until = min(
        now + timedelta(seconds=60),
        identity.aware(session.expires_at),
        retention or now + timedelta(seconds=60),
    )
    reviewed = hashlib.sha256(
        (
            "butler-discovery-digest-v1\0"
            + canonical({"session_id": str(session.id), "scope": scope, "items": items})
        ).encode()
    ).hexdigest()
    if receipt_deadline is not None:
        if receipt_deadline <= now or not hmac.compare_digest(reviewed, request.reviewed_hash):
            return identity.denied(
                db, 409, "discovery.digest_review_changed", user=user, scope=scope
            )
        until = min(until, receipt_deadline)
    bundle = {
        "schema_version": 1,
        "mode": "selected_discovery_digest",
        "scope": scope,
        "export_id": str(uuid4()),
        "prepared_at": now.isoformat(),
        "retain_until": retention.isoformat() if retention else None,
        "managed_copy": False,
        "source_verification": False,
        "execution_allowed": False,
        "items": items,
    }
    size = len(canonical(bundle).encode())
    if size > 65536:
        return identity.denied(db, 413, "discovery.digest_too_large", user=user, scope=scope)
    review_id = request.review_id or uuid4()
    session.last_seen_at = now
    identity.audit(
        db,
        "discovery.digest_" + request.purpose,
        "success",
        user=user,
        scope=scope,
        entity=str(review_id),
        entity_type="discovery_digest",
        metadata={
            "schema_version": 1,
            "session_id": str(session.id),
            "reviewed_hash": reviewed,
            "selected_count": len(items),
            "valid_until": until.isoformat(),
            "export_id": bundle["export_id"],
        },
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "mode": "discovery_digest_review",
            "checked_at": now.isoformat(),
            "valid_until": until.isoformat(),
            "purpose": request.purpose,
            "review_id": str(review_id),
            "reviewed_hash": reviewed,
            "bundle_bytes": size,
            "bundle": bundle,
        },
    )


def release(result):
    """A slow commit may preserve preparation evidence without releasing an expired copy."""
    if (
        result.status == 200
        and datetime.fromisoformat(result.payload["valid_until"]) <= identity.now_utc()
    ):
        return identity.Result(409, {"detail": "Discovery digest review expired"})
    return result
