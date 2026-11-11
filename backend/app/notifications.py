"""Synthetic-channel notification delivery. No provider, device push, email or task text."""

import hashlib
from datetime import timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import select

from app import identity
from app import manual_tasks as tasks
from app.config import settings
from app.models import AuditEvent, NotificationDelivery, NotificationDeliveryEvent

MAX_ATTEMPTS = 3
BACKOFF = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15))
IN_FLIGHT_DEADLINE = timedelta(minutes=5)
RECONCILE_INTERVAL = timedelta(minutes=1)
CHANNEL = "synthetic"


class Outcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    TRANSIENT = "transient"
    TIMEOUT = "timeout"


class Lookup(StrEnum):
    DELIVERED = "delivered"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"


class SyntheticChannel:
    """Deterministic in-memory test double for the future provider adapter contract.

    It is idempotent on the delivery key, can script transient/permanent/ambiguous outcomes and
    can answer a later lookup, which is the only contract a real connector spike must prove.
    """

    def __init__(self, script=None, *, lookup_available=True):
        self.ledger = set()
        self.script = {key: list(values) for key, values in (script or {}).items()}
        self.sent = 0
        self.lookup_available = lookup_available

    def send(self, key, recipient):
        if key in self.ledger:
            return Outcome.ACCEPTED
        steps = self.script.get(recipient)
        step = steps.pop(0) if steps else "accepted"
        self.sent += 1
        if step == "timeout_applied":
            self.ledger.add(key)
            return Outcome.TIMEOUT
        if step == "timeout_lost":
            return Outcome.TIMEOUT
        if step == "transient":
            return Outcome.TRANSIENT
        if step == "rejected":
            return Outcome.REJECTED
        self.ledger.add(key)
        return Outcome.ACCEPTED

    def lookup(self, key):
        if not self.lookup_available:
            return Lookup.UNAVAILABLE
        return Lookup.DELIVERED if key in self.ledger else Lookup.ABSENT


def recipient_ref(owner_id):
    """Opaque synthetic recipient alias; no address, device or contact detail is stored."""
    return "synthetic:" + hashlib.sha256(b"butler-notification:" + owner_id.bytes).hexdigest()[:24]


class Query(tasks.Scoped):
    state: Literal["all", "pending", "delivered", "failed", "unknown", "cancelled"] = "all"
    after: UUID | None = None


class History(tasks.Scoped):
    delivery_id: UUID
    after: int = Field(default=0, strict=True, ge=0)


def document(row):
    return {
        "id": str(row.id),
        "reminder_id": str(row.reminder_id),
        "owner_id": str(row.owner_id),
        "scope": row.scope_key,
        "channel": row.channel,
        "state": row.state,
        "revision": row.revision,
        "cycle": row.cycle,
        "attempts": row.attempts,
        "next_attempt_at": tasks.stamp(row.next_attempt_at),
        "resolved_at": tasks.stamp(row.resolved_at),
        "reason": row.reason,
        "created_at": tasks.stamp(row.created_at),
        "updated_at": tasks.stamp(row.updated_at),
    }


def record_event(db, row, operation):
    db.flush()
    db.add(
        NotificationDeliveryEvent(
            delivery_id=row.id,
            owner_id=row.owner_id,
            revision=row.revision,
            operation=operation,
            recorded_at=row.updated_at,
            snapshot=document(row),
        )
    )
    db.add(
        AuditEvent(
            environment=settings.env,
            initiator_type="system",
            initiator_id="notification_worker",
            scope_key=row.scope_key,
            event_type="notifications." + operation,
            entity_type="notification_delivery",
            entity_id=str(row.id),
            result_status="success",
            before_json=None,
            after_json={
                "revision": row.revision,
                "state": row.state,
                "attempts": row.attempts,
                "reason": row.reason,
            },
            metadata_json={},
            source_context={},
        )
    )
    db.flush()


def enqueue(db, reminder, now):
    row = NotificationDelivery(
        reminder_id=reminder.id,
        owner_id=reminder.owner_id,
        scope_key=reminder.scope_key,
        cycle=reminder.cycle,
        channel=CHANNEL,
        recipient_ref=recipient_ref(reminder.owner_id),
        revision=1,
        state="pending",
        attempts=0,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    record_event(db, row, "enqueued")
    return row


def change(db, row, operation, now, **values):
    for name, value in values.items():
        setattr(row, name, value)
    row.revision += 1
    row.updated_at = now
    record_event(db, row, operation)


def resolve(row, state, now, reason=None):
    """Terminal field set shared by delivered, failed and cancelled."""
    return {
        "state": state,
        "reason": reason,
        "next_attempt_at": None,
        "attempt_started_at": None,
        "resolved_at": now,
    }


def listing(db, token, csrf, body):
    current = tasks.authority(db, token, csrf, body.scope)
    if isinstance(current, identity.Result):
        return current
    user, session = current
    query = select(NotificationDelivery).where(
        NotificationDelivery.owner_id == user.id, NotificationDelivery.scope_key == body.scope
    )
    if body.state != "all":
        query = query.where(NotificationDelivery.state == body.state)
    if body.after:
        query = query.where(NotificationDelivery.id > body.after)
    rows = list(db.scalars(query.order_by(NotificationDelivery.id).limit(26)))
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "notifications.session_denied", user=user)
    session.last_seen_at = identity.now_utc()
    identity.audit(
        db,
        "notifications.query",
        "success",
        user=user,
        scope=body.scope,
        entity_type="notification_delivery",
        metadata={"returned": min(len(rows), 25)},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "checked_at": tasks.stamp(identity.now_utc()),
            "owner_id": str(user.id),
            "scope": body.scope,
            "state": body.state,
            "items": [document(row) for row in rows[:25]],
            "next_cursor": str(rows[24].id) if len(rows) > 25 else None,
        },
    )


def history(db, token, csrf, body):
    current = tasks.authority(db, token, csrf, body.scope)
    if isinstance(current, identity.Result):
        return current
    user, session = current
    row = db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.id == body.delivery_id,
            NotificationDelivery.owner_id == user.id,
            NotificationDelivery.scope_key == body.scope,
        )
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "notifications.session_denied", user=user)
    if row is None:
        return identity.denied(db, 404, "notifications.not_found", user=user, scope=body.scope)
    session.last_seen_at = identity.now_utc()
    events = list(
        db.scalars(
            select(NotificationDeliveryEvent)
            .where(
                NotificationDeliveryEvent.delivery_id == row.id,
                NotificationDeliveryEvent.revision > body.after,
            )
            .order_by(NotificationDeliveryEvent.revision)
            .limit(26)
        )
    )
    identity.audit(
        db,
        "notifications.history",
        "success",
        user=user,
        scope=body.scope,
        entity_type="notification_delivery",
        entity=str(row.id),
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "delivery_id": str(row.id),
            "items": [
                {
                    "revision": e.revision,
                    "operation": e.operation,
                    "recorded_at": tasks.stamp(e.recorded_at),
                    "snapshot": e.snapshot,
                }
                for e in events[:25]
            ],
            "next_cursor": events[24].revision if len(events) > 25 else None,
        },
    )
