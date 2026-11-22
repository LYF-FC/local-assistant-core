"""Durable synthetic filing destination (spec 076): guards, exclusivity, restart and controls.

Synthetic only: a temporary directory stands in for the rehearsal's named volume. The SIGKILL case
runs a real operating-system child so that the effect provably does not depend on process memory.
"""

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from app import filing, synthetic_ledger
from app.config import settings
from app.synthetic_ledger import MARKER, DurableSyntheticDestination, LedgerError

BACKEND = Path(__file__).resolve().parents[1]
KEY = "a" * 64
OTHER = "b" * 64
SHA = "c" * 64


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    root = tmp_path / "ledger"
    root.mkdir()
    synthetic_ledger.initialize(root)
    monkeypatch.setattr(settings, "filing_synthetic_ledger_directory", root)
    return root


def destination(root, **kwargs):
    # A new instance models a new worker process reading the same durable state.
    return DurableSyntheticDestination(root, **kwargs)


def test_guards_refuse_unmarked_relative_linked_missing_and_production(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(LedgerError):
        destination(plain)  # no marker
    with pytest.raises(LedgerError):
        destination(Path("relative"))
    with pytest.raises(LedgerError):
        destination(tmp_path / "missing")
    marked = tmp_path / "marked"
    marked.mkdir()
    synthetic_ledger.initialize(marked)
    link = tmp_path / "link"
    link.symlink_to(marked)
    with pytest.raises(LedgerError):
        destination(link)  # a symbolic link is never followed
    (marked / MARKER).write_text("forged")
    with pytest.raises(LedgerError):
        destination(marked)
    synthetic_ledger.initialize(plain)
    monkeypatch.setattr(settings, "env", "production")
    with pytest.raises(LedgerError):
        destination(plain)
    with pytest.raises(LedgerError):
        synthetic_ledger.initialize(plain)


def test_initialize_refuses_a_non_empty_unmarked_directory(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "unrelated.txt").write_text("not a ledger")
    with pytest.raises(LedgerError):
        synthetic_ledger.initialize(root)
    assert not (root / MARKER).exists() and (root / "unrelated.txt").exists()


def test_initialize_is_idempotent_for_a_marked_ledger(ledger):
    destination(ledger).put(KEY, "invoices/manual/a.txt", SHA, 7)
    synthetic_ledger.initialize(ledger)
    assert destination(ledger).summary()["entries"] == 1


def test_effect_survives_a_new_instance_and_never_overwrites(ledger):
    first = destination(ledger)
    assert first.put(KEY, "Invoices//Manual/A.txt", SHA, 7) is filing.Outcome.ACCEPTED
    second = destination(ledger)  # restarted worker
    assert second.lookup(KEY) is filing.Lookup.FILED
    assert second.lookup(OTHER) is filing.Lookup.ABSENT
    assert second.put(KEY, "invoices/manual/a.txt", SHA, 7) is filing.Outcome.ACCEPTED  # idempotent
    assert second.put(OTHER, "invoices/manual/A.txt", SHA, 7) is filing.Outcome.COLLISION
    summary = second.summary()
    assert summary["entries"] == 1 and summary["effects"] == 1


def test_entries_hold_metadata_only(ledger):
    destination(ledger).put(KEY, "invoices/manual/a.txt", SHA, 7)
    files = list((ledger / "objects").iterdir())
    assert len(files) == 1
    value = json.loads(files[0].read_text())
    assert value == {
        "schema": 1,
        "key": KEY,
        "path": "invoices/manual/a.txt",
        "sha256": SHA,
        "size": 7,
    }
    assert not any(ledger.rglob("*.pdf")) and not any(ledger.rglob("*.eml"))


def test_competing_threads_produce_one_effect(ledger):
    results = []

    def run(key):
        results.append(destination(ledger).put(key, "invoices/manual/a.txt", SHA, 7))

    threads = [threading.Thread(target=run, args=(KEY if i % 2 else OTHER,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    summary = destination(ledger).summary()
    assert summary["entries"] == 1 and summary["effects"] == 1
    assert results.count(filing.Outcome.COLLISION) >= 3


def test_corrupt_or_foreign_entry_is_refused_not_trusted(ledger):
    destination(ledger).put(KEY, "invoices/manual/a.txt", SHA, 7)
    entry = next((ledger / "objects").iterdir())
    entry.write_text(json.dumps({"schema": 1, "key": KEY, "extra": "unexpected"}))
    with pytest.raises(LedgerError):
        destination(ledger).lookup(KEY)
    entry.write_text("{not json")
    with pytest.raises(ValueError):
        destination(ledger).put(KEY, "invoices/manual/a.txt", SHA, 7)


def test_lookup_control_is_inconclusive_and_clears(ledger):
    target = destination(ledger)
    target.put(KEY, "invoices/manual/a.txt", SHA, 7)
    (ledger / "control" / "lookup-unavailable").write_text("1")
    assert destination(ledger).lookup(KEY) is filing.Lookup.UNAVAILABLE
    (ledger / "control" / "lookup-unavailable").unlink()
    assert destination(ledger).lookup(KEY) is filing.Lookup.FILED


def test_timeout_after_effect_records_the_effect_once_and_is_one_shot(ledger):
    (ledger / "control" / "timeout-after-effect").write_text("1")
    target = destination(ledger)
    assert target.put(KEY, "invoices/manual/a.txt", SHA, 7) is filing.Outcome.TIMEOUT
    assert target.lookup(KEY) is filing.Lookup.FILED
    assert not (ledger / "control" / "timeout-after-effect").exists()
    assert target.put(KEY, "invoices/manual/a.txt", SHA, 7) is filing.Outcome.ACCEPTED
    assert target.summary()["effects"] == 1


def test_timeout_before_effect_leaves_no_entry_and_is_one_shot(ledger):
    (ledger / "control" / "timeout-before-effect").write_text("1")
    target = destination(ledger)
    assert target.put(KEY, "invoices/manual/a.txt", SHA, 7) is filing.Outcome.TIMEOUT
    assert target.lookup(KEY) is filing.Lookup.ABSENT
    assert target.put(KEY, "invoices/manual/a.txt", SHA, 7) is filing.Outcome.ACCEPTED
    assert target.summary()["effects"] == 1


def test_control_command_is_limited_to_a_marked_ledger(ledger, tmp_path, monkeypatch, capsys):
    synthetic_ledger.main(["control", "lookup-unavailable", "on"])
    assert (ledger / "control" / "lookup-unavailable").exists()
    synthetic_ledger.main(["control", "lookup-unavailable", "off"])
    assert not (ledger / "control" / "lookup-unavailable").exists()
    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.setattr(settings, "filing_synthetic_ledger_directory", bare)
    with pytest.raises(SystemExit):
        synthetic_ledger.main(["control", "lookup-unavailable", "on"])
    assert not (bare / "control").exists()
    assert "Refused" in capsys.readouterr().err


CHILD = """
import sys
from app import synthetic_ledger
from app.config import settings

destination = synthetic_ledger.DurableSyntheticDestination(sys.argv[1], hook=lambda point: (
    print("REACHED", point, flush=True), sys.stdin.readline()) if point == sys.argv[2] else None)
destination.put(sys.argv[3], "invoices/manual/a.txt", sys.argv[4], 7)
"""


def child(ledger, point):
    env = dict(os.environ, PYTHONPATH=str(BACKEND))
    return subprocess.Popen(
        [sys.executable, "-c", CHILD, str(ledger), point, KEY, SHA],
        cwd=BACKEND,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


@pytest.mark.parametrize(("point", "present"), [("before_effect", False), ("after_effect", True)])
def test_sigkill_of_a_real_process_keeps_or_omits_the_effect_as_its_point_dictates(
    ledger, point, present
):
    proc = child(ledger, point)
    try:
        assert proc.stdout.readline().strip() == f"REACHED {point}"
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=30)
        assert proc.returncode == -signal.SIGKILL
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()
    fresh = destination(ledger)
    assert fresh.lookup(KEY) is (filing.Lookup.FILED if present else filing.Lookup.ABSENT)
    assert fresh.put(KEY, "invoices/manual/a.txt", SHA, 7) is filing.Outcome.ACCEPTED
    # Exactly one effect in both cases: lost before the kill, or kept and never repeated.
    assert fresh.summary()["entries"] == 1 and fresh.summary()["effects"] == 1


def test_worker_defaults_to_the_in_memory_destination_and_durable_is_explicit(ledger, monkeypatch):
    from app import filing_worker

    seen = []

    def once(destination, **kwargs):
        seen.append(type(destination))
        return {"errors": 0}

    monkeypatch.setattr(filing_worker, "run_once", once)
    monkeypatch.setattr(settings, "postgres_user", "butler_runtime")
    monkeypatch.setattr(settings, "postgres_db", "butler_test_ledger")
    for argv in (["--once"], ["--once", "--destination", "durable"]):
        monkeypatch.setattr(sys, "argv", ["filing_worker", *argv])
        filing_worker.main()
    assert seen == [filing.SyntheticDestination, DurableSyntheticDestination]
