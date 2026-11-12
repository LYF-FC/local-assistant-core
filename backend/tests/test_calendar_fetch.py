"""The provider fetch is genuinely bounded: a timed-out call is killed, never left running.

A Python thread cannot be cancelled, so a thread-based timeout records "timed out" while the
provider keeps working (and holds a worker's exit open). These tests use providers that sleep far
past the timeout, ignore SIGTERM, or never return, and prove the work is gone afterwards.
"""

import multiprocessing
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from uuid import UUID

import pytest
from test_calendar_sync import series_item, world  # noqa: F401

from app import calendar_provider as provider_module
from app import calendar_sync as sync
from app.calendar_provider import ChangePage
from app.config import settings

LONG = 60  # far beyond any timeout used here


class Sleeper:
    """Never returns in time, ignores SIGTERM, and records its process id."""

    def __init__(self, pid_file):
        self.pid_file = pid_file

    def changes(self, since, limit):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        with open(self.pid_file, "w") as handle:
            handle.write(str(os.getpid()))
        time.sleep(LONG)
        return ChangePage((), "v1:0", False)


def gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    # a zombie still answers signal 0; it is reaped by join(), so treat "not running" as gone
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().split(")")[-1].split()[0] == "Z"
    except FileNotFoundError:
        return True


def test_a_timed_out_fetch_is_killed_even_if_it_ignores_sigterm(tmp_path):
    pid_file = tmp_path / "pid"
    threads = threading.active_count()
    started = time.monotonic()
    with pytest.raises(provider_module.ProviderTimeout):
        sync.fetch(Sleeper(pid_file), None, 0.5)
    assert time.monotonic() - started < 5  # the call returned at the timeout, not after LONG
    pid = int(pid_file.read_text())
    assert pid != os.getpid()
    assert gone(pid), "the timed-out provider call is still running"
    assert multiprocessing.active_children() == []
    assert threading.active_count() == threads  # no leaked worker thread


def test_a_result_and_the_typed_errors_cross_the_process_boundary(tmp_path):
    page = ChangePage((provider_module.ProviderItem("series", "delete", "u", 2),), "v1:9", False)

    class Fine:
        def changes(self, since, limit):
            return page

    assert sync.fetch(Fine(), None, 5) == page
    for error in (
        provider_module.InvalidCursor("x"),
        provider_module.CursorExpired("x"),
        provider_module.PageTooLarge("x"),
        provider_module.ProviderUnavailable("x"),
    ):

        class Failing:
            def changes(self, since, limit, error=error):
                raise error

        with pytest.raises(type(error)):
            sync.fetch(Failing(), None, 5)

    class Malformed:
        def changes(self, since, limit):
            raise provider_module.MalformedItem(7)

    with pytest.raises(provider_module.MalformedItem) as caught:
        sync.fetch(Malformed(), None, 5)
    assert caught.value.index == 7
    assert multiprocessing.active_children() == []


def test_a_provider_that_exits_the_interpreter_cannot_end_the_caller():
    class Exits:
        def changes(self, since, limit):
            raise SystemExit(3)

    class Dies:
        def changes(self, since, limit):
            os._exit(9)  # no result at all

    with pytest.raises(provider_module.ProviderUnavailable):
        sync.fetch(Exits(), None, 5)
    with pytest.raises(provider_module.ProviderUnavailable):
        sync.fetch(Dies(), None, 5)


def test_worker_shutdown_is_not_held_open_by_a_timed_out_fetch(tmp_path):
    script = textwrap.dedent(
        f"""
        import os, signal, sys, time
        from app import calendar_provider as provider, calendar_sync as sync

        class Sleeper:
            def changes(self, since, limit):
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                time.sleep({LONG})

        try:
            sync.fetch(Sleeper(), None, 0.5)
        except provider.ProviderTimeout:
            print("timed out", flush=True)
        """
    )
    env = dict(
        os.environ,
        BUTLER_ENV="test",
        BUTLER_POSTGRES_DB="butler_test_unused",
        BUTLER_POSTGRES_USER="butler_runtime",
        BUTLER_POSTGRES_PASSWORD="synthetic-test-password-0123456789abcdef",
    )
    started = time.monotonic()
    done = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    elapsed = time.monotonic() - started
    assert done.returncode == 0 and "timed out" in done.stdout, done.stderr[-1500:]
    assert elapsed < 15, elapsed  # a leftover non-daemon thread would hold exit open for LONG


def test_a_sync_whose_fetch_times_out_releases_the_lease_and_recovers(world, monkeypatch):  # noqa: F811
    source = world.source()
    world.writer.append([series_item()])
    world.writer.add_fault("delay", arg=str(LONG))
    monkeypatch.setattr(settings, "calendar_fetch_timeout_seconds", 0.5)
    threads = threading.active_count()
    started = time.monotonic()
    result = world.sync(source)
    assert time.monotonic() - started < 10
    state = world.state(source)
    assert result["outcome"] == "retry_wait"
    assert (state.status, state.attempts, state.last_error_code) == (
        "retry_wait",
        1,
        "provider_timeout",
    )
    assert state.claim_token is None and state.claim_expires_at is None  # lease released at once
    assert state.next_attempt_at is not None and state.applied_seq == 0
    assert multiprocessing.active_children() == [] and threading.active_count() == threads
    # nothing was applied, and an early attempt is refused until the backoff passes
    assert world.sync(source)["reason"] == "not_due"
    # the provider recovers: after the backoff the next sync applies the page once
    world.writer.clear_faults()
    world.clock.advance(seconds=31)
    assert world.sync(source)["outcome"] == "ok"
    state = world.state(source)
    assert (state.status, state.attempts, state.applied_seq) == ("ok", 0, 1)
    assert UUID(str(state.source_id)) == source


def test_repeated_timeouts_never_accumulate_workers(world, monkeypatch):  # noqa: F811
    source = world.source()
    world.writer.add_fault("delay", arg=str(LONG))
    monkeypatch.setattr(settings, "calendar_fetch_timeout_seconds", 0.3)
    threads = threading.active_count()
    for delay in (30, 120):
        assert world.sync(source)["outcome"] == "retry_wait"
        world.clock.advance(seconds=delay + 1)
    assert multiprocessing.active_children() == []
    assert threading.active_count() == threads
    assert world.state(source).attempts == 2
