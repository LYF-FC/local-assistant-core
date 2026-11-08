"""Explicit local memory. No retrieval/model/source-fetch side effects."""

from sqlalchemy import or_, select, update

from app import approvals, identity
from app.models import MemoryRecord, MemoryRevision

SHARED = frozenset({"household_shared", "parents_child", "member_business"})
ALLOWED = identity.SCOPES - {"technical_admin"}


def visible(user, scopes):
    return (
        MemoryRecord.scope_key.in_(set(scopes) & ALLOWED),
        or_(MemoryRecord.owner_id == user.id, MemoryRecord.scope_key.in_(SHARED)),
    )


def metadata(record):
    return {
        "id": str(record.id),
        "owner_id": str(record.owner_id),
        "scope": record.scope_key,
        "kind": record.kind,
        "state": record.state,
        "revision": record.revision,
        "created_at": identity.aware(record.created_at).isoformat(),
        "updated_at": identity.aware(record.updated_at).isoformat(),
    }


def expired(record):
    return record.expires_at is not None and identity.aware(record.expires_at) <= identity.now_utc()


def document(record):
    base = metadata(record)
    if record.state == "forgotten":
        return base
    return dict(
        base,
        title=record.title,
        content=record.content,
        source_type=record.source_type,
        source_reference=record.source_reference,
        assessment=record.assessment,
        expires_at=identity.aware(record.expires_at).isoformat() if record.expires_at else None,
        expired=expired(record),
        eligible_for_context=not expired(record),
    )


def audit(db, user, record, name, before=None):
    identity.audit(
        db,
        "memory." + name,
        "success",
        user=user,
        scope=record.scope_key,
        entity=str(record.id),
        entity_type="memory",
        before={"revision": before} if before else None,
        after={"revision": record.revision, "state": record.state},
    )


def validate(kind, values):
    approvals.canonical(values["content"])
    expiry = values.get("expires_at")
    if expiry is not None and identity.aware(expiry) <= identity.now_utc():
        raise ValueError("Expiry must be future")
    if kind == "context" and expiry is None:
        raise ValueError("Context requires expiry")


def snapshot(db, user, record):
    data = document(record) if record.state == "active" else None
    if data is not None:
        # Historical snapshots never claim dynamic context eligibility.
        data.pop("eligible_for_context", None)
        data.pop("expired", None)
    db.add(
        MemoryRevision(
            memory_id=record.id, revision=record.revision, actor_id=user.id, snapshot=data
        )
    )


def create(db, token, csrf, scope, kind, values):
    current = approvals.actor(db, token, csrf, True)
    if isinstance(current, identity.Result):
        return current
    user, session, scopes = current
    if scope not in ALLOWED or scope not in scopes:
        return identity.denied(db, 403, "memory.scope_denied", user=user)
    try:
        validate(kind, values)
    except (ValueError, TypeError):
        return identity.denied(db, 422, "memory.invalid_content", user=user, scope=scope)
    now = identity.now_utc()
    record = MemoryRecord(
        owner_id=user.id,
        scope_key=scope,
        kind=kind,
        state="active",
        revision=1,
        created_at=now,
        updated_at=now,
        **values,
    )
    db.add(record)
    db.flush()
    snapshot(db, user, record)
    session.last_seen_at = now
    audit(db, user, record, "created")
    return identity.Result(201, document(record))


def operate(
    db,
    token,
    csrf,
    identifier,
    operation="read",
    expected=None,
    values=None,
    include_expired=False,
    after=0,
    limit=25,
):
    unsafe = operation in {"correct", "forget"}
    current = approvals.actor(db, token, csrf, unsafe)
    if isinstance(current, identity.Result):
        return current
    user, session, scopes = current
    query = select(MemoryRecord).where(MemoryRecord.id == identifier, *visible(user, scopes))
    record = db.scalar(query.with_for_update() if unsafe else query)
    if record is None:
        return identity.denied(db, 404, "memory.not_found", user=user)
    session.last_seen_at = identity.now_utc()
    if (unsafe or operation == "history") and record.owner_id != user.id:
        return identity.denied(db, 403, "memory.owner_denied", user=user, scope=record.scope_key)
    if unsafe and expected != record.revision:
        return identity.denied(
            db, 409, "memory.revision_conflict", user=user, scope=record.scope_key
        )
    if operation == "history":
        rows = db.scalars(
            select(MemoryRevision)
            .where(MemoryRevision.memory_id == record.id, MemoryRevision.revision > after)
            .order_by(MemoryRevision.revision)
            .limit(limit + 1)
        ).all()
        audit(db, user, record, "history_read")
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "items": [
                    {
                        "revision": row.revision,
                        "actor_id": str(row.actor_id),
                        "created_at": identity.aware(row.created_at).isoformat(),
                        "snapshot": row.snapshot,
                        "historical": row.revision != record.revision,
                        "eligible_for_context": False,
                    }
                    for row in rows[:limit]
                ],
                "next_cursor": rows[limit - 1].revision if len(rows) > limit else None,
            },
        )
    if record.state == "forgotten":
        audit(db, user, record, "forgotten_read")
        return identity.Result(200 if operation == "forget" else 410, metadata(record))
    if operation == "correct":
        try:
            validate(record.kind, values)
        except (ValueError, TypeError):
            return identity.denied(
                db, 422, "memory.invalid_content", user=user, scope=record.scope_key
            )
        before = record.revision
        for name, value in values.items():
            setattr(record, name, value)
        record.revision += 1
        record.updated_at = identity.now_utc()
        snapshot(db, user, record)
        audit(db, user, record, "corrected", before)
    elif operation == "forget":
        before = record.revision
        record.state, record.revision, record.updated_at = (
            "forgotten",
            record.revision + 1,
            identity.now_utc(),
        )
        for name in (
            "title",
            "content",
            "source_type",
            "source_reference",
            "assessment",
            "expires_at",
        ):
            setattr(record, name, None)
        db.flush()  # PostgreSQL permits history scrubbing only after parent tombstone.
        db.execute(
            update(MemoryRevision)
            .where(MemoryRevision.memory_id == record.id)
            .values(snapshot=None)
        )
        snapshot(db, user, record)
        audit(db, user, record, "forgotten", before)
    else:
        audit(db, user, record, "read")
        if expired(record) and not (include_expired and record.owner_id == user.id):
            return identity.Result(410, dict(metadata(record), expired=True))
    return identity.Result(200, document(record))


def listing(
    db,
    token,
    *,
    after=None,
    limit=25,
    scope=None,
    kind=None,
    include_expired=False,
    include_forgotten=False,
    export=False,
):
    current = approvals.actor(db, token, None, False)
    if isinstance(current, identity.Result):
        return current
    user, session, scopes = current
    now = identity.now_utc()
    active = (MemoryRecord.state == "active") & or_(
        MemoryRecord.expires_at.is_(None),
        MemoryRecord.expires_at > now,
        (MemoryRecord.owner_id == user.id) & include_expired,
    )
    condition = or_(
        active,
        (MemoryRecord.state == "forgotten")
        & (MemoryRecord.owner_id == user.id)
        & include_forgotten,
    )
    query = select(MemoryRecord).where(*visible(user, scopes), condition)
    if after is not None:
        query = query.where(MemoryRecord.id > after)
    if scope is not None:
        query = query.where(MemoryRecord.scope_key == scope)
    if kind is not None:
        query = query.where(MemoryRecord.kind == kind)
    records = db.scalars(query.order_by(MemoryRecord.id).limit(limit + 1)).all()
    session.last_seen_at = now
    identity.audit(
        db,
        "memory.export" if export else "memory.list",
        "success",
        user=user,
        entity_type="memory",
        metadata={"returned": min(len(records), limit)},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "generated_at": now.isoformat(),
            "items": [document(record) for record in records[:limit]],
            "next_cursor": str(records[limit - 1].id) if len(records) > limit else None,
        },
    )
