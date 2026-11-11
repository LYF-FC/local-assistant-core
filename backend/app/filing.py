"""Single-claim filing of approved invoice plans into a synthetic destination, with reconciliation.

An owner's explicit request is the separate, exact action authorization that plan approval
never grants: it binds one approved plan revision of one reviewed source revision. No file,
folder, network, mailbox or real destination exists here.
"""

import hashlib
import unicodedata
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator
from sqlalchemy import null, select, update
from sqlalchemy.exc import IntegrityError

from app import documents, identity
from app import invoice_review as review
from app.config import settings
from app.manual_tasks import Scoped, authority, stamp
from app.models import AuditEvent, FilingExecution, FilingExecutionEvent
from app.models import DocumentRecord as Source
from app.models import InvoiceReview as Review
from app.notifications import BACKOFF, IN_FLIGHT_DEADLINE, MAX_ATTEMPTS, RECONCILE_INTERVAL

DESTINATION = "synthetic"
DESTINATION_POLICY = "destination-v1"
MAX_PATH = 384
__all__ = ["BACKOFF", "IN_FLIGHT_DEADLINE", "MAX_ATTEMPTS", "RECONCILE_INTERVAL"]


class Outcome(StrEnum):
    ACCEPTED = "accepted"
    COLLISION = "collision"
    TRANSIENT = "transient"
    TIMEOUT = "timeout"


class Lookup(StrEnum):
    FILED = "filed"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"


class SyntheticDestination:
    """Deterministic in-memory destination: never overwrites, idempotent on the filing key.

    This is the contract a real local/Synology adapter spike must prove: a write is keyed,
    an existing path owned by another key is refused (not replaced) and a later lookup by key
    reveals whether a timed-out write was applied.
    """

    def __init__(self, script=None, *, lookup_available=True):
        self.files = {}
        self.script = {canonical_path(p): list(steps) for p, steps in (script or {}).items()}
        self.writes = 0
        self.lookup_available = lookup_available

    def put(self, key, path, sha256, size):
        path = canonical_path(path)
        owner = self.files.get(path)
        if owner is not None:
            return Outcome.ACCEPTED if owner[0] == key else Outcome.COLLISION
        steps = self.script.get(path)
        step = steps.pop(0) if steps else "accepted"
        self.writes += 1
        if step == "timeout_applied":
            self.files[path] = (key, sha256, size)
            return Outcome.TIMEOUT
        if step == "timeout_lost":
            return Outcome.TIMEOUT
        if step == "transient":
            return Outcome.TRANSIENT
        self.files[path] = (key, sha256, size)
        return Outcome.ACCEPTED

    def lookup(self, key):
        if not self.lookup_available:
            return Lookup.UNAVAILABLE
        found = any(owner[0] == key for owner in self.files.values())
        return Lookup.FILED if found else Lookup.ABSENT


def canonical_path(path):
    """Destination policy ``destination-v1``: the one identity two paths must share to collide.

    Unicode is normalised to NFC, separators are '/', duplicate and trailing separators are
    dropped and comparison is case-insensitive (the destination is treated as case-folding, the
    safe assumption for a shared or removable volume). Absolute paths, drive or stream colons,
    backslashes, control characters and '.'/'..' segments are refused rather than rewritten.
    """
    if not isinstance(path, str):
        # One refusal type for every unusable path, so callers handle a single exception.
        raise ValueError("Invalid destination path")  # noqa: TRY004
    text = unicodedata.normalize("NFC", path)
    if (
        not text
        or len(text) > MAX_PATH
        or text.startswith("/")
        or "\\" in text
        or ":" in text
        or any(ord(char) < 32 or ord(char) == 127 for char in text)
    ):
        raise ValueError("Invalid destination path")
    parts = [part for part in text.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("Invalid destination path")
    return "/".join(parts).lower()


def destination_key(scope, path):
    """Scope-qualified identity of a canonical destination; the readable path is never stored.

    This is a uniqueness and reconciliation handle, not a security boundary: authority comes from
    the owner, scope and exact approved plan revision, all re-checked under lock at claim time.
    """
    return hashlib.sha256(f"{scope}:{canonical_path(path)}".encode()).hexdigest()


def explicit(value):
    if value is not True:
        raise ValueError("Explicit acknowledgement required")
    return value


class Request(Scoped):
    document_id: UUID
    expected_document_revision: int = Field(strict=True, ge=1)
    expected_review_revision: int = Field(strict=True, ge=1)
    acknowledge_synthetic_destination: Literal[True]
    acknowledge_exact_plan: Literal[True]
    _explicit = field_validator(
        "acknowledge_synthetic_destination", "acknowledge_exact_plan", mode="before"
    )(explicit)


class Cancel(Scoped):
    execution_id: UUID
    expected_revision: int = Field(strict=True, ge=1)


class Query(Scoped):
    state: Literal["all", "pending", "filed", "failed", "unknown", "cancelled"] = "all"
    document_id: UUID | None = None
    after: UUID | None = None


class History(Scoped):
    execution_id: UUID
    after: int = Field(default=0, strict=True, ge=0)


def document(row):
    return {
        "id": str(row.id),
        "document_id": str(row.document_id),
        "owner_id": str(row.owner_id),
        "scope": row.scope_key,
        "destination": row.destination,
        "state": row.state,
        "revision": row.revision,
        "plan_revision": row.plan_revision,
        "source_revision": row.source_revision,
        "attempts": row.attempts,
        "next_attempt_at": stamp(row.next_attempt_at),
        "resolved_at": stamp(row.resolved_at),
        "reason": row.reason,
        "created_at": stamp(row.created_at),
        "updated_at": stamp(row.updated_at),
    }


def view(row):
    """API representation: a scrubbed filing no longer links to its document or plan."""
    record = document(row)
    record["scrubbed"] = row.scrubbed_at is not None
    if record["scrubbed"]:
        record["document_id"] = record["plan_revision"] = record["source_revision"] = None
    return record


def record_event(db, row, operation, actor=None):
    db.flush()
    db.add(
        FilingExecutionEvent(
            execution_id=row.id,
            owner_id=row.owner_id,
            revision=row.revision,
            operation=operation,
            actor_id=actor.id if actor else None,
            recorded_at=row.updated_at,
            snapshot=null() if operation == "scrubbed" else document(row),
        )
    )
    after = {
        "revision": row.revision,
        "state": row.state,
        "attempts": row.attempts,
        "reason": row.reason,
    }
    if actor is not None:
        identity.audit(
            db,
            "filing." + operation,
            "success",
            user=actor,
            scope=row.scope_key,
            entity_type="filing_execution",
            entity=str(row.id),
            metadata=after,
        )
    else:
        db.add(
            AuditEvent(
                environment=settings.env,
                initiator_type="system",
                initiator_id="filing_worker",
                scope_key=row.scope_key,
                event_type="filing." + operation,
                entity_type="filing_execution",
                entity_id=str(row.id),
                result_status="success",
                before_json=None,
                after_json=after,
                metadata_json={},
                source_context={},
            )
        )
    db.flush()


def change(db, row, operation, now, actor=None, **values):
    for name, value in values.items():
        setattr(row, name, value)
    row.revision += 1
    row.updated_at = now
    record_event(db, row, operation, actor)


def resolve(state, now, reason=None):
    return {
        "state": state,
        "reason": reason,
        "next_attempt_at": None,
        "attempt_started_at": None,
        "resolved_at": now,
    }


def current_plan(source, row):
    """The approved plan for this exact source and review revision, or None."""
    if source is None or row is None or source.state != "active" or row.state != "reviewed":
        return None
    plan = (row.data or {}).get("filing_plan")
    if (
        not plan
        or plan.get("state") != "approved"
        or plan.get("approved_revision") != row.revision
        or plan.get("source_revision") != source.revision
        or plan.get("source_sha256") != source.sha256
        or row.source_revision != source.revision
        or not review.eligible(source)
    ):
        return None
    return plan


def request(db, token, csrf, body):
    current = authority(db, token, csrf, body.scope, exclusive_user=True, event_prefix="filing")
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    source = db.scalar(
        select(Source)
        .where(Source.id == body.document_id, *documents.visible(user, body.scope))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "filing.session_denied", user=user)
    if source is None:
        return identity.denied(db, 404, "filing.not_found", user=user)
    if source.owner_id != user.id:
        return identity.denied(db, 403, "filing.owner_denied", user=user)
    row = db.scalar(
        select(Review)
        .where(Review.document_id == source.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if source.revision != body.expected_document_revision:
        return identity.denied(db, 409, "filing.source_changed", user=user)
    if row is None or row.revision != body.expected_review_revision:
        return identity.denied(db, 409, "filing.review_changed", user=user)
    plan = current_plan(source, row)
    if plan is None:
        return identity.denied(db, 409, "filing.plan_not_approved", user=user)
    existing = db.scalar(
        select(FilingExecution).where(
            FilingExecution.document_id == source.id,
            FilingExecution.plan_revision == row.revision,
        )
    )
    if existing is not None:
        record = view(existing)
        identity.audit(
            db,
            "filing.replayed",
            "success",
            user=user,
            scope=body.scope,
            entity_type="filing_execution",
            entity=str(existing.id),
            metadata={"revision": existing.revision, "state": existing.state},
        )
        return identity.Result(200, {"schema_version": 1, "replayed": True, "filing": record})
    try:
        key = destination_key(body.scope, plan["relative_path"])
    except ValueError:
        return identity.denied(db, 422, "filing.invalid_destination", user=user)
    taken = db.scalar(
        select(FilingExecution.id).where(
            FilingExecution.scope_key == body.scope,
            FilingExecution.destination_key == key,
            FilingExecution.state.in_(("pending", "unknown", "filed")),
        )
    )
    if taken is not None:
        return identity.denied(db, 409, "filing.destination_taken", user=user)
    now = identity.now_utc()
    execution = FilingExecution(
        document_id=source.id,
        owner_id=user.id,
        scope_key=body.scope,
        plan_revision=row.revision,
        source_revision=source.revision,
        destination_key=key,
        destination=DESTINATION,
        revision=1,
        state="pending",
        attempts=0,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(execution)
            record_event(db, execution, "requested", user)
    except IntegrityError:
        # A concurrent request reserved the destination first; the unique index is the arbiter.
        return identity.denied(db, 409, "filing.destination_taken", user=user)
    return identity.Result(201, {"schema_version": 1, "replayed": False, "filing": view(execution)})


def cancel(db, token, csrf, body):
    current = authority(db, token, csrf, body.scope, exclusive_user=True, event_prefix="filing")
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    row = db.scalar(
        select(FilingExecution)
        .where(
            FilingExecution.id == body.execution_id,
            FilingExecution.owner_id == user.id,
            FilingExecution.scope_key == body.scope,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "filing.session_denied", user=user)
    if row is None:
        return identity.denied(db, 404, "filing.not_found", user=user)
    if row.revision != body.expected_revision:
        return identity.denied(db, 409, "filing.revision_changed", user=user)
    # Only work that has not started can be withdrawn; an in-flight or unknown attempt may
    # already have an effect and must be reconciled, not abandoned.
    if row.state != "pending" or row.attempt_started_at is not None:
        return identity.denied(db, 409, "filing.not_cancellable", user=user)
    now = identity.now_utc()
    change(db, row, "cancelled", now, user, **resolve("cancelled", now, "cancelled_by_owner"))
    return identity.Result(200, {"schema_version": 1, "filing": view(row)})


def scrub_for_document(db, document_id):
    """Forget every filing of a document: cancel unfinished work, drop identifiers, null history.

    Idempotent: a scrubbed execution is never touched again. Unfinished work is cancelled in the
    same transaction that forgets the source, so a worker can only observe it afterwards as
    terminal. An effect already applied to the synthetic destination before forgetting cannot be
    recalled from here; only the records about it are scrubbed.
    """
    now = identity.now_utc()
    rows = list(
        db.scalars(
            select(FilingExecution)
            .where(FilingExecution.document_id == document_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    for row in rows:
        if row.scrubbed_at is not None:
            continue
        if row.state in {"pending", "unknown"}:
            change(
                db,
                row,
                "cancelled",
                now,
                destination_key=None,
                **resolve("cancelled", now, "source_changed"),
            )
        change(db, row, "scrubbed", now, destination_key=None, scrubbed_at=now)
    if rows:
        db.execute(
            update(FilingExecutionEvent)
            .where(
                FilingExecutionEvent.execution_id.in_([row.id for row in rows]),
                FilingExecutionEvent.snapshot.is_not(None),
            )
            .values(snapshot=null())
        )


def listing(db, token, csrf, body):
    current = authority(db, token, csrf, body.scope, event_prefix="filing")
    if isinstance(current, identity.Result):
        return current
    user, session = current
    query = select(FilingExecution).where(
        FilingExecution.owner_id == user.id, FilingExecution.scope_key == body.scope
    )
    if body.state != "all":
        query = query.where(FilingExecution.state == body.state)
    if body.document_id:
        query = query.where(FilingExecution.document_id == body.document_id)
    if body.after:
        query = query.where(FilingExecution.id > body.after)
    rows = list(db.scalars(query.order_by(FilingExecution.id).limit(26)))
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "filing.session_denied", user=user)
    session.last_seen_at = identity.now_utc()
    identity.audit(
        db,
        "filing.query",
        "success",
        user=user,
        scope=body.scope,
        entity_type="filing_execution",
        metadata={"returned": min(len(rows), 25)},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "checked_at": stamp(identity.now_utc()),
            "owner_id": str(user.id),
            "scope": body.scope,
            "state": body.state,
            "items": [view(row) for row in rows[:25]],
            "next_cursor": str(rows[24].id) if len(rows) > 25 else None,
            "notice": "Synthetic destination only. No file, folder or network effect exists.",
        },
    )


def history(db, token, csrf, body):
    current = authority(db, token, csrf, body.scope, event_prefix="filing")
    if isinstance(current, identity.Result):
        return current
    user, session = current
    row = db.scalar(
        select(FilingExecution).where(
            FilingExecution.id == body.execution_id,
            FilingExecution.owner_id == user.id,
            FilingExecution.scope_key == body.scope,
        )
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "filing.session_denied", user=user)
    if row is None:
        return identity.denied(db, 404, "filing.not_found", user=user, scope=body.scope)
    session.last_seen_at = identity.now_utc()
    events = list(
        db.scalars(
            select(FilingExecutionEvent)
            .where(
                FilingExecutionEvent.execution_id == row.id,
                FilingExecutionEvent.revision > body.after,
            )
            .order_by(FilingExecutionEvent.revision)
            .limit(26)
        )
    )
    identity.audit(
        db,
        "filing.history",
        "success",
        user=user,
        scope=body.scope,
        entity_type="filing_execution",
        entity=str(row.id),
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "execution_id": str(row.id),
            "items": [
                {
                    "revision": e.revision,
                    "operation": e.operation,
                    "recorded_at": stamp(e.recorded_at),
                    "snapshot": e.snapshot,
                }
                for e in events[:25]
            ],
            "next_cursor": events[24].revision if len(events) > 25 else None,
        },
    )
