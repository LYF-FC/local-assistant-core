"""Explicit, ephemeral reference preview. No prompt, model, cache or executor."""

import json
from datetime import timedelta

from sqlalchemy import func, or_, select, text

from app import approvals, identity, memory
from app.models import MemoryRecord

KINDS = frozenset({"profile", "preference", "procedure", "context"})
LIFETIME = timedelta(seconds=60)


def actor(db, token, csrf=None, unsafe=False):
    if db.get_bind().dialect.name == "postgresql":
        # Fixed local transaction limits; no caller-supplied SQL/settings.
        db.execute(text("SET LOCAL lock_timeout = '2s'"))
        db.execute(text("SET LOCAL statement_timeout = '3s'"))
    return approvals.actor(db, token, csrf, unsafe)


def eligible(record, now):
    if (
        record.state != "active"
        or record.assessment != "confirmed"
        or record.kind not in KINDS
        or not isinstance(record.content, dict)
        or "record_type" in record.content
        or not isinstance(record.title, str)
        or not 1 <= len(record.title.strip()) <= 160
        or not isinstance(record.source_reference, str)
        or not 1 <= len(record.source_reference.strip()) <= 512
        or record.source_type not in {"manual", "document", "conversation", "feedback"}
        or (record.expires_at is not None and identity.aware(record.expires_at) <= now)
        or (record.kind == "context" and record.expires_at is None)
    ):
        return False
    try:
        approvals.canonical(record.content)
    except (ValueError, TypeError):
        return False
    return True


def catalogue(db, token, scope, after=None, limit=25):
    current = actor(db, token)
    if isinstance(current, identity.Result):
        return current
    user, session, scopes = current
    if scope not in memory.ALLOWED or scope not in scopes:
        return identity.denied(db, 403, "context.scope_denied", user=user)
    now = identity.now_utc()
    # SQL excludes even JSON-null namespace markers; Python revalidates payloads.
    no_namespace = (
        ~MemoryRecord.content.op("?", is_comparison=True)("record_type")
        if db.get_bind().dialect.name == "postgresql"
        else func.json_type(MemoryRecord.content, "$.record_type").is_(None)
    )
    query = select(MemoryRecord).where(
        *memory.visible(user, scopes),
        MemoryRecord.scope_key == scope,
        MemoryRecord.state == "active",
        MemoryRecord.assessment == "confirmed",
        MemoryRecord.kind.in_(KINDS),
        or_(MemoryRecord.expires_at.is_(None), MemoryRecord.expires_at > now),
        or_(MemoryRecord.kind != "context", MemoryRecord.expires_at.is_not(None)),
        no_namespace,
    )
    if after is not None:
        query = query.where(MemoryRecord.id > after)
    rows = db.scalars(query.order_by(MemoryRecord.id).limit(limit + 1)).all()
    if any(not eligible(row, now) for row in rows):
        return identity.denied(db, 422, "context.invalid_catalogue", user=user, scope=scope)
    items = [
        {
            "id": str(row.id),
            "scope": row.scope_key,
            "kind": row.kind,
            "revision": row.revision,
            "title": row.title,
            "source_type": row.source_type,
            "source_reference": row.source_reference,
            "expires_at": identity.aware(row.expires_at).isoformat() if row.expires_at else None,
        }
        for row in rows[:limit]
    ]
    session.last_seen_at = now
    identity.audit(
        db,
        "context.catalogue",
        "success",
        user=user,
        scope=scope,
        entity_type="memory",
        metadata={"returned": len(items)},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "scope": scope,
            "items": items,
            "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
        },
    )


def preview(db, token, csrf, scope, selections, max_bytes=8192):
    current = actor(db, token, csrf, True)
    if isinstance(current, identity.Result):
        return current
    user, session, scopes = current
    if scope not in memory.ALLOWED or scope not in scopes:
        return identity.denied(db, 403, "context.scope_denied", user=user)
    identifiers = [item.id for item in selections]
    rows = db.scalars(
        select(MemoryRecord)
        .where(
            MemoryRecord.id.in_(identifiers),
            MemoryRecord.scope_key == scope,
            *memory.visible(user, scopes),
        )
        .order_by(MemoryRecord.id)
        .with_for_update(read=True)
    ).all()
    now = identity.now_utc()  # Recheck after any wait for a concurrent correction.
    db.refresh(user)
    if not user.is_active or identity.aware(session.expires_at) <= now:
        return identity.denied(db, 401, "context.session_denied", user=user)
    if scope not in identity.memberships(db, user):
        return identity.denied(db, 403, "context.scope_denied", user=user)
    if len(rows) != len(identifiers) or any(not eligible(row, now) for row in rows):
        return identity.denied(db, 404, "context.selection_unavailable", user=user, scope=scope)
    records = {row.id: row for row in rows}
    if any(records[item.id].revision != item.expected_revision for item in selections):
        return identity.denied(db, 409, "context.revision_conflict", user=user, scope=scope)
    items = [memory.document(records[item.id]) for item in selections]
    serialized = json.dumps(
        items, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    size = len(serialized.encode("utf-8"))
    if size > max_bytes:
        return identity.denied(db, 413, "context.budget_exceeded", user=user, scope=scope)
    expiry = min(
        [now + LIFETIME, identity.aware(session.expires_at)]
        + [identity.aware(row.expires_at) for row in rows if row.expires_at is not None]
    )
    session.last_seen_at = now
    identity.audit(
        db,
        "context.preview",
        "success",
        user=user,
        scope=scope,
        entity_type="memory",
        metadata={
            "records": [{"id": str(row.id), "revision": row.revision} for row in rows],
            "items_bytes": size,
        },
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "mode": "preview_only",
            "scope": scope,
            "model_invoked": False,
            "execution_allowed": False,
            "reference_only": True,
            "generated_at": now.isoformat(),
            "valid_until": expiry.isoformat(),
            "items_bytes": size,
            "max_bytes": max_bytes,
            "items": items,
        },
    )
