"""Sync protocol on SQLite: claims, leases, backoff, pages, blocking, crash points, forgetting.

The database triggers of migration 0035 do not exist on SQLite; the same scenarios run against
real PostgreSQL in ``tests/integration/test_calendar_sync_postgres.py``.
"""

import os
import sys
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from calendar_synthetic_writer import SyntheticWriter
from sqlalchemy import func, select
from test_approvals import signin
from test_calendars import call, create

from app import calendar_codes as codes
from app import calendar_plan as planner
from app import calendar_sync as sync
from app import identity
from app.config import settings
from app.models import (
    CalendarChange,
    CalendarOverride,
    CalendarProviderLink,
    CalendarSeries,
    CalendarSource,
    CalendarSyncState,
    User,
)

RID = "TZID=Europe/Paris:20260322T090000"
RID_NEXT = RID.replace("0322", "0316")
CANON = "2026-03-22T09:00:00"


def series_item(uid="s1", sequence=1, op="upsert", **extra):
    return {
        "entity": "series",
        "operation": op,
        "uid": uid,
        "sequence": sequence,
        "body": None
        if op == "delete"
        else {
            "title": "Synthetic",
            "dtstart": "TZID=Europe/Paris:20260315T090000",
            "duration": 3600,
            "rrule": "FREQ=WEEKLY;COUNT=4",
            **extra,
        },
    }


def override_item(uid="s1", sequence=1, op="upsert", rid=RID, status="cancelled"):
    return {
        "entity": "override",
        "operation": op,
        "uid": uid,
        "recurrence_id": rid,
        "sequence": sequence,
        "body": None if op == "delete" else {"recurrence_id": rid, "status": status},
    }


class Clock:
    def __init__(self):
        self.value = identity.now_utc()

    def __call__(self):
        return self.value

    def advance(self, **delta):
        self.value += timedelta(**delta)


class World:
    def __init__(self, maker, directory, writer, clock):
        self.maker, self.directory, self.writer, self.clock = maker, directory, writer, clock

    def source(self, ref="household", label="Synthetic provider calendar", owner=None):
        with self.maker.begin() as db:
            owner = owner or db.scalar(select(User.id).where(User.slug == "alice"))
            now = self.clock()
            row = CalendarSource(
                owner_id=owner,
                scope_key="household_shared",
                state="active",
                revision=1,
                data={
                    "label": label,
                    "status": "setup_required",
                    "window": None,
                    "attempt_at": None,
                    "changes": None,
                },
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            db.add(
                CalendarProviderLink(
                    source_id=row.id,
                    owner_id=owner,
                    scope_key="household_shared",
                    provider_kind="synthetic",
                    provider_ref=ref,
                    created_at=now,
                )
            )
            db.flush()
            db.add(
                CalendarSyncState(
                    source_id=row.id,
                    owner_id=owner,
                    scope_key="household_shared",
                    status="never",
                    applied_seq=0,
                    attempts=0,
                    revision=1,
                    updated_at=now,
                )
            )
            return row.id

    def sync(self, source, **kwargs):
        return sync.sync_source(self.maker, source, **kwargs)

    def state(self, source):
        with self.maker() as db:
            row = db.get(CalendarSyncState, source)
            db.refresh(row)
            return SimpleNamespace(**{c.name: getattr(row, c.name) for c in row.__table__.columns})

    def rows(self, model, source, **where):
        with self.maker() as db:
            query = select(model).where(model.source_id == source)
            for key, value in where.items():
                query = query.where(getattr(model, key) == value)
            return [
                SimpleNamespace(**{c.name: getattr(r, c.name) for c in r.__table__.columns})
                for r in db.scalars(query)
            ]

    def fingerprint(self, source):
        state = self.state(source)
        return (
            [(r.uid, r.state, r.sequence, r.revision) for r in self.rows(CalendarSeries, source)],
            sorted(
                (r.recurrence_id, r.state, r.sequence, r.revision, r.deleted_by_cascade)
                for r in self.rows(CalendarOverride, source)
            ),
            sorted(r.seq for r in self.rows(CalendarChange, source)),
            state.cursor,
            state.applied_seq,
        )


def make_world(auth_store, tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(sync, "clock", clock)
    monkeypatch.setattr(settings, "calendar_synthetic_directory", tmp_path)
    monkeypatch.setattr(settings, "calendar_lease_seconds", 120)
    monkeypatch.setattr(settings, "calendar_fetch_timeout_seconds", 30.0)
    return World(auth_store, tmp_path, SyntheticWriter(tmp_path / "household.sqlite"), clock)


@pytest.fixture
def world(auth_store, tmp_path, monkeypatch):
    return make_world(auth_store, tmp_path, monkeypatch)


# ---------------------------------------------------------------------------------------------
# Happy path, idempotence, caught-up
# ---------------------------------------------------------------------------------------------
def test_a_first_sync_applies_a_page_and_advances_the_cursor_with_the_change_rows(world):
    source = world.source()
    ids = world.writer.append([series_item(), override_item()])
    result = world.sync(source)
    assert (result["outcome"], result["pages"], result["changes"]) == ("ok", 1, 2)
    state = world.state(source)
    assert (state.status, state.cursor, state.applied_seq, state.attempts) == (
        "ok",
        f"v1:{ids[-1]}",
        2,
        0,
    )
    assert state.claim_token is None and state.last_success_at is not None
    series = world.rows(CalendarSeries, source)[0]
    assert (series.uid, series.state, series.kind, series.zone, series.title) == (
        "s1",
        "active",
        "timed",
        "Europe/Paris",
        "Synthetic",
    )
    override = world.rows(CalendarOverride, source)[0]
    assert (override.recurrence_id, override.state, override.status) == (
        CANON,
        "active",
        "cancelled",
    )
    changes = sorted(world.rows(CalendarChange, source), key=lambda r: r.seq)
    assert [(c.seq, c.entity, c.operation, c.cascade_count) for c in changes] == [
        (1, "series", "upsert", 0),
        (2, "override", "upsert", 0),
    ]
    assert all(c.cursor_after == f"v1:{ids[-1]}" and c.actor_id is None for c in changes)


def test_syncing_again_is_a_caught_up_no_op_that_still_advances_last_success(world):
    source = world.source()
    world.writer.append([series_item()])
    world.sync(source)
    first = world.state(source)
    before = world.fingerprint(source)
    world.clock.advance(seconds=5)
    result = world.sync(source)
    second = world.state(source)
    assert result["outcome"] == "ok" and result["changes"] == 0
    assert world.fingerprint(source)[:3] == before[:3] and second.cursor == first.cursor
    assert (
        second.last_success_at > first.last_success_at and second.revision == first.revision + 2
    )  # claim, then apply


def test_replaying_a_page_applies_nothing_new_and_counts_the_replays(world):
    source = world.source()
    world.writer.append([series_item(), override_item()])
    world.sync(source)
    before = world.fingerprint(source)
    result = world.sync(source, explicit=True, resync=True)
    assert result["changes"] == 0 and result["counters"] == {"replayed": 2}
    assert world.fingerprint(source) == before


def test_a_pass_reads_at_most_ten_pages_and_the_next_pass_continues(world):
    source = world.source()
    world.writer.append([series_item(sequence=n, title=f"Version {n}") for n in range(1, 1106)])
    first = world.sync(source)
    assert (first["outcome"], first["pages"]) == ("ok", codes.PAGES_PER_PASS)
    mid = world.state(source)
    assert mid.cursor == "v1:1000"
    second = world.sync(source)
    assert second["pages"] == 2 and world.state(source).cursor == "v1:1105"
    # one net row per page for the one entity: 10 pages, then 2
    assert world.state(source).applied_seq == 12
    assert world.rows(CalendarSeries, source)[0].sequence == 1105


# ---------------------------------------------------------------------------------------------
# T1: leases and the owner-sync policy
# ---------------------------------------------------------------------------------------------
def claim(world, source, *, explicit=False):
    with world.maker.begin() as db:
        return sync.claim(db, source, explicit=explicit)


def force_state(world, source, **values):
    with world.maker.begin() as db:
        row = db.get(CalendarSyncState, source)
        for key, value in values.items():
            setattr(row, key, value)
        sync.touch(row, world.clock())


def test_an_unexpired_lease_is_a_no_op_for_every_caller_and_an_expired_one_is_claimable(world):
    source = world.source()
    taken = claim(world, source)
    assert isinstance(taken, sync.Claim) and taken.cursor is None
    for explicit in (False, True):
        assert claim(world, source, explicit=explicit) == sync.Skipped("lease_held")
    state = world.state(source)
    assert state.claim_token == taken.token  # never overridden
    world.clock.advance(seconds=121)
    again = claim(world, source)
    assert isinstance(again, sync.Claim) and again.token != taken.token


@pytest.mark.parametrize("status", ["failed", "blocked"])
def test_the_worker_skips_failed_and_blocked_but_an_explicit_call_does_not(world, status):
    source = world.source()
    extra = {"blocked_reason": "cursor_invalid"} if status == "blocked" else {"attempts": 5}
    force_state(world, source, status=status, **extra)
    assert claim(world, source) == sync.Skipped(status)
    assert isinstance(claim(world, source, explicit=True), sync.Claim)


def test_an_explicit_call_resets_attempts_of_a_failed_source_and_preserves_others(world):
    source = world.source()
    force_state(world, source, status="failed", attempts=5)
    assert isinstance(claim(world, source, explicit=True), sync.Claim)
    assert world.state(source).attempts == 0 and world.state(source).status == "failed"
    other = world.source()
    force_state(
        world,
        other,
        status="retry_wait",
        attempts=3,
        next_attempt_at=world.clock() + timedelta(minutes=5),
    )
    assert claim(world, other) == sync.Skipped("not_due")  # the worker honours backoff
    assert isinstance(claim(world, other, explicit=True), sync.Claim)
    assert world.state(other).attempts == 3  # preserved


def test_claiming_never_changes_the_stored_cursor_status_or_next_attempt(world):
    source = world.source()
    world.writer.append([series_item()])
    world.sync(source)
    before = world.state(source)
    claim(world, source, explicit=True)
    after = world.state(source)
    assert (after.cursor, after.status, after.next_attempt_at, after.applied_seq) == (
        before.cursor,
        before.status,
        before.next_attempt_at,
        before.applied_seq,
    )


def test_forgotten_foreign_or_unknown_sources_are_skipped(world):
    assert claim(world, UUID(int=1)) == sync.Skipped("missing")


# ---------------------------------------------------------------------------------------------
# T3: backoff schedule and terminal failure
# ---------------------------------------------------------------------------------------------
def test_the_backoff_schedule_and_the_fifth_failure(world):
    source = world.source()
    world.writer.add_fault("unavailable", times=99)
    expected = [30, 120, 600, 3600]
    for attempt, delay in enumerate(expected, start=1):
        result = world.sync(source)
        state = world.state(source)
        assert result["outcome"] == "retry_wait" and state.attempts == attempt
        assert identity.aware(state.next_attempt_at) == world.clock() + timedelta(seconds=delay)
        assert state.last_error_code == "provider_unavailable" and state.claim_token is None
        # not due yet: the worker skips; the clock then passes the schedule
        assert world.sync(source)["reason"] == "not_due"
        world.clock.advance(seconds=delay + 1)
    result = world.sync(source)
    state = world.state(source)
    assert (result["outcome"], state.status, state.attempts, state.next_attempt_at) == (
        "failed",
        "failed",
        5,
        None,
    )
    world.clock.advance(days=3)
    assert world.sync(source)["reason"] == "failed"  # the worker never retries a failed source


def test_an_explicit_sync_of_a_failed_source_resets_then_counts_and_success_resets_all(world):
    source = world.source()
    force_state(world, source, status="failed", attempts=5, last_error_code="provider_timeout")
    world.writer.add_fault("unavailable", times=1)
    result = world.sync(source, explicit=True)
    state = world.state(source)
    assert (result["outcome"], state.status, state.attempts) == ("retry_wait", "retry_wait", 1)
    clean = world.source(ref="clean")
    SyntheticWriter(world.directory / "clean.sqlite").append([series_item()])
    force_state(
        world,
        clean,
        status="retry_wait",
        attempts=3,
        last_error_code="provider_timeout",
        next_attempt_at=world.clock() + timedelta(hours=1),
    )
    assert world.sync(clean, explicit=True)["outcome"] == "ok"
    ok = world.state(clean)
    assert (ok.status, ok.attempts, ok.next_attempt_at, ok.last_error_code, ok.blocked_reason) == (
        "ok",
        0,
        None,
        None,
        None,
    )


def test_a_fetch_that_outlives_its_timeout_is_a_provider_timeout(world, monkeypatch):
    source = world.source()
    world.writer.add_fault("delay", arg="1.0")
    monkeypatch.setattr(settings, "calendar_fetch_timeout_seconds", 0.1)
    result = world.sync(source)
    state = world.state(source)
    assert result["outcome"] == "retry_wait" and state.last_error_code == "provider_timeout"


def test_the_timeout_must_be_shorter_than_the_lease(monkeypatch):
    from pydantic import ValidationError

    from app.config import Settings

    base = {"postgres_password": "synthetic-test-only-password-0123456789"}
    with pytest.raises(ValidationError):
        Settings(**base, calendar_lease_seconds=10, calendar_fetch_timeout_seconds=10)
    with pytest.raises(ValidationError):
        Settings(**base, calendar_lease_seconds=0)
    assert Settings(**base, calendar_lease_seconds=1, calendar_fetch_timeout_seconds=0.5)


# ---------------------------------------------------------------------------------------------
# Blocking: cursor errors, refused pages, explicit retry and resync
# ---------------------------------------------------------------------------------------------
def test_an_unknown_cursor_blocks_and_only_an_explicit_resync_restarts(world):
    source = world.source()
    world.writer.append([series_item()])
    world.sync(source)
    force_state(world, source, cursor="v1:99")
    assert world.sync(source)["outcome"] == "blocked"
    state = world.state(source)
    assert (state.status, state.blocked_reason, state.cursor) == (
        "blocked",
        "cursor_invalid",
        "v1:99",
    )
    assert (
        state.blocked_detail["code"] == "cursor_invalid"
        and state.blocked_detail["entity"] == "page"
    )
    assert world.sync(source)["reason"] == "blocked"  # the worker does not retry
    assert world.sync(source, explicit=True)["outcome"] == "blocked"  # same code, no side effects
    result = world.sync(source, explicit=True, resync=True)
    state = world.state(source)
    assert result["outcome"] == "ok" and (state.cursor, state.status, state.blocked_reason) == (
        "v1:1",
        "ok",
        None,
    )


def test_an_expired_cursor_blocks_with_cursor_expired(world):
    source = world.source()
    ids = world.writer.append([series_item(sequence=n) for n in (1, 2, 3)])
    world.sync(source)
    world.writer.append([series_item(sequence=4), series_item(sequence=5)])
    world.writer.truncate_before(ids[-1] + 2)  # history up to change 4 is gone
    assert world.sync(source)["reason"] == "cursor_expired"
    assert world.state(source).blocked_reason == "cursor_expired"


def test_a_refused_page_changes_nothing_and_a_correction_then_applies(world):
    source = world.source()
    world.writer.append([series_item(), override_item()])
    world.sync(source)
    before = world.fingerprint(source)
    bad = world.writer.append([override_item("ghost", 1)], force=True)
    result = world.sync(source)
    assert (result["outcome"], result["reason"]) == ("blocked", "override_orphan")
    assert world.fingerprint(source) == before  # atomic: data, cursor and applied_seq unchanged
    state = world.state(source)
    detail = state.blocked_detail
    assert detail == {
        "code": "override_orphan",
        "entity": "override",
        "item_index": 0,
        "sequence": 1,
        "uid_digest": codes.uid_digest(source, "ghost"),
        "recurrence_digest": None,
    }
    assert "ghost" not in str(detail) and RID not in str(detail)
    # the provider corrects its side; the explicit retry applies and advances the cursor
    world.writer.replace_from(bad[0], [series_item("ghost", 1), override_item("ghost", 1)])
    assert world.sync(source)["reason"] == "blocked"
    assert world.sync(source, explicit=True)["outcome"] == "ok"
    state = world.state(source)
    assert (state.status, state.blocked_reason, state.blocked_detail) == ("ok", None, None)
    assert world.state(source).applied_seq == 4


def test_each_grammar_failure_is_a_stable_blocked_code_with_no_partial_apply(world):
    source = world.source()
    world.writer.append([series_item("good"), series_item("bad", rrule="FREQ=SECONDLY")])
    result = world.sync(source)
    assert result["reason"] == "freq_unsupported"
    assert world.rows(CalendarSeries, source) == [] and world.state(source).applied_seq == 0
    detail = world.state(source).blocked_detail
    assert (detail["entity"], detail["item_index"], detail["sequence"]) == ("series", 1, 1)
    assert detail["recurrence_digest"] is None


def test_a_malformed_provider_item_blocks_without_echoing_content(world):
    source = world.source()
    world.writer.append([{**series_item(), "raw_body": "{not json"}])
    assert world.sync(source)["reason"] == "item_malformed"
    assert world.state(source).blocked_detail["code"] == "item_malformed"


def test_cursor_that_does_not_progress_blocks(world, monkeypatch):
    source = world.source()
    stub = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendar_fetch_stub_child.py")
    # a (scripted) fetch child that answers "same cursor, more to come" forever
    monkeypatch.setattr(sync, "CHILD_ARGV", [sys.executable, "-I", "-S", stub, "same_cursor"])
    assert world.sync(source)["reason"] == "cursor_no_progress"
    assert world.state(source).blocked_reason == "cursor_no_progress"


# ---------------------------------------------------------------------------------------------
# Series deletion, cascade and revival through the database layer
# ---------------------------------------------------------------------------------------------
def test_a_series_delete_cascades_in_one_transaction_with_one_change_row(world):
    source = world.source()
    world.writer.append(
        [series_item(), override_item(), override_item(rid="TZID=Europe/Paris:20260329T090000")]
    )
    world.sync(source)
    world.writer.append([series_item(sequence=2, op="delete")])
    world.clock.advance(seconds=1)
    world.sync(source)
    series = world.rows(CalendarSeries, source)[0]
    assert (series.state, series.sequence, series.kind, series.title) == ("deleted", 2, None, None)
    assert series.deleted_at is not None
    overrides = world.rows(CalendarOverride, source)
    assert {(o.state, o.deleted_by_cascade, o.sequence, o.status) for o in overrides} == {
        ("deleted", True, 1, None)
    }
    last = max(world.rows(CalendarChange, source), key=lambda r: r.seq)
    assert (last.entity, last.operation, last.cascade_count, last.content_hash) == (
        "series",
        "delete",
        2,
        codes.TOMBSTONE_HASH,
    )
    assert world.state(source).applied_seq == 4  # 3 first page rows + exactly one for the delete


def test_delete_then_higher_upsert_in_one_page_is_a_revive_and_old_overrides_stay_deleted(world):
    source = world.source()
    world.writer.append([series_item(), override_item()])
    world.sync(source)
    series_id = world.rows(CalendarSeries, source)[0].id
    world.writer.append(
        [series_item(sequence=2, op="delete"), series_item(sequence=3, title="Back")]
    )
    world.clock.advance(seconds=1)
    world.sync(source)
    series = world.rows(CalendarSeries, source)[0]
    assert (series.id, series.state, series.sequence, series.title, series.deleted_at) == (
        series_id,
        "active",
        3,
        "Back",
        None,
    )
    assert series.revision == 3  # created 1, then two updates: delete (pass), revive
    override = world.rows(CalendarOverride, source)[0]
    assert (override.state, override.deleted_by_cascade, override.sequence) == ("deleted", True, 1)
    change = max(world.rows(CalendarChange, source), key=lambda r: r.seq)
    assert (change.operation, change.cascade_count, change.sequence) == ("revive", 1, 3)


def test_a_resent_override_revives_the_same_row_only_above_its_floor(world):
    source = world.source()
    world.writer.append([series_item(), override_item()])
    world.sync(source)
    row_id = world.rows(CalendarOverride, source)[0].id
    world.writer.append([series_item(sequence=2, op="delete"), series_item(sequence=3)])
    world.sync(source)
    world.writer.append([override_item(sequence=1)])
    assert world.sync(source)["reason"] == "sequence_conflict"  # equal to the cascade floor
    world.writer.replace_from(
        max(c for (c,) in world_changes(world)), [override_item(sequence=4, status="tentative")]
    )
    world.sync(source, explicit=True)
    override = world.rows(CalendarOverride, source)[0]
    assert (override.id, override.state, override.sequence, override.status) == (
        row_id,
        "active",
        4,
        "tentative",
    )
    assert override.deleted_by_cascade is False and override.deleted_at is None


def world_changes(world):
    import sqlite3

    connection = sqlite3.connect(world.directory / "household.sqlite")
    try:
        return connection.execute("SELECT change_id FROM changes").fetchall()
    finally:
        connection.close()


def test_a_floor_raising_delete_keeps_the_original_deleted_at(world):
    source = world.source()
    world.writer.append([series_item(sequence=1, op="delete")])  # unknown-entity tombstone
    world.sync(source)
    first = world.rows(CalendarSeries, source)[0]
    assert (first.state, first.sequence) == ("deleted", 1) and first.deleted_at is not None
    world.clock.advance(minutes=10)
    world.writer.append([series_item(sequence=5, op="delete")])
    world.sync(source)
    second = world.rows(CalendarSeries, source)[0]
    assert (second.sequence, second.deleted_at) == (5, first.deleted_at)
    world.writer.append([series_item(sequence=3)])  # stale: never resurrects
    result = world.sync(source)
    assert result["counters"] == {"ignored_stale": 1}
    assert world.rows(CalendarSeries, source)[0].state == "deleted"


def test_overrides_for_a_deleted_series_are_superseded_and_counted(world):
    source = world.source()
    world.writer.append([series_item(), series_item(sequence=2, op="delete")])
    world.sync(source)
    world.writer.append([override_item(sequence=9)], force=True)
    result = world.sync(source)
    assert result["counters"] == {"superseded_by_delete": 1}
    assert world.rows(CalendarOverride, source) == []


# ---------------------------------------------------------------------------------------------
# Crash points, in process (real process exits run against PostgreSQL)
# ---------------------------------------------------------------------------------------------
def test_p1_a_claim_without_a_fetch_blocks_for_the_lease_then_recovers(world):
    source = world.source()
    world.writer.append([series_item()])
    claim(world, source)  # P1: crash after T1
    assert world.sync(source)["reason"] == "lease_held"
    assert world.fingerprint(source)[2:4] == ([], None)
    world.clock.advance(seconds=121)
    assert world.sync(source)["outcome"] == "ok"


def test_p2_a_fetched_page_that_is_never_applied_is_refetched_after_the_lease(world):
    source = world.source()
    world.writer.append([series_item()])
    taken = claim(world, source)
    provider = sync.default_factory(taken.ref)
    provider.changes(taken.cursor, 100)  # P2: the page is lost
    world.clock.advance(seconds=121)
    assert world.sync(source)["changes"] == 1


def test_p3_a_failure_inside_the_apply_transaction_rolls_everything_back(world, monkeypatch):
    source = world.source()
    world.writer.append([series_item(), override_item()])
    original = sync.write_override

    def explode(*args, **kwargs):
        raise RuntimeError("crash inside T2")

    monkeypatch.setattr(sync, "write_override", explode)
    with pytest.raises(RuntimeError):
        world.sync(source)
    monkeypatch.setattr(sync, "write_override", original)
    assert world.fingerprint(source)[2:] == ([], None, 0)  # series row, change rows: rolled back
    assert world.rows(CalendarSeries, source) == []
    assert world.state(source).claim_token is not None  # the claim itself committed in T1
    world.clock.advance(seconds=121)
    assert world.sync(source)["changes"] == 2
    assert world.state(source).cursor == "v1:2"


def test_p4_a_committed_page_is_never_applied_twice(world):
    source = world.source()
    world.writer.append([series_item(), override_item()])
    world.sync(source)
    before = world.fingerprint(source)
    stale_cursor = None
    with world.maker.begin() as db:
        taken = sync.claim(db, source, explicit=True)
    page = sync.default_factory(taken.ref).changes(stale_cursor, 100)
    with world.maker.begin() as db:
        # the stored cursor moved since the claim was recorded: compare-and-swap refuses
        forged = sync.Claim(taken.source_id, taken.token, "v1:0", taken.ref, True)
        assert sync.apply_page(db, forged, page, None) is None
    with world.maker.begin() as db:
        applied = sync.apply_page(db, taken, page, None)
    assert applied.changes == 0 and applied.counters == {"replayed": 2}
    assert world.fingerprint(source) == before


def test_a_lost_claim_applies_nothing(world):
    source = world.source()
    world.writer.append([series_item()])
    taken = claim(world, source)
    world.clock.advance(seconds=121)
    claim(world, source)  # a newer claim replaces ours
    page = sync.default_factory(taken.ref).changes(None, 100)
    with world.maker.begin() as db:
        assert sync.apply_page(db, taken, page, None) is None
        assert sync.fail_retry(db, taken, "provider_timeout") is None
    assert world.rows(CalendarSeries, source) == []


# ---------------------------------------------------------------------------------------------
# Worker pass
# ---------------------------------------------------------------------------------------------
def test_a_worker_pass_checks_due_sources_only_and_is_bounded(world):
    due, waiting = world.source(), world.source(ref="other")
    SyntheticWriter(world.directory / "other.sqlite").append([series_item()])
    world.writer.append([series_item()])
    force_state(
        world, waiting, status="retry_wait", next_attempt_at=world.clock() + timedelta(hours=1)
    )
    result = sync.run_pass(world.maker)
    assert (result["checked"], result["ok"]) == (1, 1)
    assert world.state(due).status == "ok" and world.state(waiting).status == "retry_wait"
    with pytest.raises(ValueError, match="bounded"):
        sync.run_pass(world.maker, limit=101)


def test_the_worker_is_disabled_outside_development_and_test(monkeypatch, world):
    monkeypatch.setattr(settings, "env", "production")
    assert not sync.enabled()
    source = world.source()
    assert world.sync(source)["outcome"] == "retry_wait"  # no provider is ever constructed


# ---------------------------------------------------------------------------------------------
# Forgetting, export, exclusivity and link declaration through the application
# ---------------------------------------------------------------------------------------------
def linked_source(auth_client, auth_store, world):
    headers = signin(auth_client)
    row = create(auth_client, headers).json()
    token = auth_client.cookies.get(identity.COOKIE)
    body = SimpleNamespace(scope="household_shared", provider_ref="household")
    with auth_store.begin() as db:
        result = sync.declare(db, token, headers["X-CSRF-Token"], UUID(row["id"]), body)
    return headers, row, token, result


def test_declaring_a_link_needs_the_owner_an_unconfigured_source_and_a_known_fixture(
    auth_client, auth_store, world
):
    headers, row, token, result = linked_source(auth_client, auth_store, world)
    assert result.status == 200 and result.payload["provider"]["status"] == "never"
    csrf = headers["X-CSRF-Token"]
    body = SimpleNamespace(scope="household_shared", provider_ref="household")
    with auth_store.begin() as db:
        assert sync.declare(db, token, csrf, UUID(row["id"]), body).status == 409  # already linked
    second = create(auth_client, headers).json()
    with auth_store.begin() as db:
        missing = SimpleNamespace(scope="household_shared", provider_ref="absent")
        assert sync.declare(db, token, csrf, UUID(second["id"]), missing).status == 422
        assert sync.declare(db, token, csrf, UUID(int=5), body).status == 404
    imported = call(
        auth_client,
        headers,
        second,
        "unavailable",
        reason="offline",
    ).json()
    with auth_store.begin() as db:
        assert sync.declare(db, token, csrf, UUID(imported["id"]), body).status == 409
    other = signin(auth_client, "bob")
    with auth_store.begin() as db:
        denied = sync.declare(
            db,
            auth_client.cookies.get(identity.COOKIE),
            other["X-CSRF-Token"],
            UUID(row["id"]),
            body,
        )
        assert denied.status in {403, 404}


def test_declaring_is_unavailable_outside_development_and_test(
    auth_client, auth_store, world, monkeypatch
):
    headers = signin(auth_client)
    row = create(auth_client, headers).json()
    monkeypatch.setattr(settings, "env", "production")
    body = SimpleNamespace(scope="household_shared", provider_ref="household")
    with auth_store.begin() as db:
        result = sync.declare(
            db,
            auth_client.cookies.get(identity.COOKIE),
            headers["X-CSRF-Token"],
            UUID(row["id"]),
            body,
        )
    assert result.status == 404


def test_manual_import_and_unavailable_are_refused_for_a_provider_source(
    auth_client, auth_store, world
):
    headers, row, _token, _ = linked_source(auth_client, auth_store, world)
    from test_calendars import window

    for operation, extra in (
        ("import", {"window": window()}),
        ("unavailable", {"reason": "offline"}),
    ):
        refused = call(auth_client, headers, row, operation, **extra)
        assert refused.status_code == 409
    assert call(auth_client, headers, row, "read").status_code == 200


@pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning")
def test_forgetting_a_provider_source_scrubs_everything_in_the_same_transaction(
    auth_client, auth_store, world
):
    headers, row, _token, _ = linked_source(auth_client, auth_store, world)
    source = UUID(row["id"])
    world.writer.append([series_item(), override_item()])
    assert world.sync(source)["outcome"] == "ok"
    exported = call(auth_client, headers, row, "export", acknowledge_copy_limits=True).json()
    provider = exported["provider"]
    assert provider["series"][0]["title"] == "Synthetic" and provider["series"][0]["overrides"]
    assert provider["sync"]["status"] == "ok" and "cursor" not in provider["sync"]
    before = {
        r.id: r.revision
        for r in world.rows(CalendarSeries, source) + world.rows(CalendarOverride, source)
    }
    forgotten = call(auth_client, headers, row, "forget")
    assert forgotten.status_code == 200 and forgotten.json()["state"] == "forgotten"
    # Each row's own revision rises by exactly one (a shared expression once pointed at the series).
    after_rows = world.rows(CalendarSeries, source) + world.rows(CalendarOverride, source)
    assert {r.id: r.revision for r in after_rows} == {k: v + 1 for k, v in before.items()}
    series = world.rows(CalendarSeries, source)[0]
    assert (series.state, series.uid, series.title, series.rule, series.exdates) == (
        "forgotten",
        None,
        None,
        None,
        None,
    )
    override = world.rows(CalendarOverride, source)[0]
    assert (override.state, override.status, override.deleted_by_cascade) == (
        "forgotten",
        None,
        False,
    )
    assert all(c.snapshot is None for c in world.rows(CalendarChange, source))
    assert len(world.rows(CalendarChange, source)) == 2  # counts and hashes are retained
    assert world.rows(CalendarProviderLink, source)[0].provider_ref is None
    state = world.state(source)
    assert (state.status, state.blocked_reason, state.cursor, state.claim_token) == (
        "blocked",
        "source_forgotten",
        None,
        None,
    )
    assert state.applied_seq == 2
    assert world.sync(source)["reason"] == "forgotten"
    after = call(auth_client, headers, row, "export", acknowledge_copy_limits=True).json()
    assert "provider" not in after
    assert call(auth_client, headers, row, "read").status_code == 410


def test_a_page_in_flight_when_the_source_is_forgotten_applies_nothing(
    auth_client, auth_store, world
):
    headers, row, _token, _ = linked_source(auth_client, auth_store, world)
    source = UUID(row["id"])
    world.writer.append([series_item()])
    taken = claim(world, source)
    page = sync.default_factory(taken.ref).changes(None, 100)
    assert call(auth_client, headers, row, "forget").status_code == 200
    with world.maker.begin() as db:
        assert sync.apply_page(db, taken, page, None) is None
        assert sync.fail_retry(db, taken, "provider_timeout") is None
    assert world.rows(CalendarSeries, source) == []  # the page was never applied
    assert world.state(source).blocked_reason == "source_forgotten"


def test_export_of_an_ordinary_source_has_no_provider_block(auth_client):
    headers = signin(auth_client)
    row = create(auth_client, headers).json()
    exported = call(auth_client, headers, row, "export", acknowledge_copy_limits=True).json()
    assert "provider" not in exported


def test_the_sync_modules_do_not_touch_the_network():
    from pathlib import Path

    for name in ("calendar_sync.py", "calendar_plan.py"):
        source = (Path(__file__).resolve().parents[1] / "app" / name).read_text()
        for forbidden in ("socket", "urllib", "httpx", "requests", "http.client", "smtplib"):
            assert f"import {forbidden}" not in source and f"from {forbidden}" not in source
    assert planner.PageBlocked and func and codes.PAGES_PER_PASS == 10
