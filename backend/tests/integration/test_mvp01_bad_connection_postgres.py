"""Spec 077 characterisation: S4 (repeated timeouts) and S10 (reminder while its worker is killed).

These tests describe what the merged system does today; they change no behaviour. Disposable
PostgreSQL, restricted runtime role, real operating-system processes where stated, synthetic only.

S4: spec 069 allows three attempts. A destination that answers lookups ("absent") but times out on
every write ends the filing terminal ``failed`` (``attempts_exhausted``) although it was only
unreachable for writes. The composed owner outage (persistent lookup-unavailable plus one armed
write timeout) never reaches that state: the filing stays ``unknown`` until the outage ends.

S10: delivery is one database transaction. Killing the worker before the commit leaves the reminder
``scheduled`` and the next pass delivers it once; killing it after the commit leaves it ``delivered``
and no later pass delivers it again.
"""

import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from conftest import RUNTIME_PASSWORD
from sqlalchemy import func, select
from test_filing_fence_postgres import due, snap
from test_filing_postgres import forget_owned_test_sources, requested  # noqa: F401
from test_task_reminders_postgres import only_pass, setup

from app import filing, filing_worker, identity, local_answer_transport, synthetic_ledger
from app.config import settings
from app.models import TaskReminder, TaskReminderEvent
from app.synthetic_ledger import DurableSyntheticDestination

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    root = tmp_path / "ledger"
    root.mkdir()
    synthetic_ledger.initialize(root)
    monkeypatch.setattr(settings, "filing_synthetic_ledger_directory", root)
    return root


def test_s4_repeated_write_timeouts_with_conclusive_absence_end_failed_after_three_attempts(
    scenario, runtime_engine
):
    maker, admin, _doc, _receipt, path, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination({path: ["timeout_lost"] * 3})
    outcomes = []
    for _ in range(3):
        outcomes.append(filing_worker.process(maker, row, destination))  # write times out
        assert snap(admin, row)["state"] == "unknown"
        due(admin, row)
        outcomes.append(filing_worker.process(maker, row, destination))  # lookup says absent
    assert outcomes == ["unknown", "retried", "unknown", "retried", "unknown", "failed"]
    final = snap(admin, row)
    # Terminal although the destination only ever timed out: the honest wording must say so.
    assert final["state"] == "failed" and final["reason"] == "attempts_exhausted"
    assert final["attempts"] == 3 and destination.writes == 3 and destination.files == {}


def test_s4_the_composed_outage_never_fails_the_filing_and_ends_with_exactly_one_effect(
    scenario, runtime_engine, ledger
):
    maker, admin, _doc, _receipt, _path, row = requested(scenario, runtime_engine)
    synthetic_ledger.main(["control", "lookup-unavailable", "on"])
    synthetic_ledger.main(["control", "timeout-before-effect", "on"])
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "unknown"
    for _ in range(6):  # far beyond three attempts: the destination cannot even be asked
        due(admin, row)
        assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "unknown"
        state = snap(admin, row)
        assert state["state"] == "unknown" and state["reason"] == "ambiguous_outcome"
    assert state["attempts"] == 1  # never retried blindly, never counted as failing
    summary = DurableSyntheticDestination(ledger).summary()
    assert summary["effects"] == 0 and summary["calls"] == 1
    synthetic_ledger.main(["control", "lookup-unavailable", "off"])
    due(admin, row)
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "retried"
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "filed"
    summary = DurableSyntheticDestination(ledger).summary()
    assert summary["effects"] == 1 and summary["entries"] == 1 and summary["calls"] == 2


def test_s4_an_unreachable_destination_survives_a_killed_worker_and_still_files_once(
    scenario, runtime_engine, ledger
):
    maker, admin, _doc, _receipt, _path, row = requested(scenario, runtime_engine)
    synthetic_ledger.main(["control", "lookup-unavailable", "on"])
    synthetic_ledger.main(["control", "timeout-before-effect", "on"])
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "unknown"
    # A hard stop of every worker changes nothing durable: a fresh worker object keeps waiting.
    due(admin, row)
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "unknown"
    # An `unknown` row holds no claim (the database forbids one), so no deadline can reap it into `failed`.
    assert snap(admin, row)["state"] == "unknown" and not snap(admin, row)["in_flight"]
    synthetic_ledger.main(["control", "lookup-unavailable", "off"])
    due(admin, row)
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "retried"
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "filed"
    assert DurableSyntheticDestination(ledger).summary()["effects"] == 1


CHILD = """
import os, sys
from datetime import datetime
from uuid import UUID
from sqlalchemy import select
from app import identity, reminder_worker
from app.db import SessionLocal
from app.models import TaskReminder
identity.now_utc = lambda: datetime.fromisoformat(sys.argv[2])
with SessionLocal() as db, db.begin():
    candidate = db.execute(select(TaskReminder.id, TaskReminder.owner_id, TaskReminder.task_id,
        TaskReminder.scope_key).where(TaskReminder.id == UUID(sys.argv[1]))).one()
    assert reminder_worker.process(db, candidate) == "delivered"
    if sys.argv[3] == "before_commit":
        print("READY", flush=True)
        sys.stdin.readline()  # blocks inside the open transaction until killed
print("COMMITTED", flush=True)
sys.stdin.readline()
"""


def delivered_events(admin, reminder_id):
    with admin() as db:
        return db.scalar(
            select(func.count())
            .select_from(TaskReminderEvent)
            .where(
                TaskReminderEvent.reminder_id == UUID(reminder_id),
                TaskReminderEvent.operation == "delivered",
            )
        )


def run_child(row, point):
    env = dict(
        os.environ,
        PYTHONPATH=str(BACKEND),
        BUTLER_POSTGRES_USER="butler_runtime",
        BUTLER_POSTGRES_PASSWORD=RUNTIME_PASSWORD,
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", CHILD, row["id"], identity.now_utc().isoformat(), point],
        cwd=BACKEND,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout.readline().strip() == (
            "READY" if point == "before_commit" else "COMMITTED"
        )
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=30)
        assert proc.returncode == -signal.SIGKILL
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()


def test_s10_sigkill_before_the_commit_loses_nothing_and_delivers_once_afterwards(
    scenario, runtime_engine, monkeypatch
):
    _, _, admin, _, _, row = setup(scenario, monkeypatch)
    run_child(row, "before_commit")
    with admin() as db:
        assert db.get(TaskReminder, UUID(row["id"])).state == "scheduled"
    assert delivered_events(admin, row["id"]) == 0
    assert only_pass(runtime_engine, row) == "delivered"  # at the next pass: late, never lost
    assert only_pass(runtime_engine, row) == "skipped"  # and never twice
    assert delivered_events(admin, row["id"]) == 1


def test_s10_sigkill_after_the_commit_keeps_the_delivery_and_never_repeats_it(
    scenario, runtime_engine, monkeypatch
):
    _, _, admin, _, _, row = setup(scenario, monkeypatch)
    run_child(row, "after_commit")
    with admin() as db:
        assert db.get(TaskReminder, UUID(row["id"])).state == "delivered"
    assert only_pass(runtime_engine, row) == "skipped"
    assert delivered_events(admin, row["id"]) == 1


def test_a_stopped_answer_service_is_a_clean_unavailable_not_an_error():
    """R5: connection refused on a real loopback port (a stopped service) maps to the existing `unavailable`."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[
            1
        ]  # closed again on exit: nothing listens, so the connection is refused
    sources = [{"source": 1, "start_line": 1, "end_line": 1, "text": "Total: 1.00"}]
    outcome = local_answer_transport.select_passages(
        "What is the total?",
        "en",
        sources,
        f"http://127.0.0.1:{port}",
        "synthetic-citation:fixture",
        "1" * 64,
    )
    assert outcome["status"] == "unavailable" and outcome["selection"] is None
