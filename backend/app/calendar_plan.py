"""Pure page planner for calendar provider sync (proposal 7.3.1, Steps 1 to 5).

``plan_page`` takes one fetched ``ChangePage`` and the stored state the page touches and returns a
``Plan`` (net results in the deterministic write order) or raises ``PageBlocked`` with a stable code
and the sanitized detail of section 7.3.2. It touches no database, clock or network: the same items
in any order give the identical plan (Step 4).
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field

from app import calendar_codes as codes
from app import calendar_recurrence as rec


def ordered(*parts):
    """UTF-8 byte-string sort key (never a database collation or locale)."""
    return tuple((p or "").encode("utf-8") for p in parts)


class PageBlocked(Exception):
    """A whole page is refused; ``detail`` is the six-key object of section 7.3.2."""

    def __init__(self, code, entity="page", item_index=None, sequence=None, uid=None, rid=None):
        super().__init__(code)
        self.code, self.entity = code, entity
        self.item_index, self.sequence, self.uid, self.rid = item_index, sequence, uid, rid

    def detail(self, source_id):
        uid = self.uid if isinstance(self.uid, str) and self.uid else None
        return {
            "code": self.code,
            "entity": self.entity,
            "item_index": self.item_index,
            "sequence": self.sequence,
            "uid_digest": None if uid is None else codes.uid_digest(source_id, uid),
            "recurrence_digest": (
                None
                if uid is None or self.rid is None
                else codes.recurrence_digest(source_id, uid, self.rid)
            ),
        }


# ---------------------------------------------------------------------------------------------
# Content hashes (canonical content, never wire text)
# ---------------------------------------------------------------------------------------------
def series_canonical(series):
    return {
        "kind": series.kind,
        "zone": series.zone_name,
        "start": series.start.isoformat(),
        "duration": series.duration,
        "rule": series.rule,
        "exdates": list(series.exdates),
        "rdates": list(series.rdates),
        "title": series.title,
        "status": series.status,
    }


def override_canonical(override):
    return {
        "rid": override.recurrence_id,
        "status": override.status,
        "start": override.start,
        "duration": override.duration,
        "title": override.title,
    }


def canonical_of(content):
    return (
        series_canonical(content)
        if isinstance(content, rec.Series)
        else override_canonical(content)
    )


def hash_of(content):
    if content is None:
        return codes.TOMBSTONE_HASH
    text = json.dumps(
        canonical_of(content), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------
# Stored state handed in by the database layer
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class StoredSeries:
    id: object
    uid: str
    state: str  # active | deleted
    sequence: int
    content: rec.Series | None = None


@dataclass(frozen=True)
class StoredOverride:
    id: object
    uid: str  # series uid
    rid: str  # canonical recurrence id
    state: str  # active | deleted
    sequence: int
    cascade: bool = False
    content: rec.Override | None = None


# ---------------------------------------------------------------------------------------------
# Step 2: per-entity simulation
# ---------------------------------------------------------------------------------------------
@dataclass
class Item:
    index: int
    sequence: int
    op: str
    hash: str
    content: object = None


@dataclass
class State:
    kind: str  # absent | active | deleted
    sequence: int = -1
    hash: str | None = None
    cascade: bool = False
    content: object = None


@dataclass
class Reduced:
    start: State
    end: State
    applied: bool = False
    pass_sequence: int | None = None  # sequence of the delete that took an active entity down
    counters: Counter = field(default_factory=Counter)
    conflict: bool = False


def reduce_entity(items, start):
    result = Reduced(
        start, State(start.kind, start.sequence, start.hash, start.cascade, start.content)
    )
    by_sequence = {}
    for item in sorted(items, key=lambda i: (i.sequence, i.index)):
        first = by_sequence.setdefault(item.sequence, item)
        if first is item:
            continue
        if (first.op, first.hash) != (item.op, item.hash):
            result.conflict = True
            return result
        result.counters["replayed"] += 1
    state = result.end
    for q in sorted(by_sequence):
        item = by_sequence[q]
        apply = False
        if state.kind == "absent":
            apply = True
        elif q < state.sequence:
            result.counters["ignored_stale"] += 1
        elif state.kind == "active" and q == state.sequence:
            if item.op == "upsert" and item.hash == state.hash:
                result.counters["replayed"] += 1
            else:
                result.conflict = True
                return result
        elif state.kind == "deleted" and q == state.sequence:
            if item.op == "delete" and not state.cascade:
                result.counters["replayed"] += 1
            else:
                result.conflict = True
                return result
        else:
            apply = True
        if not apply:
            continue
        result.applied = True
        if item.op == "upsert":
            state.kind, state.hash, state.content = "active", item.hash, item.content
        else:
            if state.kind == "active" and result.pass_sequence is None:
                result.pass_sequence = q
            state.kind, state.hash, state.content = "deleted", None, None
        state.sequence, state.cascade = q, False
    return result


def net_operation(stored_kind, end_kind):
    """Section 7.3.1 net-result table, from the state stored at the start of the page."""
    if end_kind == "deleted":
        return "delete"
    return "revive" if stored_kind == "deleted" else "upsert"


# ---------------------------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------------------------
@dataclass
class SeriesWrite:
    uid: str
    stored: StoredSeries | None
    op: str  # upsert | delete | revive (the change-row operation)
    state: str  # final state: active | deleted
    sequence: int
    hash: str
    content: rec.Series | None
    pass_sequence: int | None  # active -> deleted(pass) -> cascade -> active in one page
    cascade: tuple  # StoredOverride rows tombstoned by this write, in recurrence-id byte order


@dataclass
class OverrideWrite:
    uid: str
    rid: str
    stored: StoredOverride | None
    op: str
    state: str
    sequence: int
    hash: str
    content: rec.Override | None


@dataclass
class Plan:
    series: list = field(default_factory=list)  # write order: deletes, then upserts and revives
    overrides: list = field(default_factory=list)  # write order: deletes, then upserts and revives
    counters: Counter = field(default_factory=Counter)

    @property
    def change_rows(self):
        return len(self.series) + len(self.overrides)


# ---------------------------------------------------------------------------------------------
# Errors: the first violated step is reported (7.3.2)
# ---------------------------------------------------------------------------------------------
class Errors:
    def __init__(self):
        self.entries = []

    def add(self, step, key, error):
        self.entries.append((step, key, error))

    def raise_first(self, upto=None):
        pool = [e for e in self.entries if upto is None or e[0] <= upto]
        if pool:
            raise min(pool, key=lambda e: (e[0], e[1]))[2]


def _wire_size(items):
    try:
        text = json.dumps(
            [[i.entity, i.operation, i.uid, i.sequence, i.recurrence_id, i.body] for i in items],
            ensure_ascii=False,
        )
    except (TypeError, ValueError):
        return codes.PAGE_BYTES_MAX + 1
    return len(text.encode("utf-8"))


def _shape(index, item):
    """Structural validation; returns (entity, uid, rid, sequence) or raises item_malformed."""
    entity = item.entity if item.entity in ("series", "override") else None
    uid = item.uid if isinstance(item.uid, str) and 1 <= len(item.uid) <= 255 else None
    sequence = item.sequence if type(item.sequence) is int and 0 <= item.sequence < 2**31 else None
    bad = PageBlocked("item_malformed", entity or "page", index, sequence, uid)
    if entity is None or uid is None or not uid.strip() or sequence is None:
        raise bad
    if item.operation not in ("upsert", "delete"):
        raise bad
    rid = item.recurrence_id
    if entity == "series" and rid is not None:
        raise bad
    if entity == "override" and not (isinstance(rid, str) and 1 <= len(rid) <= 128):
        raise bad
    if item.operation == "upsert" and not isinstance(item.body, dict):
        raise bad
    if item.operation == "delete" and item.body is not None:
        raise bad
    return entity, uid, rid, sequence


def _start_state(stored):
    if stored is None:
        return State("absent")
    active = stored.state == "active"
    return State(
        stored.state,
        stored.sequence,
        hash_of(stored.content) if active else None,
        getattr(stored, "cascade", False),
        stored.content if active else None,
    )


def _rid_text(raw):
    return raw.recurrence_id if isinstance(raw.recurrence_id, str) else ""


def plan_page(
    page,
    since,
    stored_series,
    stored_overrides,
    *,
    applied_seq,
    series_active,
    series_total,
):
    """Plan one page. ``stored_series``: uid -> StoredSeries; ``stored_overrides``: (uid, rid) ->
    StoredOverride, for every series the page mentions. Raises ``PageBlocked``."""
    errors = Errors()
    items = tuple(page.items)

    # Step 1: page level (cursor, size, count) -------------------------------------------------
    cursor = page.next_cursor
    if not isinstance(cursor, str) or not 1 <= len(cursor) <= codes.CURSOR_MAX:
        raise PageBlocked("cursor_malformed")
    if cursor == since and (items or page.has_more):
        raise PageBlocked("cursor_no_progress")
    if len(items) > codes.PAGE_ITEMS_MAX or _wire_size(items) > codes.PAGE_BYTES_MAX:
        raise PageBlocked("page_too_large")

    # Step 1: shape and grammar of every item --------------------------------------------------
    series_items, override_items = {}, {}  # uid -> [Item]; uid -> [(index, item, rid, seq)]
    for index, raw in enumerate(items):
        try:
            entity, uid, rid, sequence = _shape(index, raw)
        except PageBlocked as error:
            kind = 1 if error.entity == "override" else 0
            errors.add(1, (kind, *ordered(error.uid, _rid_text(raw)), index), error)
            continue
        if entity == "override":
            override_items.setdefault(uid, []).append((index, raw, rid, sequence))
            continue
        entry = Item(index, sequence, raw.operation, codes.TOMBSTONE_HASH)
        if raw.operation == "upsert":
            try:
                entry.content = rec.normalize_series(raw.body)
            except rec.RecurrenceError as error:
                errors.add(
                    1,
                    (0, *ordered(uid), b"", index),
                    PageBlocked(error.code, "series", index, sequence, uid),
                )
                continue
            entry.hash = hash_of(entry.content)
        series_items.setdefault(uid, []).append(entry)
    errors.raise_first()

    # Step 2: series -----------------------------------------------------------------------------
    plan = Plan()
    counters = plan.counters
    reductions = {}
    for uid, group in series_items.items():
        result = reduce_entity(group, _start_state(stored_series.get(uid)))
        if result.conflict:
            top = max(group, key=lambda i: (i.sequence, -i.index))
            errors.add(
                2,
                (0, *ordered(uid), b"", top.index),
                PageBlocked("sequence_conflict", "series", top.index, top.sequence, uid),
            )
            continue
        counters.update(result.counters)
        reductions[uid] = result

    def final_series(uid):
        if uid in reductions:
            return reductions[uid].end
        stored = stored_series.get(uid)
        return None if stored is None else _start_state(stored)

    # A series that is active at the start and deleted (or passed through a delete) at the end
    # cascades every stored active override (6.7).
    cascade_by_uid = {}
    for uid, result in reductions.items():
        went_down = result.end.kind == "deleted" or result.pass_sequence is not None
        if result.applied and result.start.kind == "active" and went_down:
            cascade_by_uid[uid] = tuple(
                sorted(
                    (
                        o
                        for (u, _), o in stored_overrides.items()
                        if u == uid and o.state == "active"
                    ),
                    key=lambda o: ordered(o.rid),
                )
            )

    # Overrides: grammar (Step 1) and reduction (Step 2) against the series' final state --------
    reduced_overrides = {}  # (uid, rid) -> (Reduced, top item)
    for uid, group in override_items.items():
        final = final_series(uid)
        if final is None:
            top = min(group, key=lambda g: (ordered(g[2]), -g[3], g[0]))
            errors.add(
                3,
                (1, *ordered(uid, top[2]), top[0]),
                PageBlocked("override_orphan", "override", top[0], top[3], uid),
            )
            continue
        if final.kind == "deleted":
            counters["superseded_by_delete"] += len(group)
            continue
        series = final.content
        grouped = {}
        for index, raw, wire_rid, sequence in group:
            entry = Item(index, sequence, raw.operation, codes.TOMBSTONE_HASH)
            try:
                canonical = rec.parse_value(
                    wire_rid, kind=series.kind, zone=series.zone, role="override"
                )
                if raw.operation == "upsert":
                    entry.content = rec.normalize_override(raw.body, series)
                    if entry.content.recurrence_id != canonical:
                        raise rec.RecurrenceError("item_malformed")
                    entry.hash = hash_of(entry.content)
            except rec.RecurrenceError as error:
                errors.add(
                    1,
                    (1, *ordered(uid, wire_rid), index),
                    PageBlocked(error.code, "override", index, sequence, uid),
                )
                continue
            grouped.setdefault(canonical, []).append(entry)
        cascaded = {o.rid for o in cascade_by_uid.get(uid, ())}
        for rid, entries in grouped.items():
            stored = stored_overrides.get((uid, rid))
            start = _start_state(stored)
            if stored is not None and stored.state == "active" and rid in cascaded:
                start = State("deleted", stored.sequence, None, True, None)
            result = reduce_entity(entries, start)
            top = max(entries, key=lambda i: (i.sequence, -i.index))
            if result.conflict:
                errors.add(
                    2,
                    (1, *ordered(uid, rid), top.index),
                    PageBlocked("sequence_conflict", "override", top.index, top.sequence, uid, rid),
                )
                continue
            counters.update(result.counters)
            reduced_overrides[(uid, rid)] = (result, top)
    errors.raise_first(upto=3)

    # Step 3: membership of every override that ends active ------------------------------------
    candidates = {}  # (uid, rid) -> (sequence, item_index)
    for (uid, rid), (result, top) in reduced_overrides.items():
        if result.end.kind == "active":
            candidates[(uid, rid)] = (top.sequence, top.index)
    for uid, result in reductions.items():
        changed = (
            result.end.kind == "active" and result.applied and result.start.hash != result.end.hash
        )
        if not changed:
            continue
        gone = {o.rid for o in cascade_by_uid.get(uid, ())}
        for (u, rid), stored in stored_overrides.items():
            if (
                u == uid
                and stored.state == "active"
                and rid not in gone
                and (u, rid) not in reduced_overrides  # reduced above: checked only if still active
            ):
                candidates[(u, rid)] = (stored.sequence, None)
    for uid, rid in sorted(candidates, key=lambda k: ordered(*k)):
        sequence, index = candidates[(uid, rid)]
        try:
            code = None if rec.is_member(final_series(uid).content, rid) else "override_unmatched"
        except rec.RecurrenceError as error:
            code = error.code
        if code:
            errors.add(
                3,
                (1, *ordered(uid, rid), 0),
                PageBlocked(code, "override", index, sequence, uid, rid),
            )
    errors.raise_first(upto=3)

    # Step 4: deterministic write order --------------------------------------------------------
    deletes, upserts = [], []
    for uid in sorted(reductions, key=ordered):
        result = reductions[uid]
        if not result.applied:
            continue
        stored = stored_series.get(uid)
        end = result.end
        op = net_operation("absent" if stored is None else stored.state, end.kind)
        went_down = (
            result.start.kind == "active"
            and result.pass_sequence is not None
            and end.kind == "active"
        )
        if went_down:
            op = "revive"
        write = SeriesWrite(
            uid,
            stored,
            op,
            end.kind,
            end.sequence,
            codes.TOMBSTONE_HASH if end.kind == "deleted" else end.hash,
            end.content if end.kind == "active" else None,
            result.pass_sequence if went_down else None,
            cascade_by_uid.get(uid, ()),
        )
        (deletes if end.kind == "deleted" else upserts).append(write)
    plan.series = deletes + upserts
    odeletes, oupserts = [], []
    for key in sorted(reduced_overrides, key=lambda k: ordered(*k)):
        result, _top = reduced_overrides[key]
        if not result.applied:
            continue
        uid, rid = key
        stored = stored_overrides.get(key)
        end = result.end
        write = OverrideWrite(
            uid,
            rid,
            stored,
            net_operation("absent" if stored is None else stored.state, end.kind),
            end.kind,
            end.sequence,
            codes.TOMBSTONE_HASH if end.kind == "deleted" else end.hash,
            end.content if end.kind == "active" else None,
        )
        (odeletes if end.kind == "deleted" else oupserts).append(write)
    plan.overrides = odeletes + oupserts

    # Step 5: limits against the final state of the complete page ------------------------------
    active, total = series_active, series_total
    for write in plan.series:
        before = write.stored.state if write.stored else None
        total += write.stored is None
        active += (write.state == "active") - (before == "active")
    if active > codes.ACTIVE_SERIES_MAX:
        errors.add(5, (0,), PageBlocked("series_limit"))
    if total > codes.TOTAL_SERIES_MAX:
        errors.add(5, (1,), PageBlocked("tombstone_limit"))
    per_series = {}  # uid -> [active, total] after the page
    for (uid, _rid), stored in stored_overrides.items():
        counts = per_series.setdefault(uid, [0, 0])
        counts[0] += stored.state == "active"
        counts[1] += 1
    cascaded_keys = set()
    for write in plan.series:
        for stored in write.cascade:
            per_series[write.uid][0] -= 1
            cascaded_keys.add((stored.uid, stored.rid))
    for write in plan.overrides:
        counts = per_series.setdefault(write.uid, [0, 0])
        was_active = (
            write.stored is not None
            and write.stored.state == "active"
            and (write.uid, write.rid) not in cascaded_keys
        )
        counts[1] += write.stored is None
        counts[0] += (write.state == "active") - was_active
    for uid in sorted(per_series, key=ordered):
        active_count, total_count = per_series[uid]
        if active_count > codes.ACTIVE_OVERRIDES_MAX:
            errors.add(5, (2,), PageBlocked("override_limit"))
        if total_count > codes.TOTAL_OVERRIDES_MAX:
            errors.add(5, (3,), PageBlocked("tombstone_limit"))
    if applied_seq + plan.change_rows > codes.CHANGE_ROWS_MAX:
        errors.add(5, (4,), PageBlocked("change_log_full"))
    errors.raise_first()
    return plan
