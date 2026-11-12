"""Calendar sync on real PostgreSQL as the restricted runtime role.

The page application, the cascade order, the forgetting scrub and the crash points run against
the triggers of migration 0035 (which SQLite does not have). Crash tests exit a real subprocess
(``os._exit``) with a transaction open, then recover from a fresh process and a shared fixture.
"""

import itertools
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from calendar_synthetic_writer import SyntheticWriter
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker
from test_calendar_sync import RID_NEXT, Clock, World, override_item, series_item
from test_calendars import call, create

from app import calendar_codes as codes
from app import calendar_sync as sync
from app import identity
from app.calendar_provider import SyntheticProvider
from app.config import settings
from app.models import (
    CalendarChange,
    CalendarOverride,
    CalendarSeries,
    CalendarSource,
    CalendarSyncState,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def pg(scenario, runtime_engine, tmp_path, monkeypatch):
    client, headers, _record, admin, user_id = scenario
    clock = Clock()
    monkeypatch.setattr(sync, "clock", clock)
    monkeypatch.setattr(settings, "calendar_synthetic_directory", tmp_path)
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    world = World(maker, tmp_path, SyntheticWriter(tmp_path / "household.sqlite"), clock)
    world.client, world.headers, world.admin, world.user = client, headers, admin, user_id
    world.token = client.cookies.get(identity.COOKIE)
    yield world
    retire(world)


def retire(world):
    """Forget every source this fixture's user still has, through the API (best effort).

    Committed synthetic rows outlive a test in the shared database, and the briefing tests read the
    first 25 active sources of the shared scope, so leaving many active sources behind would crowd
    them out. Forgetting is the real, supported way to retire a source.
    """
    with world.admin() as db:
        rows = list(
            db.execute(
                select(CalendarSource.id, CalendarSource.scope_key, CalendarSource.revision).where(
                    CalendarSource.owner_id == world.user, CalendarSource.state == "active"
                )
            )
        )
    for identifier, scope, revision in rows:
        row = {"id": str(identifier), "scope": scope, "revision": revision}
        call(world.client, world.headers, row, "forget")


def api_source(world):
    """A source created through the API and linked through the application, as in production."""
    row = create(world.client, world.headers).json()
    from types import SimpleNamespace

    body = SimpleNamespace(scope="household_shared", provider_ref="household")
    with world.maker.begin() as db:
        result = sync.declare(db, world.token, world.headers["X-CSRF-Token"], UUID(row["id"]), body)
    assert result.status == 200
    return row, UUID(row["id"])


def test_a_page_with_overrides_applies_under_every_database_guard(pg):
    _row, source = api_source(pg)
    pg.writer.append([series_item(), override_item(), series_item("s2", 1)])
    result = pg.sync(source)
    assert (result["outcome"], result["changes"]) == ("ok", 3)
    assert [r.seq for r in sorted(pg.rows(CalendarChange, source), key=lambda r: r.seq)] == [
        1,
        2,
        3,
    ]
    assert pg.state(source).applied_seq == 3


def test_series_delete_writes_the_series_before_the_cascade_in_one_transaction(pg):
    _row, source = api_source(pg)
    pg.writer.append(
        [series_item(), override_item(), override_item(rid="TZID=Europe/Paris:20260329T090000")]
    )
    pg.sync(source)
    pg.writer.append([series_item(sequence=2, op="delete")])
    pg.clock.advance(seconds=1)
    assert pg.sync(source)["outcome"] == "ok"
    rows = pg.rows(CalendarOverride, source)
    assert {(r.state, r.deleted_by_cascade, r.sequence) for r in rows} == {("deleted", True, 1)}
    assert pg.rows(CalendarSeries, source)[0].state == "deleted"


def test_delete_then_revive_in_one_page_and_a_resend_above_the_floor(pg):
    _row, source = api_source(pg)
    pg.writer.append([series_item(), override_item()])
    pg.sync(source)
    row_id = pg.rows(CalendarOverride, source)[0].id
    pg.writer.append(
        [
            series_item(sequence=2, op="delete"),
            series_item(sequence=3, title="Back"),
            override_item(sequence=4, status="tentative"),
        ]
    )
    pg.clock.advance(seconds=1)
    assert pg.sync(source)["outcome"] == "ok"
    series = pg.rows(CalendarSeries, source)[0]
    override = pg.rows(CalendarOverride, source)[0]
    assert (series.state, series.sequence, series.revision) == ("active", 3, 3)
    assert (override.id, override.state, override.sequence, override.deleted_by_cascade) == (
        row_id,
        "active",
        4,
        False,
    )
    changes = {c.entity: c for c in pg.rows(CalendarChange, source) if c.seq > 2}
    assert (changes["series"].operation, changes["series"].cascade_count) == ("revive", 1)
    assert changes["override"].operation == "upsert"


def test_an_override_tombstone_is_created_under_a_series_created_in_the_same_page(pg):
    _row, source = api_source(pg)
    # listed before its series inside one page: order within a page is irrelevant
    pg.writer.append([override_item(sequence=3, op="delete"), series_item()], force=True)
    assert pg.sync(source)["outcome"] == "ok"
    override = pg.rows(CalendarOverride, source)[0]
    assert (override.state, override.sequence, override.deleted_by_cascade) == ("deleted", 3, False)
    assert override.deleted_at is not None


def test_floor_raise_keeps_deleted_at_and_stale_redelivery_never_resurrects(pg):
    _row, source = api_source(pg)
    pg.writer.append([series_item(sequence=1, op="delete")])
    pg.sync(source)
    first = pg.rows(CalendarSeries, source)[0]
    pg.clock.advance(minutes=5)
    pg.writer.append([series_item(sequence=7, op="delete"), series_item(sequence=2)])
    pg.sync(source)
    second = pg.rows(CalendarSeries, source)[0]
    assert (second.sequence, second.deleted_at) == (7, first.deleted_at)
    pg.writer.append([series_item(sequence=7)])
    assert pg.sync(source)["reason"] == "sequence_conflict"


def test_a_refused_page_leaves_every_table_exactly_as_it_was(pg):
    _row, source = api_source(pg)
    pg.writer.append([series_item(), override_item()])
    pg.sync(source)
    before = pg.fingerprint(source)
    pg.writer.append([series_item("s9"), override_item("ghost", 1)], force=True)
    result = pg.sync(source)
    assert result["reason"] == "override_orphan"
    assert pg.fingerprint(source) == before
    assert pg.state(source).blocked_detail["code"] == "override_orphan"


def test_the_last_success_stamp_is_strictly_monotonic_on_the_database_clock(pg):
    _row, source = api_source(pg)
    pg.writer.append([series_item()])
    stamps = []
    for _ in range(4):
        pg.sync(source)
        stamps.append(pg.state(source).last_success_at)
    assert all(a < b for a, b in itertools.pairwise(stamps))


def test_forgetting_through_the_api_scrubs_every_table_and_the_commit_succeeds(pg):
    row, source = api_source(pg)
    pg.writer.append([series_item(), override_item()])
    pg.sync(source)
    forgotten = call(pg.client, pg.headers, row, "forget")
    assert forgotten.status_code == 200
    with pg.admin() as db:
        assert (
            db.scalar(select(CalendarSeries.state).where(CalendarSeries.source_id == source))
            == "forgotten"
        )
        assert not db.scalar(
            text(
                "SELECT count(*) FROM calendar_changes WHERE source_id=:s AND snapshot IS NOT NULL"
            ),
            {"s": source},
        )
        state = db.get(CalendarSyncState, source)
        assert (state.status, state.blocked_reason, state.cursor) == (
            "blocked",
            "source_forgotten",
            None,
        )
    assert pg.sync(source)["reason"] == "forgotten"


def test_forgetting_while_a_page_is_in_flight_applies_nothing(pg):
    row, source = api_source(pg)
    pg.writer.append([series_item()])
    with pg.maker.begin() as db:
        taken = sync.claim(db, source)
    page = sync.default_factory(taken.ref).changes(None, 100)
    assert call(pg.client, pg.headers, row, "forget").status_code == 200
    with pg.maker.begin() as db:
        assert sync.apply_page(db, taken, page, None) is None
    assert pg.rows(CalendarSeries, source) == []


# ---------------------------------------------------------------------------------------------
# Real process exits at every crash point of section 7.4
# ---------------------------------------------------------------------------------------------
CRASH = """
import os, sys
from datetime import datetime, UTC
from uuid import UUID
from app import calendar_sync as sync
from app.db import SessionLocal

point, source = sys.argv[1], UUID(sys.argv[2])

def die():
    os._exit(31)

if point == "P0":
    die()
if point in {"P1", "P2", "P3"}:
    with SessionLocal.begin() as db:
        taken = sync.claim(db, source)
    if point == "P1":
        die()
    page = sync.default_factory(taken.ref).changes(taken.cursor, 100)
    if point == "P2":
        die()
    db = SessionLocal()
    db.begin()
    assert sync.apply_page(db, taken, page, taken.cursor) is not None
    die()  # inside T2: everything flushed, nothing committed
if point == "P4":
    assert sync.sync_source(SessionLocal, source)["outcome"] == "ok"
    die()
if point == "P5":
    calls = {"n": 0}
    original = sync.claim
    def counting(db, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            die()  # after the first page's T2 commit, before the next page's T1
        return original(db, *args, **kwargs)
    sync.claim = counting
    sync.sync_source(SessionLocal, source)
if point == "P6":
    original = sync.fail_retry
    def failing(db, taken, code):
        original(db, taken, code)
        die()  # inside T3, uncommitted
    sync.fail_retry = failing
    sync.sync_source(SessionLocal, source)
"""


def crash(pg, point, source):
    env = dict(
        os.environ,
        BUTLER_POSTGRES_USER="butler_runtime",
        BUTLER_POSTGRES_PASSWORD=os.environ.get("BUTLER_RUNTIME_PASSWORD_FOR_TESTS", "")
        or __import__("conftest").RUNTIME_PASSWORD,
        BUTLER_CALENDAR_SYNTHETIC_DIRECTORY=str(pg.directory),
    )
    done = subprocess.run(
        [sys.executable, "-c", CRASH, point, str(source)],
        env=env,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 31, (point, done.stdout, done.stderr[-2000:])
    # The subprocess stamped its claim with the real clock. The fixture clock started earlier, so
    # without this a lease of 120 s could still look unexpired after "lease + 1 s" (start-up of the
    # subprocess takes seconds): that was an intermittent failure. Never move the clock backwards.
    pg.clock.value = max(pg.clock.value, identity.now_utc())


def invariants(pg, source):
    state = pg.state(source)
    seqs = sorted(r.seq for r in pg.rows(CalendarChange, source))
    assert seqs == list(range(1, len(seqs) + 1))  # gapless, no duplicate change rows
    assert state.applied_seq == len(seqs)  # the cursor is never ahead of applied changes
    keys = [
        (r.entity, r.sequence, r.content_hash, r.series_id, r.override_id)
        for r in pg.rows(CalendarChange, source)
    ]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("point", ["P0", "P1", "P2", "P3"])
def test_a_process_that_dies_before_commit_changes_nothing_and_a_fresh_process_recovers(pg, point):
    _row, source = api_source(pg)
    pg.writer.append([series_item(), override_item()])
    crash(pg, point, source)
    assert pg.rows(CalendarSeries, source) == [] and pg.state(source).cursor is None
    invariants(pg, source)
    held = pg.state(source).claim_token is not None
    assert held == (point != "P0")
    if held:
        assert pg.sync(source)["reason"] == "lease_held"  # the lease protects the in-flight claim
        pg.clock.advance(seconds=settings.calendar_lease_seconds + 1)
    assert pg.sync(source)["outcome"] == "ok"
    invariants(pg, source)
    assert pg.state(source).cursor == "v1:2" and len(pg.rows(CalendarSeries, source)) == 1


def test_p4_a_process_that_dies_after_commit_leaves_the_page_applied_once(pg):
    _row, source = api_source(pg)
    pg.writer.append([series_item(), override_item()])
    crash(pg, "P4", source)
    assert pg.state(source).cursor == "v1:2" and pg.state(source).claim_token is None
    invariants(pg, source)
    before = pg.fingerprint(source)
    result = pg.sync(source)
    assert result["changes"] == 0 and pg.fingerprint(source)[:3] == before[:3]
    resync = pg.sync(source, explicit=True, resync=True)
    assert resync["counters"] == {"replayed": 2} and pg.fingerprint(source)[:3] == before[:3]


def test_p5_a_death_between_pages_leaves_no_lease_and_resumes_from_the_committed_cursor(pg):
    _row, source = api_source(pg)
    pg.writer.append([series_item(sequence=n, title=f"v{n}") for n in range(1, 151)])
    crash(pg, "P5", source)
    state = pg.state(source)
    assert state.cursor == "v1:100" and state.claim_token is None  # no lease to wait for
    invariants(pg, source)
    assert pg.sync(source)["outcome"] == "ok" and pg.state(source).cursor == "v1:150"
    assert pg.rows(CalendarSeries, source)[0].sequence == 150


def test_p6_a_death_inside_the_failure_transaction_rolls_it_back(pg):
    _row, source = api_source(pg)
    pg.writer.add_fault("unavailable", times=99)
    crash(pg, "P6", source)
    state = pg.state(source)
    assert (state.attempts, state.status) == (0, "never") and state.claim_token is not None
    pg.clock.advance(seconds=settings.calendar_lease_seconds + 1)
    assert pg.sync(source)["outcome"] == "retry_wait" and pg.state(source).attempts == 1


def test_a_process_restart_never_reuses_or_extends_a_lease(pg):
    _row, source = api_source(pg)
    pg.writer.append([series_item()])
    crash(pg, "P1", source)
    token = pg.state(source).claim_token
    assert pg.sync(source, explicit=True)["reason"] == "lease_held"
    assert pg.state(source).claim_token == token
    pg.clock.advance(seconds=codes.LEASE_SECONDS + 1)
    assert pg.sync(source)["outcome"] == "ok"


def test_backoff_and_failed_state_survive_on_the_database(pg):
    _row, source = api_source(pg)
    pg.writer.add_fault("timeout", times=99)
    for delay in (30, 120, 600, 3600):
        assert pg.sync(source)["outcome"] == "retry_wait"
        pg.clock.advance(seconds=delay + 1)
    assert pg.sync(source)["outcome"] == "failed"
    state = pg.state(source)
    assert (state.attempts, state.next_attempt_at, state.last_error_code) == (
        5,
        None,
        "provider_timeout",
    )
    assert pg.sync(source)["reason"] == "failed"


def test_a_fetch_that_outlives_its_timeout_is_killed_and_the_lease_released(pg, monkeypatch):
    _row, source = api_source(pg)
    pg.writer.append([series_item()])
    pg.writer.add_fault("delay", arg="60")  # far beyond the timeout: the child must be killed
    monkeypatch.setattr(settings, "calendar_fetch_timeout_seconds", 0.5)
    started = time.monotonic()
    result = pg.sync(source, explicit=True)
    assert time.monotonic() - started < 15
    assert result["outcome"] == "retry_wait"
    state = pg.state(source)
    assert (state.status, state.attempts, state.last_error_code) == (
        "retry_wait",
        1,
        "provider_timeout",
    )
    assert state.claim_token is None and state.claim_expires_at is None and state.applied_seq == 0
    with pytest.raises(ChildProcessError):  # no fetch child is left, not even a zombie
        os.waitpid(-1, os.WNOHANG)
    # the lease is free at once: an explicit sync may run again, and after recovery it applies once
    pg.writer.clear_faults()
    assert pg.sync(source, explicit=True)["outcome"] == "ok"
    assert [r.seq for r in pg.rows(CalendarChange, source)] == [1]
    invariants(pg, source)


def test_briefing_v2_and_the_owner_sync_route_run_on_the_restricted_role(pg):
    _row, source = api_source(pg)
    pg.writer.append([series_item(rrule="FREQ=DAILY;COUNT=10"), override_item(rid=RID_NEXT)])
    base = {"scope": "household_shared"}
    synced = pg.client.post(f"/api/v1/calendars/{source}/sync", headers=pg.headers, json=base)
    assert synced.status_code == 200, synced.text
    assert synced.json()["sync"]["outcome"] == "ok" and "cursor" not in synced.text
    status = pg.client.post(
        f"/api/v1/calendars/{source}/sync-status", headers=pg.headers, json=base
    )
    assert status.status_code == 200 and status.json()["provider"]["applied_seq"] == 2
    response = pg.client.post(
        "/api/v1/calendars/briefing",
        headers=pg.headers,
        json={**base, "day": "2026-03-15", "timezone": "Europe/Paris", "horizon_days": 3},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    entry = next(c for c in body["calendars"] if c["id"] == str(source))
    assert (entry["mode"], entry["source_state"]) == ("provider", "available")
    mine = [e for e in body["events"] if e["source_id"] == str(source)]
    assert [e["days"] for e in mine] == [["2026-03-15"], ["2026-03-17"]]
    assert body["cancelled_count"] >= 1 and body["limits"]["events"]["truncated"] is False
    # a foreign or unknown source is the same 404 as a forgotten one
    unknown = pg.client.post(f"/api/v1/calendars/{UUID(int=3)}/sync", headers=pg.headers, json=base)
    assert unknown.status_code == 404


# ---------------------------------------------------------------------------------------------
# Real concurrency: threads against the restricted role, actual row waits (no mocks of locking)
# ---------------------------------------------------------------------------------------------
def test_two_concurrent_explicit_syncs_apply_the_page_exactly_once(pg):
    _row, source = api_source(pg)
    pg.writer.append([series_item(), override_item()])
    # the provider call takes ~3 s, outside any database transaction, while the lease is held
    pg.writer.add_fault("delay", arg="3")
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(pg.sync, source, explicit=True)
        give_up = time.monotonic() + 20
        while pg.state(source).claim_token is None:  # the claim is committed before the fetch
            assert time.monotonic() < give_up, "the first sync never took the lease"
            time.sleep(0.02)
        # the lease is held while the provider is being read: every other claimant is a no-op
        second = pg.sync(source, explicit=True)
        assert (second["outcome"], second["reason"]) == ("skipped", "lease_held")
        assert first.result(60)["outcome"] == "ok"
    assert [r.seq for r in sorted(pg.rows(CalendarChange, source), key=lambda r: r.seq)] == [1, 2]
    invariants(pg, source)


def test_concurrent_passes_and_owner_syncs_never_duplicate_or_skip_a_change(pg):
    _row, source = api_source(pg)
    for number in range(6):
        pg.writer.append([series_item(uid=f"c{number}", sequence=1)])
    barrier = threading.Barrier(4)

    def worker(kind):
        barrier.wait(20)
        if kind == "pass":
            return sync.run_pass(pg.maker)
        return pg.sync(source, explicit=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(worker, ["pass", "sync", "pass", "sync"]))
    assert results
    for _ in range(2):  # whatever the interleaving, a final sync converges
        pg.clock.advance(seconds=settings.calendar_lease_seconds + 1)
        pg.sync(source, explicit=True)
    invariants(pg, source)
    assert len(pg.rows(CalendarSeries, source)) == 6
    assert pg.state(source).applied_seq == 6


@pytest.mark.parametrize("round_number", range(4))
def test_forgetting_races_a_sync_and_always_ends_fully_scrubbed(pg, round_number):
    row, source = api_source(pg)
    pg.writer.append([series_item(), override_item(), series_item("s2", 1)])
    barrier = threading.Barrier(2)

    def sync_side():
        barrier.wait(20)
        return pg.sync(source, explicit=True)

    def forget_side():
        barrier.wait(20)
        return call(pg.client, pg.headers, row, "forget")

    with ThreadPoolExecutor(max_workers=2) as pool:
        syncing, forgetting = pool.submit(sync_side), pool.submit(forget_side)
        outcome, response = syncing.result(60), forgetting.result(60)
    assert response.status_code in {200, 409}, response.text
    if response.status_code == 409:  # the sync advanced the source revision first: retry once
        row = {
            **row,
            "revision": pg.client.post(
                f"/api/v1/calendars/{source}/read", headers=pg.headers, json={"scope": row["scope"]}
            ).json()["revision"],
        }
        assert call(pg.client, pg.headers, row, "forget").status_code == 200
    assert outcome["outcome"] in {"ok", "skipped", "lost"}, outcome
    state = pg.state(source)
    assert (state.status, state.blocked_reason, state.cursor, state.claim_token) == (
        "blocked",
        "source_forgotten",
        None,
        None,
    )
    assert all(r.state == "forgotten" and r.uid is None for r in pg.rows(CalendarSeries, source))
    assert all(r.state == "forgotten" for r in pg.rows(CalendarOverride, source))
    assert all(r.snapshot is None for r in pg.rows(CalendarChange, source))
    seqs = sorted(r.seq for r in pg.rows(CalendarChange, source))
    assert seqs == list(range(1, len(seqs) + 1))  # counts and hashes stay gapless
    assert pg.sync(source)["reason"] == "forgotten"


def test_a_database_failure_during_apply_rolls_back_and_a_retry_applies_once(pg, monkeypatch):
    _row, source = api_source(pg)
    pg.writer.append([series_item(), override_item()])
    original = sync.record_change
    calls = {"n": 0}

    def failing(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("synthetic injected failure after the first change row")
        return original(*args, **kwargs)

    with monkeypatch.context() as scoped:  # a plain undo() would also revert the fixture's clock
        scoped.setattr(sync, "record_change", failing)
        with pytest.raises(RuntimeError):
            pg.sync(source, explicit=True)
    assert pg.rows(CalendarSeries, source) == [] and pg.rows(CalendarChange, source) == []
    pg.clock.advance(seconds=settings.calendar_lease_seconds + 1)
    assert pg.sync(source, explicit=True)["outcome"] == "ok"
    invariants(pg, source)


# ---------------------------------------------------------------------------------------------
# The provider call must never stall because of what other threads of the API process are doing
# ---------------------------------------------------------------------------------------------
class Activity:
    """Unrelated work on other threads of the same process, as the live API process has it.

    Real requests through the application on the restricted role (authentication, briefing,
    queries: starlette, anyio worker threads, psycopg, SQLAlchemy, pydantic), plus the library
    activity of the answer path (an httpx client against a local HTTP server, which builds TLS
    contexts), logging, hashing, JSON, garbage collection and imports.
    """

    def __init__(self, pg):
        self.pg, self.stop, self.threads, self.errors, self.count = pg, threading.Event(), [], [], 0

    def _loop(self, work):
        while not self.stop.is_set():
            try:
                work()
                self.count += 1
            except Exception as error:  # noqa: BLE001
                if "LockNotAvailable" not in repr(error):  # same-user row contention is by design
                    self.errors.append(repr(error))
                    return
            time.sleep(0.002)  # steady traffic, not a CPU hog that starves every other thread

    def _api_requests(self):
        """Unrelated requests; a 503 (pool busy under this deliberate load) is not the point."""
        base = {"scope": "household_shared"}
        pg = self.pg
        briefing = {**base, "day": "2026-03-15", "timezone": "Europe/Paris", "horizon_days": 3}
        for response in (
            pg.client.get("/api/v1/auth/me", headers=pg.headers),
            pg.client.post("/api/v1/calendars/briefing", headers=pg.headers, json=briefing),
            pg.client.post("/api/v1/calendars/query", headers=pg.headers, json=base),
        ):
            assert response.status_code in (200, 422, 503), response.status_code

    def _database(self):
        with self.pg.maker.begin() as db:
            db.execute(text("select count(*) from calendar_sources")).scalar()

    def _libraries(self):
        import gc
        import hashlib
        import importlib
        import json
        import logging
        import uuid

        logging.getLogger("fetch-activity").info("x" * 200)
        hashlib.sha256(os.urandom(4096)).hexdigest()
        json.loads(json.dumps({"k": [uuid.uuid4().hex] * 50}))
        importlib.import_module("json.tool")
        _ = [bytearray(4000) for _ in range(40)]
        if self.count % 25 == 0:
            gc.collect()

    def _http_client(self):
        import httpx

        with httpx.Client(timeout=5) as client:  # builds an SSL context, opens a socket
            assert client.get(self.url).status_code == 200

    def __enter__(self):
        import http.server
        import socketserver

        class Quiet(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                pass

        class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Quiet)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        work = [self._api_requests] + [self._database] + [self._libraries] * 3
        work += [self._http_client] * 2
        self.threads = [threading.Thread(target=self._loop, args=(w,), daemon=True) for w in work]
        for thread in self.threads:
            thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        for thread in self.threads:
            thread.join(30)
        self.server.shutdown()
        self.server.server_close()


def test_concurrent_provider_fetches_never_stall_beside_unrelated_api_activity(pg, monkeypatch):
    sources = [api_source(pg)[1] for _ in range(4)]
    pg.writer.append([series_item(), override_item()])
    monkeypatch.setattr(settings, "calendar_fetch_timeout_seconds", 10)
    durations, fetch_errors, real_fetch = [], [], sync.fetch

    def timed(provider, since, timeout):
        started = time.monotonic()
        try:
            return real_fetch(provider, since, timeout)
        except Exception as error:
            fetch_errors.append(repr(error))
            raise
        finally:
            durations.append(time.monotonic() - started)

    monkeypatch.setattr(sync, "fetch", timed)
    outcomes, failures, contended = [], [], []

    def syncs(source):
        # Exactly what the owner sync route runs after it has authorized the request. The apply
        # step takes the owner's row lock with a short lock timeout, so unrelated same-user
        # requests can make it fail fast: the lease then simply runs out (crash-equivalent, as the
        # injected-failure test pins), later explicit syncs are "skipped / lease_held", and the
        # recovery check below proves the source syncs again. None of that is a fetch problem.
        for _ in range(30):
            try:
                outcomes.append(pg.sync(source, explicit=True)["outcome"])
            except Exception as error:  # noqa: BLE001
                (contended if "LockNotAvailable" in repr(error) else failures).append(repr(error))

    def route_syncs(source):
        # Requests of one user contend on that user's row with a short lock timeout (a documented
        # fast failure, a 503 or a lock error): that is the API's behaviour, not what is tested.
        try:
            for _ in range(8):
                response = pg.client.post(
                    f"/api/v1/calendars/{source}/sync",
                    headers=pg.headers,
                    json={"scope": "household_shared"},
                )
                if response.status_code == 200:
                    outcomes.append(response.json()["sync"]["outcome"])
                elif response.status_code == 503:
                    contended.append(response.text)
                else:
                    failures.append(f"{response.status_code} {response.text[:200]}")
        except Exception as error:  # noqa: BLE001
            (contended if "LockNotAvailable" in repr(error) else failures).append(repr(error))

    direct, direct_failures = [], []
    household = SyntheticProvider(settings.calendar_synthetic_directory, "household")
    expected_page = household.changes(None, codes.PAGE_ITEMS_MAX)

    def direct_fetches():
        # concurrent provider fetches themselves, a guaranteed number of them
        for _ in range(25):
            started = time.monotonic()
            try:
                direct.append(real_fetch(household, None, 10) == expected_page)
            except Exception as error:  # noqa: BLE001
                direct_failures.append(repr(error))
            durations.append(time.monotonic() - started)

    with Activity(pg) as activity:
        threads = [threading.Thread(target=syncs, args=(s,)) for s in sources[:2]]
        threads.append(threading.Thread(target=route_syncs, args=(sources[3],)))
        threads += [threading.Thread(target=direct_fetches) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(300)
    assert not any(thread.is_alive() for thread in threads)
    assert activity.errors == [], activity.errors[:3]
    assert activity.count > 100, activity.count  # the other threads really were busy throughout
    assert failures == [], failures[:3]
    # every fetch finished quickly and cleanly: no timeout, no stuck child, no protocol error
    assert fetch_errors == [], fetch_errors[:3]
    assert direct_failures == [], direct_failures[:3]
    assert direct == [True] * 100  # every direct fetch returned exactly the expected page
    assert max(durations) < 5, max(durations)  # nothing came near the 10 s fetch timeout
    # The sync-level part has no count floor (user-row lock timeouts decide how many syncs run);
    # what it proves is that every outcome is a normal one.
    assert set(outcomes) <= {"ok", "skipped"}, {o: outcomes.count(o) for o in set(outcomes)}
    with pytest.raises(ChildProcessError):  # no fetch child is left, not even a zombie
        os.waitpid(-1, os.WNOHANG)
    # recovery: once any lease left by a fast-failed apply has run out, every source syncs again
    pg.clock.advance(seconds=codes.LEASE_SECONDS + 1)
    for source in sources:
        assert pg.sync(source, explicit=True)["outcome"] == "ok"
        assert pg.state(source).claim_token is None
        invariants(pg, source)
    print(
        f"stress: {len(durations)} fetches (100 direct), max {max(durations):.3f}s, "
        f"{outcomes.count('ok')} syncs ok, {outcomes.count('skipped')} skipped, "
        f"{len(contended)} user-row lock timeouts, unrelated operations {activity.count}"
    )
