"""Read side of provider mode: per-source state, occurrence expansion on read, duplicate notes.

Nothing here writes. Occurrences are expanded from stored series and overrides for the requested
window and are never stored (proposal 5 and 8). A stored item that cannot be read is counted and
reported (``unreadable``); it is never silently dropped and never a server error.
"""

from datetime import timedelta

from sqlalchemy import select

from app import calendar_codes as codes
from app import calendar_contracts as contract
from app import calendar_recurrence as rec
from app import calendar_sync, identity
from app.models import CalendarOverride, CalendarSeries, CalendarSyncState

STALE_AFTER = timedelta(hours=24)
READ_ERRORS = (
    rec.RecurrenceError,
    ValueError,
    LookupError,
    TypeError,
    AttributeError,
    OverflowError,
)
STATES = ("available", "stale", "unavailable", "blocked", "unknown_coverage", "limit_reached")


def sync_states(db, source_ids):
    """Sync state per provider-mode source; ordinary sources are absent from the result."""
    if not source_ids:
        return {}
    rows = db.scalars(select(CalendarSyncState).where(CalendarSyncState.source_id.in_(source_ids)))
    return {row.source_id: row for row in rows}


def provider_state(row, now, *, unreadable=0):
    """The section 8.2 enum for a provider source, with the evidence for it."""
    as_of = row.last_success_at
    if row.status == "blocked":
        reason = row.blocked_reason
        state = "limit_reached" if reason in codes.LIMIT_CODES else "blocked"
    elif row.status in {"failed", "retry_wait"}:
        state = "unavailable"
    elif as_of is None:
        state = "unknown_coverage"
    elif now - identity.aware(as_of) > STALE_AFTER:
        state = "stale"
    else:
        state = "available"
    if unreadable and state in {"available", "stale"}:
        state = "unknown_coverage"  # coverage cannot be asserted for unreadable stored items
    return state


def manual_state(snapshot, status, covers, now, *, unreadable=0):
    if snapshot is None or not covers or unreadable:
        return "unknown_coverage"
    if status in {"offline", "failed"}:
        return "unavailable"
    fetched = identity.aware(contract.datetime.fromisoformat(snapshot["fetched_at"]))
    return "stale" if now - fetched > STALE_AFTER else "available"


def expand_source(db, source, window, tz):
    """Occurrences of every active series of one provider source over ``window``.

    Returns ``(events, info)``; ``info`` carries ``cancelled_count``, ``truncated_series``,
    ``omitted_at_least`` and ``unreadable`` (stored series or overrides that cannot be read).
    """
    info = {"cancelled_count": 0, "truncated_series": [], "omitted_at_least": 0, "unreadable": 0}
    overrides = {}
    for row in db.scalars(
        select(CalendarOverride)
        .where(CalendarOverride.source_id == source.id, CalendarOverride.state == "active")
        .order_by(CalendarOverride.recurrence_id)
    ):
        overrides.setdefault(row.series_id, []).append(row)
    events = []
    series_rows = db.scalars(
        select(CalendarSeries)
        .where(CalendarSeries.source_id == source.id, CalendarSeries.state == "active")
        .order_by(CalendarSeries.uid)
    )
    for row in series_rows:
        try:
            content = calendar_sync.series_content(row)
            stored = [calendar_sync.override_content(o) for o in overrides.get(row.id, [])]
            result = rec.expand(
                content,
                stored,
                window,
                meta={"uid": row.uid, "sequence": row.sequence},
                all_day_zone=tz,
            )
        except READ_ERRORS:
            info["unreadable"] += 1
            continue
        info["cancelled_count"] += result.cancelled_count
        if result.truncated:
            info["truncated_series"].append(str(row.id))
            info["omitted_at_least"] += max(
                1, result.occurrences_at_least - len(result.occurrences)
            )
        events.extend(result.occurrences)
    return events, info


def duplicate_notes(events):
    """Flag, never merge: same title and overlapping interval across different sources."""
    groups = {}
    for event in events:
        groups.setdefault(event["title"].strip().casefold(), []).append(event)
    for group in groups.values():
        if len(group) < 2:
            continue
        for event in group:
            low, high = contract.interval(event)
            others = sorted(
                other["id"]
                for other in group
                if other["source_id"] != event["source_id"]
                and contract.interval(other)[0] < high
                and contract.interval(other)[1] > low
            )
            if others:
                event["possible_duplicate_of"] = others[:5]
