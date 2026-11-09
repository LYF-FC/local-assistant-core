"""Local read snapshots and deterministic day briefing. No provider/model I/O."""

import json
from datetime import datetime, timedelta
from uuid import uuid5

from sqlalchemy import func, or_, select, update

from app import calendar_contracts as contract
from app import identity, manual_tasks
from app.models import CalendarRevision, CalendarSource, ManualTask, MemoryRecord


def visible(model, user, scope):
    return model.scope_key == scope, or_(
        model.owner_id == user.id, model.scope_key == "household_shared"
    )


def stamp(value):
    return identity.aware(value).isoformat()


def receipt(row, user, full=True):
    result = {
        "id": str(row.id),
        "owner_id": str(row.owner_id),
        "scope": row.scope_key,
        "state": row.state,
        "revision": row.revision,
        "created_at": stamp(row.created_at),
        "updated_at": stamp(row.updated_at),
        "can_edit": row.owner_id == user.id,
    }
    if full:
        result["data"] = row.data
    elif row.data:
        snap = row.data["window"]
        result.update(
            label=row.data["label"],
            status=row.data["status"],
            fetched_at=snap["fetched_at"] if snap else None,
            start_date=snap["start_date"] if snap else None,
            end_date=snap["end_date"] if snap else None,
            timezone=snap["timezone"] if snap else None,
        )
    return result


def audit(db, user, scope, name, row=None, **metadata):
    identity.audit(
        db,
        "calendar." + name,
        "success",
        user=user,
        scope=scope,
        entity_type="calendar_source",
        entity=str(row.id) if row else None,
        metadata={**metadata, **({"revision": row.revision, "state": row.state} if row else {})},
    )


def remember(db, user, row):
    db.flush()
    db.add(
        CalendarRevision(
            source_id=row.id,
            revision=row.revision,
            actor_id=user.id,
            snapshot=row.data,
            created_at=row.updated_at,
        )
    )


def create(db, token, csrf, body):
    current = manual_tasks.authority(
        db, token, csrf, body.scope, exclusive_user=True, event_prefix="calendar"
    )
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    if (
        db.scalar(
            select(func.count())
            .select_from(CalendarSource)
            .where(CalendarSource.owner_id == user.id)
        )
        >= 10
    ):
        return identity.denied(db, 429, "calendar.source_limit", user=user)
    now = identity.now_utc()
    row = CalendarSource(
        owner_id=user.id,
        scope_key=body.scope,
        state="active",
        revision=1,
        data={
            "label": body.label,
            "status": "setup_required",
            "window": None,
            "attempt_at": None,
            "changes": None,
        },
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    remember(db, user, row)
    audit(db, user, body.scope, "created", row)
    return identity.Result(201, receipt(row, user))


def changes(old, new):
    previous = {contract.key(e): e for e in old["events"]} if old else {}
    current = {contract.key(e): e for e in new["events"]}
    a = contract.midnight(datetime.fromisoformat(new["start_date"]).date(), new["timezone"])
    b = contract.midnight(datetime.fromisoformat(new["end_date"]).date(), new["timezone"])
    if old:
        a = max(
            a, contract.midnight(datetime.fromisoformat(old["start_date"]).date(), old["timezone"])
        )
        b = min(
            b, contract.midnight(datetime.fromisoformat(old["end_date"]).date(), old["timezone"])
        )
    omitted = [e for k, e in previous.items() if k not in current]
    removed = sum(
        a < b and contract.interval(e)[0] < b and contract.interval(e)[1] > a for e in omitted
    )
    return {
        "added": len(current.keys() - previous.keys()),
        "updated": sum(k in previous and previous[k] != e for k, e in current.items()),
        "removed_in_coverage": removed,
        "outside_coverage_unknown": len(omitted) - removed,
    }


def operate(db, token, csrf, identifier, body, operation):
    current = manual_tasks.authority(db, token, csrf, body.scope, event_prefix="calendar")
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    unsafe = operation in {"import", "unavailable", "forget"}
    row = db.scalar(
        select(CalendarSource)
        .where(CalendarSource.id == identifier, *visible(CalendarSource, user, body.scope))
        .with_for_update(read=not unsafe)
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "calendar.session_denied", user=user)
    if row is None:
        return identity.denied(db, 404, "calendar.not_found", user=user)
    if operation != "read" and row.owner_id != user.id:
        return identity.denied(db, 403, "calendar.owner_denied", user=user)
    if operation in {"history", "export"}:
        history = list(
            db.scalars(
                select(CalendarRevision)
                .where(CalendarRevision.source_id == row.id, CalendarRevision.revision > body.after)
                .order_by(CalendarRevision.revision)
                .limit(6)
            )
        )
        audit(db, user, body.scope, operation, row, returned=min(len(history), 5))
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "source_id": str(row.id),
                "scope": body.scope,
                "current_revision": row.revision,
                "state": row.state,
                "managed_copy": False if operation == "export" else None,
                "items": [
                    {
                        "revision": r.revision,
                        "actor_id": str(r.actor_id),
                        "created_at": stamp(r.created_at),
                        "snapshot": r.snapshot,
                    }
                    for r in history[:5]
                ],
                "next_cursor": history[4].revision if len(history) > 5 else None,
            },
        )
    if row.state == "forgotten":
        audit(db, user, body.scope, "forgotten_read", row)
        return identity.Result(410, receipt(row, user))
    window = body.window.canonical() if operation == "import" else None
    # Exact replay is allowed after a lost response, but never resets an offline state.
    if (
        window is not None
        and window == row.data["window"]
        and body.expected_revision <= row.revision
    ):
        audit(db, user, body.scope, "replayed", row)
        return identity.Result(200, receipt(row, user))
    if unsafe and row.revision != body.expected_revision:
        return identity.denied(db, 409, "calendar.revision_conflict", user=user)
    if unsafe and operation != "forget" and row.revision >= 100:
        return identity.denied(db, 429, "calendar.history_limit", user=user)
    if operation == "import":
        now = identity.now_utc()
        fetched = datetime.fromisoformat(window["fetched_at"])
        old = row.data["window"]
        if (
            fetched > now + timedelta(seconds=60)
            or (old and fetched <= datetime.fromisoformat(old["fetched_at"]))
            or (
                row.data["status"] in {"offline", "failed"}
                and fetched < datetime.fromisoformat(row.data["attempt_at"])
            )
        ):
            return identity.denied(db, 409, "calendar.fetch_conflict", user=user)
        history = list(
            db.scalars(
                select(CalendarRevision)
                .where(CalendarRevision.source_id == row.id)
                .order_by(CalendarRevision.revision)
            )
        )
        latest = {}
        for rev in history:
            snap = rev.snapshot and rev.snapshot["window"]
            if not snap:
                continue
            if snap["cursor"] == window["cursor"]:
                return identity.denied(db, 409, "calendar.cursor_conflict", user=user)
            latest.update({contract.key(e): e for e in snap["events"]})
        for item in window["events"]:
            prior = latest.get(contract.key(item))
            if prior and (
                item["sequence"] < prior["sequence"]
                or (item["sequence"] == prior["sequence"] and item != prior)
            ):
                return identity.denied(db, 409, "calendar.event_conflict", user=user)
        row.data = {
            **row.data,
            "status": "ready",
            "window": window,
            "attempt_at": stamp(now),
            "changes": changes(old, window),
        }
    elif operation == "unavailable":
        row.data = {
            **row.data,
            "status": body.reason,
            "attempt_at": stamp(identity.now_utc()),
            "changes": None,
        }
    elif operation == "forget":
        row.state, row.data = "forgotten", None
    else:
        audit(db, user, body.scope, "read", row)
        return identity.Result(200, receipt(row, user))
    row.revision += 1
    row.updated_at = identity.now_utc()
    db.flush()
    if operation == "forget":
        db.execute(
            update(CalendarRevision)
            .where(CalendarRevision.source_id == row.id)
            .values(snapshot=None)
        )
    remember(db, user, row)
    audit(db, user, body.scope, operation, row)
    return identity.Result(200, receipt(row, user))


def listing(db, token, csrf, body):
    current = manual_tasks.authority(db, token, csrf, body.scope, event_prefix="calendar")
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    query = select(CalendarSource).where(
        *visible(CalendarSource, user, body.scope), CalendarSource.state == "active"
    )
    if body.after:
        query = query.where(CalendarSource.id > body.after)
    rows = list(
        db.scalars(
            query.order_by(CalendarSource.id)
            .limit(26)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "calendar.session_denied", user=user)
    audit(db, user, body.scope, "query", returned=min(25, len(rows)))
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "scope": body.scope,
            "items": [receipt(r, user, False) for r in rows[:25]],
            "next_cursor": str(rows[24].id) if len(rows) > 25 else None,
        },
    )


def briefing(db, token, csrf, body):
    current = manual_tasks.authority(db, token, csrf, body.scope, event_prefix="briefing")
    if isinstance(current, identity.Result):
        return current
    user, session = current
    now = identity.now_utc()
    start = contract.midnight(body.day, body.timezone)
    try:
        end = contract.midnight(body.day + timedelta(days=1), body.timezone)
    except (OverflowError, ValueError):
        return identity.denied(db, 422, "briefing.invalid_day", user=user)
    if end <= start:
        return identity.denied(db, 422, "briefing.invalid_day", user=user)
    sources = list(
        db.scalars(
            select(CalendarSource)
            .where(*visible(CalendarSource, user, body.scope), CalendarSource.state == "active")
            .order_by(CalendarSource.id)
            .limit(26)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    tasks = list(
        db.scalars(
            select(ManualTask)
            .where(
                *visible(ManualTask, user, body.scope),
                ManualTask.state == "active",
                ManualTask.status == "open",
                ManualTask.due_at < end,
            )
            .order_by(ManualTask.due_at, ManualTask.id)
            .limit(26)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    memories = list(
        db.scalars(
            select(MemoryRecord)
            .where(
                *visible(MemoryRecord, user, body.scope),
                MemoryRecord.state == "active",
                MemoryRecord.assessment == "confirmed",
                or_(MemoryRecord.expires_at.is_(None), MemoryRecord.expires_at > now),
            )
            .order_by(MemoryRecord.id)
            .limit(11)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "briefing.session_denied", user=user)
    checked = identity.now_utc()
    calendars, events = [], []
    for source in sources[:25]:
        snap = source.data["window"]
        covers = bool(
            snap
            and contract.midnight(
                datetime.fromisoformat(snap["start_date"]).date(), snap["timezone"]
            )
            <= start
            and contract.midnight(datetime.fromisoformat(snap["end_date"]).date(), snap["timezone"])
            >= end
        )
        stale = not snap or checked - datetime.fromisoformat(snap["fetched_at"]) > timedelta(
            hours=24
        )
        calendars.append({**receipt(source, user, False), "covers_day": covers, "stale": stale})
        if not snap:
            continue
        for event in snap["events"]:
            a, b = contract.interval(event)
            if event["status"] == "cancelled" or a >= end or b <= start:
                continue
            identifier = str(uuid5(source.id, json.dumps(contract.key(event), ensure_ascii=False)))
            events.append(
                {
                    **event,
                    "id": identifier,
                    "source_id": str(source.id),
                    "source_revision": source.revision,
                    "source_label": source.data["label"],
                    "stale": stale,
                    "availability": source.data["status"],
                    "possible_conflict": False,
                }
            )
    events.sort(key=lambda e: (*contract.interval(e), e["id"]))
    # A sweep marks overlapping intervals without a quadratic pair scan.
    latest_event, latest_end = None, None
    for event in events:
        if event["kind"] != "timed":
            continue
        a, b = contract.interval(event)
        if latest_end is not None and a < latest_end:
            event["possible_conflict"] = latest_event["possible_conflict"] = True
        if latest_end is None or b > latest_end:
            latest_event, latest_end = event, b
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "briefing.session_denied", user=user)
    checked = identity.now_utc()
    # Exclude memory that expired while waiting for another source/task row.
    memories = [
        r for r in memories if r.expires_at is None or identity.aware(r.expires_at) > checked
    ]
    audit(
        db,
        user,
        body.scope,
        "briefing",
        sources=[{"id": str(r.id), "revision": r.revision} for r in sources[:25]],
        tasks=[{"id": str(r.id), "revision": r.revision} for r in tasks[:25]],
        memories=[{"id": str(r.id), "revision": r.revision} for r in memories[:10]],
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "scope": body.scope,
            "day": body.day.isoformat(),
            "timezone": body.timezone,
            "checked_at": stamp(checked),
            "valid_until": stamp(
                min(checked + timedelta(seconds=60), identity.aware(session.expires_at))
            ),
            "start_at": stamp(start),
            "end_at": stamp(end),
            "calendars": calendars,
            "events": events[:100],
            "tasks": [
                {**manual_tasks.presented(r, user), "overdue": identity.aware(r.due_at) < start}
                for r in tasks[:25]
            ],
            "memories": [
                {
                    "id": str(r.id),
                    "revision": r.revision,
                    "title": r.title,
                    "source_reference": r.source_reference,
                }
                for r in memories[:10]
            ],
            "truncated": {
                "calendars": len(sources) > 25,
                "events": len(events) > 100,
                "tasks": len(tasks) > 25,
                "memories": len(memories) > 10,
            },
            "notice": "One-scope snapshot. Missing coverage is unknown; stale/offline events are last-known. Overlaps are possible conflicts. Undated tasks and other scopes are not included. Memory references are unranked, not inferred needs.",
        },
    )
