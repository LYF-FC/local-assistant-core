"""The provider fetch is genuinely bounded and isolated: a timed-out call is killed, never left running.

A Python thread cannot be cancelled, so a thread-based timeout records "timed out" while the
provider keeps working (and holds a worker's exit open). The provider call therefore runs in a
fresh interpreter started with exec (not forked from this multithreaded process), which the parent
kills with SIGKILL at the deadline. These tests use a scripted stand-in child (selected through
``calendar_sync.CHILD_ARGV``) that hangs, ignores SIGTERM, starts grandchildren or answers with
garbage, plus the real child against real fixture files.
"""

import os
import subprocess
import sys
import textwrap
import threading
import time

import pytest
from calendar_synthetic_writer import SyntheticWriter
from test_calendar_sync import series_item, world  # noqa: F401

from app import calendar_provider as provider_module
from app import calendar_sync as sync
from app.calendar_provider import ChangePage, SyntheticProvider
from app.config import settings

STUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendar_fetch_stub_child.py")
LONG = 60  # far beyond any timeout used here


def use_stub(monkeypatch, scenario, target=None):
    argv = [sys.executable, "-I", "-S", STUB, scenario] + ([str(target)] if target else [])
    monkeypatch.setattr(sync, "CHILD_ARGV", argv)


def gone(pid):
    """SIGKILL is delivered asynchronously: allow a moment, then require it to be dead or a zombie."""
    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        try:  # a zombie still answers signal 0; "not running" is what matters
            with open(f"/proc/{pid}/stat") as handle:
                if handle.read().split(")")[-1].split()[0] == "Z":
                    return True
        except FileNotFoundError:
            return True
        time.sleep(0.05)
    return False


def no_children_left():
    try:
        os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        return True
    return False


@pytest.fixture
def fixture_file(tmp_path):
    writer = SyntheticWriter(tmp_path / "ref1.sqlite")
    return writer, SyntheticProvider(tmp_path, "ref1")


@pytest.fixture
def plain(fixture_file):
    """A real provider the stub child simply ignores (the stub speaks the protocol by script)."""
    return fixture_file[1]


# --- the deadline is hard ---------------------------------------------------------------------
def test_a_hung_child_that_ignores_sigterm_is_killed_with_everything_it_started(
    monkeypatch, tmp_path, plain
):
    pids = tmp_path / "pids"
    use_stub(monkeypatch, "hang", pids)
    threads = threading.active_count()
    started = time.monotonic()
    with pytest.raises(provider_module.ProviderTimeout):
        sync.fetch(plain, None, 1.0)
    assert time.monotonic() - started < 8  # returned at the timeout, not after LONG
    child, grandchild = (int(value) for value in pids.read_text().split())
    assert child != os.getpid() and gone(child), "the timed-out child is still running"
    assert gone(grandchild), "a process the child started survived the kill"
    assert threading.active_count() == threads and no_children_left()


def test_the_deadline_covers_a_child_that_never_answers_a_slow_provider(fixture_file, monkeypatch):
    writer, provider = fixture_file
    writer.add_fault("delay", arg=str(LONG))
    started = time.monotonic()
    with pytest.raises(provider_module.ProviderTimeout):
        sync.fetch(provider, None, 0.7)
    assert time.monotonic() - started < 8 and no_children_left()


def test_an_unreapable_child_is_reported_not_swallowed(monkeypatch, caplog, plain):
    """A child that survives SIGKILL and the bounded wait is an explicit, logged failure."""
    use_stub(monkeypatch, "ok")
    real = sync._reap
    monkeypatch.setattr(sync, "_reap", lambda process: real(process) and False)
    with caplog.at_level("ERROR"), pytest.raises(sync.FetchNotTerminated) as caught:
        sync.fetch(plain, None, 5)
    assert isinstance(caught.value, provider_module.ProviderUnavailable)
    assert "survived SIGKILL" in caplog.text
    assert sync.failure(caught.value) == ("retry", "provider_unavailable")

    class Stuck:
        pid = 2**22 + 99  # no such group
        stdin = stdout = None

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("child", timeout)

    monkeypatch.setattr(sync, "REAP_SECONDS", 0.05)
    assert real(Stuck()) is False


# --- what crosses the boundary ------------------------------------------------------------------
def test_the_real_child_returns_exactly_the_page_an_in_process_call_would(fixture_file):
    writer, provider = fixture_file
    writer.append([series_item(), series_item("s2", 1, op="delete")])
    assert sync.fetch(provider, None, 20) == provider.changes(None, 100)
    page = sync.fetch(provider, "v1:1", 20)
    assert page == provider.changes("v1:1", 100) and len(page.items) == 1


@pytest.mark.parametrize(
    ("setup", "since", "error"),
    [
        ("timeout", None, provider_module.ProviderTimeout),
        ("unavailable", None, provider_module.ProviderUnavailable),
        (None, "v1:999", provider_module.InvalidCursor),
        (None, "junk", provider_module.InvalidCursor),
        ("expired", "v1:1", provider_module.CursorExpired),
    ],
)
def test_the_typed_provider_errors_survive_the_process_boundary(fixture_file, setup, since, error):
    writer, provider = fixture_file
    writer.append([series_item(f"s{n}", 1) for n in range(4)])
    if setup == "expired":
        writer.truncate_before(3)  # min_retained 2: a cursor at change 1 is older
    elif setup:
        writer.add_fault(setup)
    with pytest.raises(error) as caught:
        sync.fetch(provider, since, 20)
    assert type(caught.value) is error


def test_a_malformed_item_keeps_its_index(fixture_file):
    writer, provider = fixture_file
    writer.append([series_item(), {**series_item("s2", 1), "raw_body": "{not json"}])
    with pytest.raises(provider_module.MalformedItem) as caught:
        sync.fetch(provider, None, 20)
    assert caught.value.index == 1


@pytest.mark.parametrize(
    ("kind", "error"),
    [
        ("InvalidCursor", provider_module.InvalidCursor),
        ("CursorExpired", provider_module.CursorExpired),
        ("PageTooLarge", provider_module.PageTooLarge),
        ("ProviderTimeout", provider_module.ProviderTimeout),
        ("ProviderUnavailable", provider_module.ProviderUnavailable),
        ("SomethingElse", provider_module.ProviderUnavailable),
        ("MalformedItem", provider_module.MalformedItem),
    ],
)
def test_the_error_kinds_a_child_may_report_are_a_closed_set(monkeypatch, kind, error, plain):
    use_stub(monkeypatch, f"error:{kind}")
    with pytest.raises(error) as caught:
        sync.fetch(plain, None, 5)
    assert type(caught.value) is error
    if error is provider_module.MalformedItem:
        assert caught.value.index == 4


@pytest.mark.parametrize("scenario", ["garbage", "huge", "empty_exit", "wrong_shape", "extra_keys"])
def test_a_child_that_breaks_the_protocol_is_provider_unavailable_and_gone(
    monkeypatch, scenario, plain
):
    use_stub(monkeypatch, scenario)
    with pytest.raises(provider_module.ProviderUnavailable) as caught:
        sync.fetch(plain, None, 5)
    assert type(caught.value) is provider_module.ProviderUnavailable
    assert no_children_left()


def test_a_well_formed_answer_from_the_stub_is_rebuilt_into_typed_objects(monkeypatch, plain):
    use_stub(monkeypatch, "ok")
    page = sync.fetch(plain, None, 5)
    assert page == ChangePage(
        (provider_module.ProviderItem("series", "delete", "u", 2, None, None),), "v1:9", False
    )


# --- isolation ------------------------------------------------------------------------------------
def test_the_child_inherits_no_environment_secret_and_does_not_run_in_the_working_directory(
    monkeypatch, tmp_path, plain
):
    monkeypatch.setenv("BUTLER_POSTGRES_PASSWORD", "synthetic-secret-that-must-not-leak")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    report = tmp_path / "report.json"
    use_stub(monkeypatch, "environment", report)
    sync.fetch(plain, None, 5)
    import json

    seen = json.loads(report.read_text())
    assert set(seen["env"]) <= {"LC_CTYPE"}  # at most the interpreter's own locale setting
    assert seen["cwd"] == "/"


def test_the_real_child_imports_no_settings_database_or_network_library(tmp_path):
    probe = textwrap.dedent(
        f"""
        import json, os, sys
        sys.argv = ["child"]
        sys.path.append({os.path.dirname(os.path.dirname(STUB))!r})
        from app import calendar_provider
        loaded = set(sys.modules)
        banned = {{"app.config", "pydantic", "sqlalchemy", "psycopg", "socket", "ssl", "http",
                  "urllib.request", "httpx", "requests"}}
        print(json.dumps(sorted(banned & loaded)))
        """
    )
    done = subprocess.run(
        [sys.executable, "-I", "-S", "-c", probe], capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "[]", done.stdout


# --- concurrency and shutdown -----------------------------------------------------------------------
def test_concurrent_fetches_from_many_threads_all_succeed(fixture_file):
    writer, provider = fixture_file
    writer.append([series_item()])
    expected = provider.changes(None, 100)
    failures = []

    def run():
        for _ in range(5):
            try:
                assert sync.fetch(provider, None, 30) == expected
            except Exception as error:  # noqa: BLE001
                failures.append(repr(error))

    workers = [threading.Thread(target=run) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(180)
    assert failures == [] and no_children_left()


def test_worker_shutdown_is_not_held_open_by_a_timed_out_fetch(tmp_path):
    writer = SyntheticWriter(tmp_path / "ref1.sqlite")
    writer.add_fault("delay", arg=str(LONG))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {root!r})
        from app import calendar_provider as provider, calendar_sync as sync

        try:
            sync.fetch(provider.SyntheticProvider({str(tmp_path)!r}, "ref1"), None, 0.7)
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
        timeout=40,
        check=False,
    )
    elapsed = time.monotonic() - started
    assert done.returncode == 0 and "timed out" in done.stdout, done.stderr[-1500:]
    assert elapsed < 20, elapsed  # a leftover non-daemon thread would hold exit open for LONG


# --- the sync protocol around a timed-out fetch --------------------------------------------------
def test_a_sync_whose_fetch_times_out_releases_the_lease_and_recovers(world, monkeypatch):  # noqa: F811
    source = world.source()
    world.writer.append([series_item()])
    world.writer.add_fault("delay", arg=str(LONG))
    monkeypatch.setattr(settings, "calendar_fetch_timeout_seconds", 0.7)
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
    assert threading.active_count() == threads and no_children_left()
    # nothing was applied, and an early attempt is refused until the backoff passes
    assert world.sync(source)["reason"] == "not_due"
    # the provider recovers: after the backoff the next sync applies the page once
    world.writer.clear_faults()
    world.clock.advance(seconds=31)
    assert world.sync(source)["outcome"] == "ok"
    state = world.state(source)
    assert (state.status, state.attempts, state.applied_seq) == ("ok", 0, 1)


def test_repeated_timeouts_never_accumulate_workers(world, monkeypatch):  # noqa: F811
    source = world.source()
    world.writer.add_fault("delay", arg=str(LONG))
    monkeypatch.setattr(settings, "calendar_fetch_timeout_seconds", 0.5)
    threads = threading.active_count()
    for delay in (30, 120):
        assert world.sync(source)["outcome"] == "retry_wait"
        world.clock.advance(seconds=delay + 1)
    assert threading.active_count() == threads and no_children_left()
    assert world.state(source).attempts == 2


def test_only_a_synthetic_provider_can_run_in_the_isolated_child():
    class Other:
        def changes(self, since, limit):
            return ChangePage((), "v1:0", False)

    with pytest.raises(provider_module.ProviderUnavailable):
        sync.fetch(Other(), None, 5)
    assert no_children_left()
