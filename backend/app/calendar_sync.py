"""Calendar provider sync: the three-phase protocol and the database side of page application.

Proposal sections 6.8, 6.9, 7.3 and 7.3.1. One page is one complete cycle:

* T1 claims (locks owner, source, sync state in that order), records the stored cursor, commits;
* the provider fetch runs with no lock and no open transaction, under a timeout that is strictly
  shorter than the lease;
* T2 re-locks, verifies the claim and compares the stored cursor, plans the whole page purely
  (``calendar_plan``), writes it in the deterministic order, inserts the change rows, then updates
  the sync state, and commits once; or T3 records a failure or a blocked page.

The provider has no write method and no network is used (synthetic fixtures only).
"""

import logging
import math
import multiprocessing
import os
import signal
import time
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import case, func, literal_column, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from app import calendar_codes as codes
from app import calendar_plan as plan_module
from app import calendar_provider as provider_module
from app import calendar_recurrence as rec
from app import identity, manual_tasks
from app.config import settings
from app.db import SessionLocal
from app.models import (
    CalendarChange,
    CalendarOverride,
    CalendarProviderLink,
    CalendarSeries,
    CalendarSource,
    CalendarSyncState,
)
from app.notification_worker import lock_owner

clock = identity.now_utc  # tests replace this; the database clock is used for last_success_at


def enabled():
    """Provider and sync routes and the worker exist only in development and test, with a
    synthetic store configured (production restriction of section 10)."""
    return (
        settings.env in {"development", "test"}
        and settings.calendar_synthetic_directory is not None
    )


def lease():
    return timedelta(seconds=settings.calendar_lease_seconds)


def aware(value):
    return None if value is None else identity.aware(value)


def touch(row, now):
    """Every guarded update advances the revision by one and never moves updated_at back."""
    row.revision += 1
    row.updated_at = max(now, aware(row.updated_at))


# ---------------------------------------------------------------------------------------------
# Locking: owner, then source, then sync state (one order everywhere)
# ---------------------------------------------------------------------------------------------
def lock_source(db, source_id):
    return db.scalar(
        select(CalendarSource)
        .where(CalendarSource.id == source_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def lock_state(db, source_id):
    return db.scalar(
        select(CalendarSyncState)
        .where(CalendarSyncState.source_id == source_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def lock_all(db, source_id):
    """Returns (user, granted, source, link, state); any of them can be None."""
    owner = db.execute(
        select(CalendarSource.owner_id, CalendarSource.scope_key).where(
            CalendarSource.id == source_id
        )
    ).first()
    if owner is None:
        return None, False, None, None, None
    user, granted = lock_owner(db, owner.owner_id, owner.scope_key)
    source = lock_source(db, source_id)
    link = db.get(CalendarProviderLink, source_id)
    state = lock_state(db, source_id) if link is not None else None
    return user, granted, source, link, state


# ---------------------------------------------------------------------------------------------
# T1: claim
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Claim:
    source_id: object
    token: object
    cursor: str | None  # the stored cursor recorded under the lock (compare-and-swap value)
    ref: str
    explicit: bool


@dataclass(frozen=True)
class Skipped:
    reason: str  # missing | forgotten | owner_unavailable | lease_held | not_due | failed | blocked


def claim(db, source_id, *, explicit=False):
    user, granted, source, link, state = lock_all(db, source_id)
    if source is None or link is None or state is None:
        return Skipped("missing")
    if source.state != "active" or link.provider_ref is None:
        return Skipped("forgotten")
    if user is None or not user.is_active or not granted:
        return Skipped("owner_unavailable")
    now = clock()
    if state.claim_token is not None and aware(state.claim_expires_at) > now:
        return Skipped("lease_held")  # an unexpired lease is a no-op for every caller
    if not explicit:
        if state.status in {"failed", "blocked"}:
            return Skipped(state.status)
        if state.next_attempt_at is not None and aware(state.next_attempt_at) > now:
            return Skipped("not_due")
    if explicit and state.status == "failed":
        state.attempts = 0
    token = uuid4()
    state.claim_token = token
    state.claim_expires_at = now + lease()
    state.last_attempt_at = now
    touch(state, now)
    db.flush()
    return Claim(source_id, token, state.cursor, link.provider_ref, explicit)


# ---------------------------------------------------------------------------------------------
# T3: failure
# ---------------------------------------------------------------------------------------------
def held(db, taken):
    """Lock and verify that the claim is still ours; returns (source, state) or None."""
    _user, _granted, source, link, state = lock_all(db, taken.source_id)
    if (
        source is None
        or link is None
        or state is None
        or source.state != "active"
        or state.claim_token != taken.token
    ):
        return None
    return source, state


def release(state):
    state.claim_token = None
    state.claim_expires_at = None


def fail_retry(db, taken, code):
    """Provider timeout or unavailable: attempts + 1 and the backoff of section 7.3 item 4."""
    owned = held(db, taken)
    if owned is None:
        return None
    _source, state = owned
    now = clock()
    state.attempts += 1
    state.last_error_code = code
    state.blocked_reason = state.blocked_detail = None
    if state.attempts >= codes.RETRY_ATTEMPTS_MAX:
        state.status, state.next_attempt_at = "failed", None
    else:
        state.status = "retry_wait"
        state.next_attempt_at = now + timedelta(seconds=codes.BACKOFF_SECONDS[state.attempts - 1])
    release(state)
    touch(state, now)
    db.flush()
    return state.status


def fail_blocked(db, taken, blocked):
    owned = held(db, taken)
    if owned is None:
        return None
    _source, state = owned
    now = clock()
    state.status = "blocked"
    state.blocked_reason = blocked.code
    state.blocked_detail = blocked.detail(taken.source_id)
    state.next_attempt_at = None
    state.last_error_code = None
    release(state)
    touch(state, now)
    db.flush()
    return "blocked"


# ---------------------------------------------------------------------------------------------
# Stored state, as the pure planner sees it
# ---------------------------------------------------------------------------------------------
def series_content(row):
    timed = row.kind == "timed"
    return rec.Series(
        row.kind,
        row.zone,
        row.start_local if timed else row.start_date,
        row.duration_seconds if timed else row.duration_days,
        row.rule,
        tuple(row.exdates or ()),
        tuple(row.rdates or ()),
        row.title,
        row.status,
    )


def override_content(row):
    return rec.Override(row.recurrence_id, row.status, row.start_wall, row.duration, row.title)


def mentioned(page):
    return {
        item.uid
        for item in page.items
        if isinstance(item.uid, str) and item.entity in {"series", "override"}
    }


class Stored:
    """Loaded rows (ORM objects, for writing) and their planner views."""

    def __init__(self, db, source_id, uids):
        self.series_rows, self.override_rows = {}, {}
        self.series, self.overrides = {}, {}
        if uids:
            for row in db.scalars(
                select(CalendarSeries)
                .where(CalendarSeries.source_id == source_id, CalendarSeries.uid.in_(sorted(uids)))
                .execution_options(populate_existing=True)
            ):
                self.series_rows[row.uid] = row
                self.series[row.uid] = plan_module.StoredSeries(
                    row.id,
                    row.uid,
                    row.state,
                    row.sequence,
                    series_content(row) if row.state == "active" else None,
                )
            by_id = {row.id: row.uid for row in self.series_rows.values()}
            if by_id:
                for row in db.scalars(
                    select(CalendarOverride)
                    .where(CalendarOverride.series_id.in_(list(by_id)))
                    .execution_options(populate_existing=True)
                ):
                    key = (by_id[row.series_id], row.recurrence_id)
                    self.override_rows[key] = row
                    self.overrides[key] = plan_module.StoredOverride(
                        row.id,
                        key[0],
                        row.recurrence_id,
                        row.state,
                        row.sequence,
                        bool(row.deleted_by_cascade),
                        override_content(row) if row.state == "active" else None,
                    )
        counts = db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(case((CalendarSeries.state == "active", 1), else_=0)), 0),
            ).where(CalendarSeries.source_id == source_id)
        ).one()
        self.series_total, self.series_active = int(counts[0]), int(counts[1])


# ---------------------------------------------------------------------------------------------
# Writing a plan
# ---------------------------------------------------------------------------------------------
def set_series_content(row, content):
    timed = content is not None and content.kind == "timed"
    row.kind = None if content is None else content.kind
    row.status = None if content is None else content.status
    row.title = None if content is None else content.title
    row.zone = content.zone_name if timed else None
    row.start_local = content.start if timed else None
    row.start_date = content.start if content is not None and not timed else None
    row.duration_seconds = content.duration if timed else None
    row.duration_days = content.duration if content is not None and not timed else None
    row.rule = None if content is None else content.rule
    row.exdates = None if content is None else list(content.exdates)
    row.rdates = None if content is None else list(content.rdates)
    row.provider_version = None


def set_override_content(row, content):
    row.status = None if content is None else content.status
    row.start_wall = None if content is None else content.start
    row.duration = None if content is None else content.duration
    row.title = None if content is None else content.title


def cascade(db, stored, plan_cascade, now):
    """Tombstone the overrides that were active when their series went down (6.7)."""
    for entry in plan_cascade:
        row = stored.override_rows[(entry.uid, entry.rid)]
        row.state = "deleted"
        row.deleted_by_cascade = True
        row.deleted_at = now
        set_override_content(row, None)
        touch(row, now)
        db.flush()


def write_series(db, source, stored, write, now):
    row = stored.series_rows.get(write.uid)
    if row is None:
        row = CalendarSeries(
            id=uuid4(),
            source_id=source.id,
            owner_id=source.owner_id,
            scope_key=source.scope_key,
            uid=write.uid,
            state=write.state,
            sequence=write.sequence,
            revision=1,
            created_at=now,
            updated_at=now,
            deleted_at=now if write.state == "deleted" else None,
        )
        set_series_content(row, write.content)
        db.add(row)
        db.flush()
        stored.series_rows[write.uid] = row
        return row
    if write.state == "deleted":
        was_active = row.state == "active"
        row.state, row.sequence = "deleted", write.sequence
        if was_active:
            row.deleted_at = now
            set_series_content(row, None)
        touch(row, now)
        db.flush()
        if was_active:
            cascade(db, stored, write.cascade, now)
        return row
    if row.state == "active" and write.pass_sequence is not None:
        # delete, then cascade, then the higher upsert: the required order of the F1 audit
        row.state, row.sequence, row.deleted_at = "deleted", write.pass_sequence, now
        set_series_content(row, None)
        touch(row, now)
        db.flush()
        cascade(db, stored, write.cascade, now)
    row.state, row.sequence, row.deleted_at = "active", write.sequence, None
    set_series_content(row, write.content)
    touch(row, now)
    db.flush()
    return row


def write_override(db, source, stored, write, now):
    key = (write.uid, write.rid)
    row = stored.override_rows.get(key)
    if row is None:
        parent = stored.series_rows[write.uid]
        row = CalendarOverride(
            id=uuid4(),
            series_id=parent.id,
            source_id=source.id,
            owner_id=source.owner_id,
            scope_key=source.scope_key,
            recurrence_id=write.rid,
            state=write.state,
            deleted_by_cascade=False,
            sequence=write.sequence,
            revision=1,
            created_at=now,
            updated_at=now,
            deleted_at=now if write.state == "deleted" else None,
        )
        set_override_content(row, write.content)
        db.add(row)
        db.flush()
        stored.override_rows[key] = row
        return
    if write.state == "active":
        row.state, row.deleted_at = "active", None
        set_override_content(row, write.content)
    else:
        if row.state != "deleted":  # active to deleted by an explicit delete
            row.deleted_at = now
        row.state = "deleted"  # a floor raise keeps the original deleted_at
        set_override_content(row, None)
    row.deleted_by_cascade = False
    row.sequence = write.sequence
    touch(row, now)
    db.flush()


def record_change(db, source, sequence, entity, row_id, write, cascade_count, run, cursor, now):
    content = write.content
    db.add(
        CalendarChange(
            id=uuid4(),
            source_id=source.id,
            owner_id=source.owner_id,
            scope_key=source.scope_key,
            seq=sequence,
            entity=entity,
            series_id=row_id if entity == "series" else None,
            override_id=row_id if entity == "override" else None,
            operation=write.op,
            sequence=write.sequence,
            cascade_count=cascade_count,
            content_hash=write.hash,
            snapshot=None if content is None else plan_module.canonical_of(content),
            actor_id=None,
            sync_run_id=run,
            cursor_after=cursor,
            applied_at=now,
        )
    )
    db.flush()


def success_stamp(db, state, now):
    """The one ``last_success_at`` expression of section 6.5 (database clock, strictly monotonic)."""
    if db.get_bind().dialect.name == "postgresql":
        return func.greatest(
            func.clock_timestamp(),
            func.coalesce(
                CalendarSyncState.last_success_at, literal_column("'-infinity'::timestamptz")
            )
            + literal_column("interval '1 microsecond'"),
        )
    old = aware(state.last_success_at)
    return now if old is None else max(now, old + timedelta(microseconds=1))


@dataclass(frozen=True)
class Applied:
    changes: int
    counters: dict
    caught_up: bool


def apply_page(db, taken, page, since):
    """T2. Returns ``Applied``, or ``None`` when the claim was lost (nothing is written).
    Raises ``PageBlocked`` before any row is written; the caller rolls back and runs T3."""
    owned = held(db, taken)
    if owned is None or owned[1].cursor != taken.cursor:
        return None
    source, state = owned
    now = clock()
    stored = Stored(db, source.id, mentioned(page))
    plan = plan_module.plan_page(
        page,
        since,
        stored.series,
        stored.overrides,
        applied_seq=state.applied_seq,
        series_active=stored.series_active,
        series_total=stored.series_total,
    )
    run = uuid4()
    sequence = state.applied_seq
    for write in plan.series:
        write_series(db, source, stored, write, now)
    for write in plan.overrides:
        write_override(db, source, stored, write, now)
    # Change rows go in before the sync-state update (the guard needs applied_seq = max(seq)).
    for write in plan.series:
        sequence += 1
        row = stored.series_rows[write.uid]
        count = len(write.cascade) if write.op in {"delete", "revive"} else 0
        record_change(
            db, source, sequence, "series", row.id, write, count, run, page.next_cursor, now
        )
    for write in plan.overrides:
        sequence += 1
        row = stored.override_rows[(write.uid, write.rid)]
        record_change(
            db, source, sequence, "override", row.id, write, 0, run, page.next_cursor, now
        )
    applied_before = state.applied_seq
    state.applied_seq = sequence
    caught_up = page.next_cursor == taken.cursor
    if not caught_up:
        state.cursor = page.next_cursor
    state.status = "ok"
    state.attempts = 0
    state.next_attempt_at = state.last_error_code = None
    state.blocked_reason = state.blocked_detail = None
    state.last_success_at = success_stamp(db, state, now)
    release(state)
    touch(state, now)
    db.flush()
    return Applied(sequence - applied_before, dict(plan.counters), caught_up)


# ---------------------------------------------------------------------------------------------
# Fetch (no lock, no open transaction) and the pass
# ---------------------------------------------------------------------------------------------
REAP_SECONDS = 5
logger = logging.getLogger(__name__)


def default_factory(ref):
    if not enabled():
        raise provider_module.ProviderUnavailable("provider mode is not enabled")
    return provider_module.SyntheticProvider(settings.calendar_synthetic_directory, ref)


def _fetch_child(provider, since, sender, timeout):
    """Runs in the forked child only: one provider call, one result, then a hard exit.

    The child arms its own alarm, so even if the parent dies and never kills it, it ends itself
    shortly after the timeout. ``os._exit`` skips every inherited destructor and atexit hook, so
    the parent's database connections and buffers are never touched from here.
    """
    try:
        signal.alarm(max(1, math.ceil(timeout) + 1))
        try:
            result = ("ok", provider.changes(since, codes.PAGE_ITEMS_MAX))
        except BaseException as error:  # noqa: BLE001 - every failure is reported to the parent
            result = ("error", error)
        try:
            sender.send(result)
        except Exception:  # noqa: BLE001 - an unpicklable page or error
            sender.send(("error", provider_module.ProviderUnavailable("unreadable result")))
    finally:
        os._exit(0)


class FetchNotTerminated(provider_module.ProviderUnavailable):
    """The fetch child was still alive after SIGKILL and the bounded wait (a stuck process).

    It is an ordinary retryable failure (``provider_unavailable``, with backoff), never a silent
    success, and it is logged at error level with the child's process id for the operator.
    """


def _reap(pid):
    """End the child for certain: SIGKILL cannot be ignored, and the wait is bounded.

    Waits for this one pid only. Returns True when the child is gone (reaped here, or already
    reaped elsewhere); False means it survived SIGKILL and ``REAP_SECONDS`` (for example a process
    stuck in uninterruptible I/O) and the caller must surface that.
    """
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + REAP_SECONDS
    while True:
        try:
            finished, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return True
        if finished:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.005)


def fetch(provider, since, timeout):
    """One bounded fetch; a fetch that outlives ``timeout`` is a ProviderTimeout.

    The provider call runs in a forked child process that is killed (SIGKILL) at the timeout.
    A running Python thread cannot be cancelled, so a thread would keep working after the timeout
    (and would hold a worker's exit open); a process can be ended for certain. No thread, child
    process or open pipe survives this function, whatever the outcome.

    The child is forked and waited for directly (``os.fork``/``os.waitpid`` on its own pid), not
    through ``multiprocessing.Process``: that class keeps process-wide child bookkeeping that races
    when several threads fetch at once (a child reaped by another thread's cleanup looks alive).
    """
    receiver, sender = multiprocessing.Pipe(duplex=False)
    try:
        pid = os.fork()
    except BaseException:
        receiver.close()
        sender.close()
        raise
    if pid == 0:  # the child: never returns
        receiver.close()
        _fetch_child(provider, since, sender, timeout)
    sender.close()
    try:
        if not receiver.poll(timeout):
            raise provider_module.ProviderTimeout("fetch exceeded its timeout")
        try:
            kind, value = receiver.recv()
        except (EOFError, OSError):
            raise provider_module.ProviderUnavailable("fetch ended without a result") from None
    finally:
        receiver.close()
        if not _reap(pid):
            logger.error("calendar fetch child pid=%s survived SIGKILL; not reaped", pid)
            raise FetchNotTerminated("fetch process could not be terminated")
    if kind == "error":
        # Only ordinary exceptions cross over: a SystemExit or KeyboardInterrupt raised inside the
        # provider must never end this process.
        raise (
            value if isinstance(value, Exception) else provider_module.ProviderUnavailable("failed")
        )
    return value


def failure(error):
    """Map a provider error to ('retry', code) or ('blocked', PageBlocked)."""
    blocked = plan_module.PageBlocked
    if isinstance(error, provider_module.ProviderTimeout):
        return "retry", "provider_timeout"
    if isinstance(error, provider_module.InvalidCursor):
        return "blocked", blocked("cursor_invalid")
    if isinstance(error, provider_module.CursorExpired):
        return "blocked", blocked("cursor_expired")
    if isinstance(error, provider_module.PageTooLarge):
        return "blocked", blocked("page_too_large")
    if isinstance(error, provider_module.MalformedItem):
        return "blocked", blocked("item_malformed")
    return "retry", "provider_unavailable"


def sync_source(
    maker, source_id, factory=None, *, explicit=False, resync=False, pages=codes.PAGES_PER_PASS
):
    """One bounded pass over one source: at most ``pages`` complete T1, fetch, T2/T3 cycles.

    Returns a summary dict; ``outcome`` is one of ok, blocked, retry_wait, failed, skipped, lost.
    """
    factory = factory or default_factory
    summary = {"outcome": "skipped", "reason": None, "pages": 0, "changes": 0}
    totals = Counter()
    for number in range(pages):
        with maker.begin() as db:
            taken = claim(db, source_id, explicit=explicit)
        if isinstance(taken, Skipped):
            summary["reason"] = taken.reason
            summary["counters"] = dict(totals)
            return summary
        since = None if resync and number == 0 else taken.cursor
        try:
            page = fetch(factory(taken.ref), since, settings.calendar_fetch_timeout_seconds)
        except provider_module.ProviderError as error:
            kind, detail = failure(error)
            outcome = record(maker, taken, kind, detail)
            reason = detail.code if kind == "blocked" else None
            return {**summary, "outcome": outcome, "reason": reason, "counters": dict(totals)}
        except Exception:  # noqa: BLE001 - an unknown provider failure is an unavailable provider
            outcome = record(maker, taken, "retry", "provider_unavailable")
            return {**summary, "outcome": outcome, "reason": None, "counters": dict(totals)}
        try:
            with maker.begin() as db:
                applied = apply_page(db, taken, page, since)
        except plan_module.PageBlocked as blocked:
            outcome = record(maker, taken, "blocked", blocked)
            return {**summary, "outcome": outcome, "reason": blocked.code, "counters": dict(totals)}
        if applied is None:
            return {**summary, "outcome": "lost", "counters": dict(totals)}
        summary["pages"] += 1
        summary["changes"] += applied.changes
        totals.update(applied.counters)
        summary["outcome"] = "ok"
        if not page.has_more:
            break
    summary["counters"] = dict(totals)
    return summary


def record(maker, taken, kind, detail):
    with maker.begin() as db:
        if kind == "retry":
            return fail_retry(db, taken, detail) or "lost"
        return fail_blocked(db, taken, detail) or "lost"


def candidates(db, limit=codes.SOURCES_PER_PASS):
    now = clock()
    return list(
        db.scalars(
            select(CalendarSyncState.source_id)
            .join(CalendarSource, CalendarSource.id == CalendarSyncState.source_id)
            .where(
                CalendarSource.state == "active",
                CalendarSyncState.status.in_(("never", "ok", "retry_wait")),
                or_(
                    CalendarSyncState.claim_token.is_(None),
                    CalendarSyncState.claim_expires_at <= now,
                ),
                or_(
                    CalendarSyncState.next_attempt_at.is_(None),
                    CalendarSyncState.next_attempt_at <= now,
                ),
            )
            .order_by(
                CalendarSyncState.last_attempt_at.asc().nulls_first(), CalendarSyncState.source_id
            )
            .limit(limit)
        )
    )


def run_pass(maker=SessionLocal, factory=None, limit=codes.SOURCES_PER_PASS):
    """The scheduled worker's pass: at most 100 sources, each bounded to 10 pages."""
    if not 1 <= limit <= codes.SOURCES_PER_PASS:
        raise ValueError("A bounded pass is required")
    result = Counter(
        checked=0, ok=0, blocked=0, retry_wait=0, failed=0, skipped=0, lost=0, errors=0
    )
    try:
        with maker.begin() as db:
            batch = candidates(db, limit)
    except SQLAlchemyError:
        result["errors"] += 1
        return dict(result)
    result["checked"] = len(batch)
    for source_id in batch:
        try:
            result[sync_source(maker, source_id, factory)["outcome"]] += 1
        except SQLAlchemyError:
            result["errors"] += 1  # a failed transaction rolled back; the lease expires on its own
    return dict(result)


# ---------------------------------------------------------------------------------------------
# Forgetting (6.9): called by calendars.operate after the source row has been flushed as forgotten
# ---------------------------------------------------------------------------------------------
def linked(db, source_id):
    return db.get(CalendarProviderLink, source_id) is not None


def scrub(db, source_id, now):
    """Scrub every provider table in the forgetting transaction. The deferred trigger of section
    6.6 refuses the commit if any step is missing."""
    db.execute(
        update(CalendarOverride)
        .where(CalendarOverride.source_id == source_id)
        .values(
            state="forgotten",
            deleted_by_cascade=False,
            status=None,
            start_wall=None,
            duration=None,
            title=None,
            deleted_at=None,
            revision=CalendarOverride.revision + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(CalendarSeries)
        .where(CalendarSeries.source_id == source_id)
        .values(
            state="forgotten",
            uid=None,
            kind=None,
            status=None,
            title=None,
            start_local=None,
            start_date=None,
            zone=None,
            duration_seconds=None,
            duration_days=None,
            rule=None,
            exdates=None,
            rdates=None,
            provider_version=None,
            deleted_at=None,
            revision=CalendarSeries.revision + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(CalendarChange)
        .where(CalendarChange.source_id == source_id)
        .values(snapshot=None)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(CalendarProviderLink)
        .where(CalendarProviderLink.source_id == source_id)
        .values(provider_ref=None)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(CalendarSyncState)
        .where(CalendarSyncState.source_id == source_id)
        .values(
            status="blocked",
            blocked_reason="source_forgotten",
            cursor=None,
            claim_token=None,
            claim_expires_at=None,
            blocked_detail=None,
            next_attempt_at=None,
            revision=CalendarSyncState.revision + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    db.flush()


# ---------------------------------------------------------------------------------------------
# Export and status (owner only, never for a forgotten source)
# ---------------------------------------------------------------------------------------------
def stamp(value):
    return None if value is None else identity.aware(value).isoformat()


def status_view(state):
    return {
        "status": state.status,
        "attempts": state.attempts,
        "applied_seq": state.applied_seq,
        "last_attempt_at": stamp(state.last_attempt_at),
        "last_success_at": stamp(state.last_success_at),
        "next_attempt_at": stamp(state.next_attempt_at),
        "last_error_code": state.last_error_code,
        "blocked_reason": state.blocked_reason,
        "blocked_detail": state.blocked_detail,
    }


def export_view(db, source_id):
    """Active series with their active overrides, and the sync summary (bounded by section 9)."""
    state = db.get(CalendarSyncState, source_id)
    series = list(
        db.scalars(
            select(CalendarSeries)
            .where(CalendarSeries.source_id == source_id, CalendarSeries.state == "active")
            .order_by(CalendarSeries.uid)
        )
    )
    overrides = {}
    for row in db.scalars(
        select(CalendarOverride)
        .where(CalendarOverride.source_id == source_id, CalendarOverride.state == "active")
        .order_by(CalendarOverride.recurrence_id)
    ):
        overrides.setdefault(row.series_id, []).append(
            {
                "recurrence_id": row.recurrence_id,
                "status": row.status,
                "start": row.start_wall,
                "duration": row.duration,
                "title": row.title,
                "sequence": row.sequence,
            }
        )
    counts = db.execute(
        select(CalendarSeries.state, func.count())
        .where(CalendarSeries.source_id == source_id)
        .group_by(CalendarSeries.state)
    ).all()
    return {
        "sync": None if state is None else status_view(state),
        "series": [
            {
                "uid": row.uid,
                "kind": row.kind,
                "zone": row.zone,
                "start": (row.start_local or row.start_date).isoformat(),
                "duration": row.duration_seconds or row.duration_days,
                "rule": row.rule,
                "exdates": row.exdates,
                "rdates": row.rdates,
                "title": row.title,
                "status": row.status,
                "sequence": row.sequence,
                "overrides": overrides.get(row.id, []),
            }
            for row in series
        ],
        "tombstones": {state: int(n) for state, n in counts if state != "active"},
    }


# ---------------------------------------------------------------------------------------------
# Link declaration (owner only, development and test only)
# ---------------------------------------------------------------------------------------------
def declare(db, token, csrf, identifier, body):
    """Mark an unconfigured, never-imported source as provider-mode (6.1, 6.6)."""
    current = manual_tasks.authority(db, token, csrf, body.scope, event_prefix="calendar")
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    if not enabled():
        return identity.denied(db, 404, "calendar.not_found", user=user)
    row = db.scalar(
        select(CalendarSource)
        .where(CalendarSource.id == identifier, CalendarSource.scope_key == body.scope)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or row.owner_id != user.id or row.state == "forgotten":
        return identity.denied(db, 404, "calendar.not_found", user=user)
    if (
        row.state != "active"
        or row.revision != 1
        or (row.data or {}).get("status") != "setup_required"
        or db.get(CalendarProviderLink, row.id) is not None
    ):
        return identity.denied(db, 409, "calendar.provider_mode", user=user)
    try:
        provider_module.SyntheticProvider(settings.calendar_synthetic_directory, body.provider_ref)
    except provider_module.ProviderUnavailable:
        return identity.denied(db, 422, "calendar.provider_unavailable", user=user)
    now = clock()
    db.add(
        CalendarProviderLink(
            source_id=row.id,
            owner_id=row.owner_id,
            scope_key=row.scope_key,
            provider_kind="synthetic",
            provider_ref=body.provider_ref,
            created_at=now,
        )
    )
    db.flush()
    state = CalendarSyncState(
        source_id=row.id,
        owner_id=row.owner_id,
        scope_key=row.scope_key,
        status="never",
        applied_seq=0,
        attempts=0,
        revision=1,
        updated_at=now,
    )
    db.add(state)
    db.flush()
    identity.audit(
        db,
        "calendar.provider_linked",
        "success",
        user=user,
        scope=body.scope,
        entity_type="calendar_source",
        entity=str(row.id),
        metadata={"provider_kind": "synthetic"},
    )
    return identity.Result(200, {"source_id": str(row.id), "provider": status_view(state)})


# ---------------------------------------------------------------------------------------------
# Owner routes (8.1): sync and sync-status exist only where ``enabled()``; any other case is the
# same 404 (disabled, foreign, forgotten, not linked), so the routes reveal nothing.
# ---------------------------------------------------------------------------------------------
def _owned(db, token, csrf, identifier, body):
    current = manual_tasks.authority(db, token, csrf, body.scope, event_prefix="calendar")
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    if not enabled():
        return identity.denied(db, 404, "calendar.not_found", user=user)
    row = db.scalar(
        select(CalendarSource)
        .where(CalendarSource.id == identifier, CalendarSource.scope_key == body.scope)
        .execution_options(populate_existing=True)
    )
    state = db.get(CalendarSyncState, identifier) if row is not None else None
    if (
        row is None
        or row.owner_id != user.id
        or row.state != "active"
        or state is None
        or state.status == "blocked"
        and state.blocked_reason == "source_forgotten"
    ):
        return identity.denied(db, 404, "calendar.not_found", user=user)
    return user, row, state


def authorize(db, token, csrf, identifier, body):
    """Authorize an owner sync request; nothing is written."""
    found = _owned(db, token, csrf, identifier, body)
    return found if isinstance(found, identity.Result) else identity.Result(200, {})


def status(db, token, csrf, identifier, body, summary=None):
    """The owner's sync status: codes, counts and times only, never content or the cursor."""
    found = _owned(db, token, csrf, identifier, body)
    if isinstance(found, identity.Result):
        return found
    user, row, state = found
    payload = {"source_id": str(row.id), "provider": status_view(state)}
    metadata = {"status": state.status}
    if summary is not None:
        brief = {
            "outcome": summary["outcome"],
            "reason": summary.get("reason"),
            "pages": summary["pages"],
            "changes": summary["changes"],
            "counters": summary.get("counters", {}),
        }
        payload["sync"] = brief
        metadata.update(outcome=brief["outcome"], pages=brief["pages"], changes=brief["changes"])
    identity.audit(
        db,
        "calendar.sync_requested" if summary is not None else "calendar.sync_status",
        "success",
        user=user,
        scope=body.scope,
        entity_type="calendar_source",
        entity=str(row.id),
        metadata=metadata,
    )
    return identity.Result(200, payload)
