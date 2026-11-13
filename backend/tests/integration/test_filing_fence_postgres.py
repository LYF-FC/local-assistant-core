"""Revision fence: a stale worker or reconciler can never modify a newer revision of a filing.

Every attempt and every reconciliation episode owns the row revision its own claim produced. A
result is applied only if the row still carries that revision, decided by the database inside the
locking read. Stale results are discarded without writing the row or its history.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import select, text
from test_filing_postgres import forget_owned_test_sources, requested  # noqa: F401

from app import filing, filing_worker, identity
from app.models import FilingExecution, FilingExecutionEvent

pytestmark = pytest.mark.integration

FULL_HISTORY = ["requested", "attempted", "unknown", "reconciled", "attempted", "filed"]


def edit(admin, row_id, **columns):
    """Test-only backdating of timestamps; the seal trigger is re-enabled immediately."""
    with admin.begin() as db:
        db.execute(text("ALTER TABLE filing_executions DISABLE TRIGGER butler_filing_guard"))
        state = db.get(FilingExecution, row_id)
        for name, value in columns.items():
            setattr(state, name, value)
        db.flush()
        db.execute(text("ALTER TABLE filing_executions ENABLE TRIGGER butler_filing_guard"))


def age(admin, row, **extra):
    edit(
        admin,
        row.id,
        attempt_started_at=identity.now_utc() - filing.IN_FLIGHT_DEADLINE - timedelta(seconds=1),
        **extra,
    )


def due(admin, row):
    edit(admin, row.id, next_attempt_at=identity.now_utc())


def claim(maker, row):
    with maker.begin() as db:
        return filing_worker.claim(db, row)


def finish(maker, row, outcome, fence):
    with maker.begin() as db:
        return filing_worker.finish(db, row, outcome, fence)


def reconcile(maker, row, found, fence):
    with maker.begin() as db:
        return filing_worker.reconcile(db, row, found, fence)


def snap(admin, row):
    with admin() as db:
        state = db.get(FilingExecution, row.id)
        events = db.scalars(
            select(FilingExecutionEvent)
            .where(FilingExecutionEvent.execution_id == row.id)
            .order_by(FilingExecutionEvent.revision)
        ).all()
        return {
            "state": state.state,
            "revision": state.revision,
            "attempts": state.attempts,
            "in_flight": state.attempt_started_at is not None,
            "reason": state.reason,
            "next_attempt_at": state.next_attempt_at,
            "resolved_at": state.resolved_at,
            "operations": [e.operation for e in events],
            "event_revisions": [e.revision for e in events],
        }


def first_attempt(maker, row):
    action, payload = claim(maker, row)
    assert action == "apply"
    return payload[-1]


def reap_and_reconcile_absent(maker, admin, row, destination):
    """The first claim goes stale, is reaped to unknown and then reconciled as absent."""
    age(admin, row)
    assert filing_worker.process(maker, row, destination) == "unknown"
    due(admin, row)
    assert filing_worker.process(maker, row, destination) == "retried"


def second_attempt(maker, admin, row, destination):
    """Worker A claims and stalls; worker B reaps, reconciles and claims attempt two."""
    stale = first_attempt(maker, row)
    reap_and_reconcile_absent(maker, admin, row, destination)
    action, payload = claim(maker, row)
    assert action == "apply"
    return stale, payload[-1]


def assert_untouched(admin, row, before, destination, writes=0):
    assert snap(admin, row) == before
    assert destination.writes == writes


OUTCOMES = [
    filing.Outcome.TIMEOUT,
    filing.Outcome.TRANSIENT,
    filing.Outcome.ACCEPTED,
    filing.Outcome.COLLISION,
]


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_a_stale_outcome_after_a_newer_attempt_begins_is_skipped(scenario, runtime_engine, outcome):
    maker, admin, _, _, _, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    stale, current = second_attempt(maker, admin, row, destination)
    assert stale != current
    before = snap(admin, row)
    assert before["state"] == "pending" and before["attempts"] == 2 and before["in_flight"]
    assert finish(maker, row, outcome, stale) == "skipped"
    assert_untouched(admin, row, before, destination)
    # The newer attempt's own outcome stays authoritative.
    assert finish(maker, row, filing.Outcome.ACCEPTED, current) == "filed"
    after = snap(admin, row)
    assert after["state"] == "filed" and after["operations"] == FULL_HISTORY
    assert after["event_revisions"] == list(range(1, 7))


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_a_stale_worker_returning_after_the_newer_attempt_filed_is_skipped(
    scenario, runtime_engine, outcome
):
    maker, admin, _, _, _, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    stale, current = second_attempt(maker, admin, row, destination)
    assert finish(maker, row, filing.Outcome.ACCEPTED, current) == "filed"
    before = snap(admin, row)
    assert before["state"] == "filed" and before["resolved_at"] is not None
    assert finish(maker, row, outcome, stale) == "skipped"
    assert_untouched(admin, row, before, destination)


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_a_stale_worker_returning_after_the_newer_attempt_failed_is_skipped(
    scenario, runtime_engine, outcome
):
    maker, admin, _, _, _, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    stale, current = second_attempt(maker, admin, row, destination)
    assert finish(maker, row, filing.Outcome.COLLISION, current) == "failed"
    before = snap(admin, row)
    assert before["state"] == "failed" and before["reason"] == "collision"
    assert finish(maker, row, outcome, stale) == "skipped"
    assert_untouched(admin, row, before, destination)


@pytest.mark.parametrize("filed_at_destination", [False, True])
@pytest.mark.parametrize("outcome", OUTCOMES)
def test_a_stale_worker_returning_after_reconciliation_is_skipped(
    scenario, runtime_engine, outcome, filed_at_destination
):
    maker, admin, _, _, path, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    stale = first_attempt(maker, row)
    age(admin, row)
    assert filing_worker.process(maker, row, destination) == "unknown"
    unknown = snap(admin, row)
    assert unknown["state"] == "unknown"
    # While the filing is merely unknown the stale result must not settle it either.
    assert finish(maker, row, outcome, stale) == "skipped"
    assert_untouched(admin, row, unknown, destination)
    if filed_at_destination:
        assert destination.put(str(row.id), path, "0" * 64, 1) == filing.Outcome.ACCEPTED
    due(admin, row)
    expected = "filed" if filed_at_destination else "retried"
    assert filing_worker.process(maker, row, destination) == expected
    settled = snap(admin, row)
    assert settled["state"] == ("filed" if filed_at_destination else "pending")
    assert settled["reason"] == (None if filed_at_destination else "reconciled_absent")
    writes = destination.writes
    assert finish(maker, row, outcome, stale) == "skipped"
    assert_untouched(admin, row, settled, destination, writes)


def test_a_reconciliation_result_from_an_earlier_unknown_episode_is_rejected(
    scenario, runtime_engine
):
    maker, admin, _, _, _, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    first_attempt(maker, row)
    age(admin, row)
    assert filing_worker.process(maker, row, destination) == "unknown"
    episode = snap(admin, row)["revision"]
    due(admin, row)
    action, (_, fence) = claim(maker, row)
    assert action == "reconcile" and fence == episode
    # Another reconciler could not reach the destination: the row enters a newer unknown episode.
    assert reconcile(maker, row, filing.Lookup.UNAVAILABLE, fence) == "unknown"
    newer = snap(admin, row)
    assert newer["state"] == "unknown" and newer["revision"] == episode + 1
    # The late answer of the earlier episode is rejected, whatever it says.
    for found in (filing.Lookup.FILED, filing.Lookup.ABSENT):
        assert reconcile(maker, row, found, fence) == "skipped"
        assert_untouched(admin, row, newer, destination)
    # It is also rejected once the row has moved on to a newer attempt.
    due(admin, row)
    assert filing_worker.process(maker, row, destination) == "retried"
    action, payload = claim(maker, row)
    assert action == "apply"
    current = snap(admin, row)
    assert current["state"] == "pending" and current["attempts"] == 2 and current["in_flight"]
    for found in (filing.Lookup.FILED, filing.Lookup.ABSENT):
        assert reconcile(maker, row, found, fence) == "skipped"
        assert_untouched(admin, row, current, destination)
    assert finish(maker, row, filing.Outcome.ACCEPTED, payload[-1]) == "filed"


def test_the_attempt_three_false_failure_is_eliminated(scenario, runtime_engine):
    maker, admin, _, _, path, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    stale = first_attempt(maker, row)
    reap_and_reconcile_absent(maker, admin, row, destination)
    assert claim(maker, row)[0] == "apply"  # attempt two stalls as well
    age(admin, row)
    assert filing_worker.process(maker, row, destination) == "unknown"
    due(admin, row)
    assert filing_worker.process(maker, row, destination) == "retried"
    action, payload = claim(maker, row)
    assert action == "apply"
    assert snap(admin, row)["attempts"] == filing.MAX_ATTEMPTS
    # The third attempt's write really lands while the very first worker finally reports back.
    assert destination.put(str(row.id), path, payload[2], payload[3]) == filing.Outcome.ACCEPTED
    before = snap(admin, row)
    assert finish(maker, row, filing.Outcome.TRANSIENT, stale) == "skipped"
    assert_untouched(admin, row, before, destination, writes=1)
    assert before["state"] == "pending" and before["in_flight"]
    assert finish(maker, row, filing.Outcome.ACCEPTED, payload[-1]) == "filed"
    final = snap(admin, row)
    assert final["state"] == "filed" and final["reason"] is None
    assert destination.lookup(str(row.id)) == filing.Lookup.FILED and destination.writes == 1


def test_the_in_flight_deadline_boundary_decides_who_owns_the_attempt(
    scenario, runtime_engine, monkeypatch
):
    maker, admin, _, _, _, row = requested(scenario, runtime_engine)
    maker2, admin2, _, _, _, other = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    fence = first_attempt(maker, row)
    fence2 = first_attempt(maker2, other)
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    # One microsecond inside the deadline the claim is still live: nobody reaps it...
    edit(
        admin,
        row.id,
        attempt_started_at=now - filing.IN_FLIGHT_DEADLINE + timedelta(microseconds=1),
    )
    live = snap(admin, row)
    assert claim(maker, row) == ("skipped", None)
    assert snap(admin, row) == live
    # ...and its own outcome is still accepted.
    assert finish(maker, row, filing.Outcome.ACCEPTED, fence) == "filed"
    # Exactly at the deadline the claim is stale: it is reaped to unknown, never re-applied.
    edit(admin2, other.id, attempt_started_at=now - filing.IN_FLIGHT_DEADLINE)
    assert claim(maker2, other) == ("unknown", None)
    reaped = snap(admin2, other)
    assert reaped["state"] == "unknown" and not reaped["in_flight"]
    # The late finish of the reaped claim loses, whatever it reports.
    for outcome in OUTCOMES:
        assert finish(maker2, other, outcome, fence2) == "skipped"
        assert_untouched(admin2, other, reaped, destination)


def test_a_finisher_racing_the_reaper_has_exactly_one_winner(scenario, runtime_engine):
    for _ in range(5):
        maker, admin, _, _, _, row = requested(scenario, runtime_engine)
        destination = filing.SyntheticDestination()
        fence = first_attempt(maker, row)
        age(admin, row)
        barrier = Barrier(2)

        def finisher(maker=maker, row=row, fence=fence, barrier=barrier):
            barrier.wait()
            return finish(maker, row, filing.Outcome.ACCEPTED, fence)

        def reaper(maker=maker, row=row, barrier=barrier):
            barrier.wait()
            return claim(maker, row)[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = (pool.submit(finisher), pool.submit(reaper))
            pair = tuple(future.result() for future in futures)
        assert pair in {("filed", "skipped"), ("skipped", "unknown")}, pair
        final = snap(admin, row)
        if pair[0] == "filed":
            assert final["operations"] == ["requested", "attempted", "filed"]
        else:
            assert final["operations"] == ["requested", "attempted", "unknown"]
            assert final["state"] == "unknown"
        assert final["event_revisions"] == list(range(1, len(final["operations"]) + 1))
        assert destination.writes == 0


def test_a_stale_finish_racing_a_reconcile_never_beats_the_reconciler(scenario, runtime_engine):
    for _ in range(3):
        maker, admin, _, _, path, row = requested(scenario, runtime_engine)
        destination = filing.SyntheticDestination()
        stale = first_attempt(maker, row)
        age(admin, row)
        assert filing_worker.process(maker, row, destination) == "unknown"
        assert destination.put(str(row.id), path, "0" * 64, 1) == filing.Outcome.ACCEPTED
        due(admin, row)
        action, (_, fence) = claim(maker, row)
        assert action == "reconcile"
        barrier = Barrier(2)

        def stale_finish(maker=maker, row=row, stale=stale, barrier=barrier):
            barrier.wait()
            return finish(maker, row, filing.Outcome.TRANSIENT, stale)

        def reconciler(maker=maker, row=row, fence=fence, barrier=barrier):
            barrier.wait()
            return reconcile(maker, row, filing.Lookup.FILED, fence)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = (pool.submit(stale_finish), pool.submit(reconciler))
            pair = tuple(future.result() for future in futures)
        assert pair == ("skipped", "filed"), pair
        final = snap(admin, row)
        assert final["state"] == "filed"
        assert final["operations"] == ["requested", "attempted", "unknown", "reconciled"]
        assert destination.writes == 1
