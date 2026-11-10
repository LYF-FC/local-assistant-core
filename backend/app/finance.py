"""Owner-private manual records. No financial actions, calculations or context projection."""

from sqlalchemy import Text, func, select, update

from app import identity
from app.manual_tasks import authority, stamp
from app.models import FinancialRecord as Record
from app.models import FinancialRevision as Revision


def authorized(db, token, csrf, body, write=False):
    return authority(
        db,
        token,
        csrf,
        body.scope,
        exclusive_user=write,
        event_prefix="finance",
        scope_lock="finance",
    )


def document(row):
    result = {
        "id": str(row.id),
        "owner_id": str(row.owner_id),
        "scope": row.scope_key,
        "kind": row.kind,
        "state": row.state,
        "revision": row.revision,
        "created_at": stamp(row.created_at),
        "updated_at": stamp(row.updated_at),
    }
    if row.state == "active":
        result.update(
            values=row.payload,
            plan_status=("accepted" if row.accepted_by else "proposed")
            if row.kind == "plan"
            else None,
            accepted_by=str(row.accepted_by) if row.accepted_by else None,
            accepted_at=stamp(row.accepted_at),
        )
    return result


def audit(db, user, row, op):
    identity.audit(
        db,
        "finance." + op,
        "success",
        user=user,
        scope="finance_private",
        entity_type="financial_record",
        entity=str(row.id),
        metadata={"revision": row.revision, "state": row.state},
    )


def snapshot(db, user, row):
    db.add(
        Revision(
            record_id=row.id,
            revision=row.revision,
            actor_id=user.id,
            snapshot=document(row) if row.state == "active" else None,
            created_at=row.updated_at,
        )
    )


def create(db, token, csrf, body):
    current = authorized(db, token, csrf, body, True)
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    try:
        values = body.values.payload()
    except ValueError:
        return identity.denied(db, 422, "finance.invalid_values", user=user)
    if db.scalar(select(func.count()).select_from(Record).where(Record.owner_id == user.id)) >= 100:
        return identity.denied(db, 429, "finance.record_limit", user=user)
    now = identity.now_utc()
    row = Record(
        owner_id=user.id,
        scope_key=body.scope,
        kind=body.kind,
        state="active",
        revision=1,
        payload=values,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    snapshot(db, user, row)
    audit(db, user, row, "created")
    return identity.Result(201, document(row))


def operate(db, token, csrf, identifier, body, op):
    current = authorized(db, token, csrf, body, op in {"correct", "accept", "forget"})
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    row = db.scalar(
        select(Record)
        .where(Record.id == identifier, Record.owner_id == user.id, Record.scope_key == body.scope)
        .with_for_update(read=op in {"read", "history", "export"})
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "finance.session_denied", user=user)
    if row is None:
        return identity.denied(db, 404, "finance.not_found", user=user)
    if op in {"history", "export"}:
        if op == "export" and row.revision != body.expected_revision:
            return identity.denied(db, 409, "finance.changed", user=user)
        rows = list(
            db.scalars(
                select(Revision)
                .where(Revision.record_id == row.id, Revision.revision > body.after)
                .order_by(Revision.revision)
                .limit(26)
            )
        )
        audit(db, user, row, op)
        return identity.Result(
            200,
            {
                **({"record": document(row), "managed_copy": False} if op == "export" else {}),
                "schema_version": 1,
                "record_id": str(row.id),
                "current_revision": row.revision,
                "state": row.state,
                "items": [
                    {
                        "revision": r.revision,
                        "actor_id": str(r.actor_id),
                        "created_at": stamp(r.created_at),
                        "snapshot": r.snapshot,
                    }
                    for r in rows[:25]
                ],
                "next_cursor": rows[24].revision if len(rows) > 25 else None,
            },
        )
    if op == "read":
        audit(db, user, row, "read")
        return identity.Result(200, document(row))
    if op == "forget" and row.state == "forgotten":
        audit(db, user, row, "forget_replayed")
        return identity.Result(200, document(row))
    if row.revision != body.expected_revision:
        return identity.denied(db, 409, "finance.changed", user=user)
    if row.state != "active":
        return identity.denied(db, 410, "finance.forgotten", user=user)
    if op == "correct":
        try:
            values = body.values.payload()
        except ValueError:
            return identity.denied(db, 422, "finance.invalid_values", user=user)
        if values == row.payload:
            return identity.denied(db, 409, "finance.no_change", user=user)
    elif op == "accept":
        if row.kind != "plan":
            return identity.denied(db, 409, "finance.not_plan", user=user)
        if row.accepted_by:
            audit(db, user, row, "accept_replayed")
            return identity.Result(200, document(row))
    if op != "forget" and row.revision >= 100:
        return identity.denied(db, 429, "finance.history_limit", user=user)
    now = identity.now_utc()
    if op == "correct":
        row.payload = values
        row.accepted_by = None
        row.accepted_at = None
    elif op == "accept":
        row.accepted_by = user.id
        row.accepted_at = now
    elif op == "forget":
        row.state = "forgotten"
        row.payload = None
        row.accepted_by = None
        row.accepted_at = None
    row.revision += 1
    row.updated_at = now
    db.flush()
    if op == "forget":
        db.execute(update(Revision).where(Revision.record_id == row.id).values(snapshot=None))
    snapshot(db, user, row)
    audit(db, user, row, op)
    return identity.Result(200, document(row))


def listing(db, token, csrf, body, export=False):
    current = authorized(db, token, csrf, body)
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    query = select(Record).where(Record.owner_id == user.id, Record.scope_key == body.scope)
    if body.after:
        query = query.where(Record.id > body.after)
    # Search only active payload text; no foreign/tombstone content can match.
    if body.search:
        query = query.where(Record.payload.cast(Text).icontains(body.search, autoescape=True))
    rows = list(
        db.scalars(
            query.order_by(Record.id)
            .limit(26)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "finance.session_denied", user=user)
    identity.audit(
        db,
        "finance.export" if export else "finance.query",
        "success",
        user=user,
        scope=body.scope,
        entity_type="financial_record",
        metadata={"returned": min(len(rows), 25)},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "scope": body.scope,
            "owner_id": str(user.id),
            "checked_at": stamp(identity.now_utc()),
            "managed_copy": False if export else None,
            "items": [document(r) for r in rows[:25]],
            "next_cursor": str(rows[24].id) if len(rows) > 25 else None,
        },
    )
