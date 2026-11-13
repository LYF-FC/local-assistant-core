"""Local read snapshots and deterministic day briefing. No provider/model I/O."""

import itertools
import json
from datetime import datetime, timedelta
from uuid import uuid5

from sqlalchemy import func, or_, select, update

from app import calendar_codes as codes
from app import calendar_contracts as contract
from app import calendar_recurrence as rec
from app import calendar_sync, calendar_view, identity, manual_tasks
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
        provider = (
            {"provider": calendar_sync.export_view(db, row.id)}
            if operation == "export"
            and row.state != "forgotten"
            and calendar_sync.linked(db, row.id)
            else {}
        )
        return identity.Result(
            200,
            {
                **provider,
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
    if operation in {"import", "unavailable"} and calendar_sync.linked(db, row.id):
        # A provider-mode source is fed only by the sync worker (6.6); refused before the trigger.
        return identity.denied(db, 409, "calendar.provider_mode", user=user)
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
        if calendar_sync.linked(db, row.id):
            # Same transaction, after the source reads forgotten (6.9); the deferred trigger of
            # 6.6 refuses the commit if any scrub step is missing.
            calendar_sync.scrub(db, row.id, row.updated_at)
    remember(db, user, row)
    audit(db, user, body.scope, operation, row)
    return identity.Result(200, receipt(row, user))


def listing(db, token, csrf, body):
    current = manual_tasks.authority(db, token, csrf, body.scope, event_prefix="calendar")
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    if body.days is not None and not 1 <= body.days <= codes.QUERY_HORIZON_DAYS:
        return identity.denied(db, 422, "calendar.horizon_exceeded", user=user)
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
    states = calendar_view.sync_states(db, [r.id for r in rows[:25]])
    items = []
    for row in rows[:25]:
        item = receipt(row, user, False)
        provider = states.get(row.id)
        if provider is not None:
            item["mode"] = "provider"
            item["sync"] = {
                "status": provider.status,
                "last_success_at": calendar_sync.stamp(provider.last_success_at),
                "blocked_reason": provider.blocked_reason,
                "last_error_code": provider.last_error_code,
            }
            if body.days is not None:
                window = rec.window_for_days(body.day, body.days, body.timezone)
                events, info = calendar_view.expand_source(db, row, window, body.timezone)
                events.sort(
                    key=lambda e: (
                        e["start"] if e["kind"] == "timed" else e["start_date"],
                        e["uid"],
                    )
                )
                item["occurrences"] = events[:366]
                item["cancelled_count"] = info["cancelled_count"]
                item["truncated"] = len(events) > 366 or bool(info["truncated_series"])
                item["truncated_series"] = info["truncated_series"]
                item["unreadable"] = info["unreadable"]
        items.append(item)
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "scope": body.scope,
            "items": items,
            "next_cursor": str(rows[24].id) if len(rows) > 25 else None,
        },
    )


def briefing(db, token, csrf, body):
    current = manual_tasks.authority(db, token, csrf, body.scope, event_prefix="briefing")
    if isinstance(current, identity.Result):
        return current
    user, session = current
    now = identity.now_utc()
    horizon = body.horizon_days
    if horizon is not None and not 1 <= horizon <= codes.BRIEFING_HORIZON_DAYS:
        return identity.denied(db, 422, "briefing.horizon_exceeded", user=user)
    count = horizon or 1
    try:
        bounds = [
            contract.midnight(body.day + timedelta(days=i), body.timezone) for i in range(count + 1)
        ]
    except (OverflowError, ValueError):
        return identity.denied(db, 422, "briefing.invalid_day", user=user)
    if any(b <= a for a, b in itertools.pairwise(bounds)):
        return identity.denied(db, 422, "briefing.invalid_day", user=user)
    start, end = bounds[0], bounds[-1]
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
    checked = identity.now_utc()
    states = calendar_view.sync_states(db, [s.id for s in sources[:25]])
    calendars, events = [], []
    unreadable_total = 0
    truncated_series = 0
    omitted_series = 0
    cancelled_total = 0
    for source in sources[:25]:
        provider = states.get(source.id)
        snap = source.data["window"]
        unreadable = 0
        found = []
        if provider is not None:
            window = rec.window_for_days(body.day, count, body.timezone)
            found, info = calendar_view.expand_source(db, source, window, body.timezone)
            unreadable += info["unreadable"]
            truncated_series += len(info["truncated_series"])
            omitted_series += info["omitted_at_least"]
            cancelled_total += info["cancelled_count"]
            covers = True
            as_of = provider.last_success_at
            stale = as_of is None or checked - identity.aware(as_of) > calendar_view.STALE_AFTER
            label = source.data["label"]
            availability = source.data["status"]  # the v1 field; ``state`` carries the evidence
        else:
            try:
                covers = bool(
                    snap
                    and contract.midnight(
                        datetime.fromisoformat(snap["start_date"]).date(), snap["timezone"]
                    )
                    <= start
                    and contract.midnight(
                        datetime.fromisoformat(snap["end_date"]).date(), snap["timezone"]
                    )
                    >= end
                )
            except (ValueError, KeyError, TypeError, OverflowError):
                covers = False
                unreadable += 1
            as_of = datetime.fromisoformat(snap["fetched_at"]) if snap else None
            stale = not snap or checked - as_of > timedelta(hours=24)
            label = source.data["label"]
            availability = source.data["status"]
            found = list(snap["events"]) if snap else []
        placed_events = []
        for event in found:
            if provider is None and not isinstance(event, dict):
                unreadable += 1
                continue
            try:
                if event["status"] == "cancelled":
                    continue
                days = [
                    (body.day + timedelta(days=i)).isoformat()
                    for i in range(count)
                    if contract.placed_on_day(
                        event, body.day + timedelta(days=i), bounds[i], bounds[i + 1]
                    )
                ]
                if not days:
                    continue
                key = contract.key(event)
                contract.agenda_key({**event, "id": ""})
            except (ValueError, KeyError, TypeError, OverflowError):
                unreadable += 1  # kept visible as a count, never dropped silently
                continue
            identifier = str(uuid5(source.id, json.dumps(key, ensure_ascii=False)))
            placed_events.append(
                {
                    **event,
                    "id": identifier,
                    "source_id": str(source.id),
                    "source_revision": source.revision,
                    "source_label": label,
                    "stale": stale,
                    "availability": availability,
                    "possible_conflict": False,
                    **({"days": days, "continues": len(days) > 1} if horizon else {}),
                }
            )
        if provider is not None:
            state = calendar_view.provider_state(provider, checked, unreadable=unreadable)
        else:
            state = calendar_view.manual_state(
                snap, source.data["status"], covers, checked, unreadable=unreadable
            )
        unreadable_total += unreadable
        if horizon:
            for placed in placed_events:
                placed.update(source_state=state, as_of=stamp(as_of) if as_of else None)
        events.extend(placed_events)
        entry = {**receipt(source, user, False), "covers_day": covers, "stale": stale}
        if horizon:
            entry.update(
                mode="provider" if provider is not None else "manual",
                source_state=state,
                as_of=stamp(as_of) if as_of else None,
                unreadable=unreadable,
            )
            if provider is not None:
                entry.update(
                    blocked_reason=provider.blocked_reason,
                    blocked_detail=provider.blocked_detail,
                )
        calendars.append(entry)
    events.sort(key=contract.agenda_key)
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
    if horizon:
        calendar_view.duplicate_notes(events)
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
    over_events = max(0, len(events) - 100) + omitted_series
    limits = {
        "sources": _limit(min(len(sources), 25), len(sources) - 25),
        "events": _limit(min(len(events), 100), over_events, truncated_series > 0),
        "tasks": _limit(min(len(tasks), 25), len(tasks) - 25),
        "memories": _limit(min(len(memories), 10), len(memories) - 10),
        "unreadable_items": unreadable_total,
    }
    body_out = {
        "schema_version": 2 if horizon else 1,
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
            "calendars": limits["sources"]["truncated"],
            "events": limits["events"]["truncated"],
            "tasks": limits["tasks"]["truncated"],
            "memories": limits["memories"]["truncated"],
        },
        "notice": "One-scope snapshot. Missing coverage is unknown; stale/offline events are last-known. Overlaps are possible conflicts. Undated tasks and other scopes are not included. Memory references are unranked, not inferred needs.",
    }
    if horizon:
        # Version 1 keeps its exact key set; the counts exist from version 2 on.
        body_out["limits"] = limits
        body_out["horizon_days"] = horizon
        body_out["days"] = [
            {
                "day": (body.day + timedelta(days=i)).isoformat(),
                "start_at": stamp(bounds[i]),
                "end_at": stamp(bounds[i + 1]),
                "events": sum(
                    1
                    for e in events[:100]
                    if (body.day + timedelta(days=i)).isoformat() in e["days"]
                ),
            }
            for i in range(count)
        ]
        body_out["cancelled_count"] = cancelled_total
    return identity.Result(200, body_out)


def _limit(shown, omitted, forced=False):
    omitted = max(0, omitted)
    return {"shown": shown, "truncated": bool(omitted or forced), "omitted_at_least": omitted}
