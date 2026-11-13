"""Gate 7 process-restart evidence: the filing worker recovers after its process is genuinely gone.

Every worker here is a separate operating-system process running the real
`filing_worker.process`. The synthetic destination is a durable directory ledger, so the effect and
the call history survive SIGKILL. A fresh, distinct process recovers from the same PostgreSQL rows
and the same ledger. Time passes by backdating the persisted claim (the same test-only technique
as the revision-fence tests); nothing is synchronised with sleeps.

This is process-restart evidence for a synthetic destination only. It does not show durability of a
real destination, a live inbox, real authorization or cross-store reconciliation.
"""

import pytest
from restart_support import FileDestination, Ledger, Worker, run_to_completion
from test_filing_fence_postgres import FULL_HISTORY, age, due, snap
from test_filing_postgres import forget_owned_test_sources, requested  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def procs():
    started = []
    yield started
    for worker in started:  # reliable cleanup, including after a failed assertion
        worker.stop()


@pytest.fixture
def env(scenario, runtime_engine, tmp_path, procs):
    maker, admin, doc, _receipt, path, row = requested(scenario, runtime_engine)
    ledger = Ledger(tmp_path / "destination")
    url = runtime_engine.url.render_as_string(hide_password=False)

    class Env:
        pass

    e = Env()
    e.admin, e.row, e.path, e.ledger, e.url, e.doc = admin, row, path, ledger, url, doc
    e.key = str(row.id)
    e.scenario, e.maker = scenario, maker

    def spawn(crash_at=None):
        worker = Worker("filing", url, ledger, row.id, crash_at).start()
        procs.append(worker)
        return worker

    e.spawn = spawn
    e.fresh = lambda: run_to_completion("filing", url, ledger, row.id)
    return e


def crash_at(env, point):
    """Run a worker to a crash point and kill it; returns the evidence at the moment of death."""
    worker = env.spawn(point)
    assert worker.wait_reached() == point
    at_point = snap(env.admin, env.row)
    effects_at_point = list(env.ledger.effects())
    worker.kill()
    # The durable state is exactly what the dead process left behind.
    assert snap(env.admin, env.row) == at_point
    assert env.ledger.effects() == effects_at_point
    return at_point, worker


def test_termination_before_the_effect_recovers_and_completes_once(env):
    at_death, worker = crash_at(env, "before_effect")
    # The claim was committed and the authorization consumed, but no effect exists.
    assert at_death["state"] == "pending" and at_death["in_flight"] and at_death["attempts"] == 1
    assert env.ledger.objects() == [] and env.ledger.effects() == []
    assert len(env.ledger.calls()) == 1

    # A fresh process inside the in-flight deadline must not touch the claimed row.
    assert env.fresh() == "skipped"
    assert len(env.ledger.calls()) == 1

    age(env.admin, env.row)
    assert env.fresh() == "unknown"  # reaped to unknown; never re-applied blindly
    assert len(env.ledger.calls()) == 1 and snap(env.admin, env.row)["state"] == "unknown"

    due(env.admin, env.row)
    assert env.fresh() == "retried"  # lookup answers "absent": only now may the effect be retried
    assert len(env.ledger.calls()) == 1 and env.ledger.lookups() == [env.key]

    assert env.fresh() == "filed"
    final = snap(env.admin, env.row)
    assert final["state"] == "filed" and final["attempts"] == 2
    assert final["operations"] == FULL_HISTORY and final["event_revisions"] == list(range(1, 7))
    [effect] = env.ledger.objects()
    assert effect["key"] == env.key and effect["path"] == env.path
    assert len(env.ledger.effects()) == 1 and len(env.ledger.calls()) == 2
    assert worker.proc.returncode == -9


def test_termination_after_the_effect_reconciles_without_repeating_it(env):
    at_death, _ = crash_at(env, "after_effect")
    # The effect is durable in the ledger while the database still shows an unreported claim.
    assert at_death["state"] == "pending" and at_death["in_flight"]
    [effect] = env.ledger.objects()
    assert effect["key"] == env.key and len(env.ledger.calls()) == 1

    assert env.fresh() == "skipped"
    age(env.admin, env.row)
    assert env.fresh() == "unknown"  # not "failed": the effect may exist
    assert snap(env.admin, env.row)["state"] == "unknown"

    due(env.admin, env.row)
    assert env.fresh() == "filed"  # reconciled from the persistent ledger
    final = snap(env.admin, env.row)
    assert final["state"] == "filed" and final["attempts"] == 1
    assert final["operations"] == ["requested", "attempted", "unknown", "reconciled"]
    # Exactly one write call and one effect ever happened; recovery never re-applied it.
    assert len(env.ledger.calls()) == 1 and len(env.ledger.effects()) == 1
    assert env.ledger.objects() == [effect]


def test_an_inconclusive_lookup_keeps_the_outcome_unknown_until_it_can_be_resolved(env):
    crash_at(env, "after_effect")
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    env.ledger.block_lookup()
    for _ in range(2):  # repeated recovery passes while the destination cannot answer
        due(env.admin, env.row)
        assert env.fresh() == "unknown"
        state = snap(env.admin, env.row)
        assert state["state"] == "unknown" and state["reason"] == "ambiguous_outcome"
        assert state["attempts"] == 1 and state["resolved_at"] is None
    # No resend, no overwrite, no false failure while the outcome was unknowable.
    assert len(env.ledger.calls()) == 1 and len(env.ledger.effects()) == 1
    assert len(env.ledger.lookups()) == 2

    env.ledger.unblock_lookup()
    due(env.admin, env.row)
    assert env.fresh() == "filed"
    final = snap(env.admin, env.row)
    assert final["state"] == "filed" and final["attempts"] == 1
    assert len(env.ledger.calls()) == 1 and len(env.ledger.effects()) == 1


def test_an_inconclusive_lookup_never_triggers_a_retry_even_if_no_effect_happened(env):
    crash_at(env, "before_effect")
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    env.ledger.block_lookup()
    due(env.admin, env.row)
    assert env.fresh() == "unknown"  # cannot tell "absent" from "unreachable": do not retry
    assert env.ledger.calls().__len__() == 1 and env.ledger.objects() == []
    env.ledger.unblock_lookup()
    due(env.admin, env.row)
    assert env.fresh() == "retried"  # a conclusive "absent" is what allows the retry
    assert env.fresh() == "filed"
    assert len(env.ledger.calls()) == 2 and len(env.ledger.effects()) == 1


def test_a_competing_recovery_worker_cannot_advance_a_claim_it_does_not_hold(env):
    crash_at(env, "before_effect")
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    due(env.admin, env.row)
    assert env.fresh() == "retried"
    # Worker A re-claims and stalls just before the effect, holding the valid claim.
    holder = env.spawn("before_effect")
    assert holder.wait_reached() == "before_effect"
    held = snap(env.admin, env.row)
    assert held["state"] == "pending" and held["in_flight"] and held["attempts"] == 2
    calls_before = len(env.ledger.calls())
    # Worker B races for the same operation and loses without touching state or destination.
    assert env.fresh() == "skipped"
    assert snap(env.admin, env.row) == held
    assert len(env.ledger.calls()) == calls_before and env.ledger.effects() == []
    # The holder alone advances it.
    holder.release()
    assert holder.finish() == "filed"
    assert snap(env.admin, env.row)["state"] == "filed"
    assert len(env.ledger.effects()) == 1


def test_simultaneous_fresh_workers_create_one_effect(env):
    first, second = env.spawn(), env.spawn()
    outcomes = sorted([first.finish(), second.finish()])
    assert outcomes == ["filed", "skipped"]
    assert len(env.ledger.effects()) == 1 and len(env.ledger.calls()) == 1
    assert snap(env.admin, env.row)["operations"] == ["requested", "attempted", "filed"]


@pytest.mark.parametrize("stall_at", ["before_effect", "after_effect"])
def test_a_stalled_worker_resuming_after_recovery_cannot_overwrite_the_newer_result(env, stall_at):
    stalled = env.spawn(stall_at)
    assert stalled.wait_reached() == stall_at
    # Recovery proceeds in other processes while the first worker is alive but stalled.
    age(env.admin, env.row)
    assert env.fresh() == "unknown"
    due(env.admin, env.row)
    expected_effect_first = stall_at == "after_effect"
    if expected_effect_first:
        assert env.fresh() == "filed"  # ledger already holds the effect: reconciled, not rewritten
    else:
        assert env.fresh() == "retried"
        assert env.fresh() == "filed"  # a newer attempt applies the effect itself
    newer = snap(env.admin, env.row)
    effects = list(env.ledger.effects())
    assert newer["state"] == "filed" and len(effects) == 1
    # The stalled, now stale, worker resumes with an obsolete fence and is discarded.
    stalled.release()
    assert stalled.finish() == "skipped"
    assert snap(env.admin, env.row) == newer
    assert env.ledger.effects() == effects and len(env.ledger.objects()) == 1


def test_an_existing_destination_object_is_never_overwritten_after_a_restart(env):
    Ledger(env.ledger.root).publish(
        FileDestination.name(env.path),
        {"key": "other-filing-key", "path": env.path, "sha256": "x", "size": 1},
    )
    before = env.ledger.objects()
    assert env.fresh() == "failed"
    state = snap(env.admin, env.row)
    assert state["state"] == "failed" and state["reason"] == "collision"
    assert env.ledger.objects() == before and env.ledger.effects() == []


def test_a_cancelled_request_has_no_effect_in_any_process(env):
    client, headers = env.scenario[0], env.scenario[1]
    cancelled = client.post(
        "/api/v1/filing/cancel",
        headers=headers,
        json={"scope": env.doc["scope"], "execution_id": env.key, "expected_revision": 1},
    )
    assert cancelled.status_code == 200
    assert env.fresh() == "skipped"
    assert env.ledger.calls() == [] and env.ledger.objects() == []
