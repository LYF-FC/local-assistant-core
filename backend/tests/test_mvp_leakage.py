"""Whole-MVP cross-user leakage sweep on SQLite (Gate 1). See ``mvp_leakage_support``.

The restricted-PostgreSQL mirror is ``integration/test_mvp_leakage_postgres.py``; the sensitivity
controls are ``test_mvp_leakage_controls.py``; the route classification is
``test_mvp_leakage_inventory.py``.
"""

from contextlib import ExitStack

import mvp_leakage_inventory as inventory
import mvp_leakage_support as lk
import pytest

REQUESTED = {}  # adapter name -> set of (METHOD, route) requested by that adapter's sweep


@pytest.fixture
def world(auth_client, auth_store):
    with ExitStack() as stack:
        env = lk.support.sqlite_environment(auth_store, stack)
        world = lk.build_world(env)
        yield world
        lk.cleanup(world)


@pytest.mark.parametrize("name", sorted(lk.ADAPTERS))
def test_sweep(world, name, caplog):
    REQUESTED[name] = lk.run_sweep(world, name, caplog)


def test_operations_observations_carry_no_record_content(world, caplog):
    REQUESTED["operations"] = lk.run_operations_sweep(world, caplog)


def test_every_swept_route_was_requested(auth_client, auth_store, caplog):
    """A classification as swept is checked against the requests the sweeps really made. Sweeps that
    have not run in this session (a single test was selected) are run here, so the check never
    passes on missing evidence."""
    for name in sorted(lk.ADAPTERS):
        if name not in REQUESTED:
            with ExitStack() as stack:
                env = lk.support.sqlite_environment(auth_store, stack)
                world = lk.build_world(env)
                try:
                    REQUESTED[name] = lk.run_sweep(world, name, caplog)
                finally:
                    lk.cleanup(world)
    if "operations" not in REQUESTED:
        with ExitStack() as stack:
            env = lk.support.sqlite_environment(auth_store, stack)
            world = lk.build_world(env)
            try:
                REQUESTED["operations"] = lk.run_operations_sweep(world, caplog)
            finally:
                lk.cleanup(world)
    requested = set().union(*REQUESTED.values())
    entries = inventory.classified(lk.registered_operations())
    never = sorted(
        key for key, entry in entries.items() if entry.kind == "swept" and key not in requested
    )
    assert not never, f"routes classified as swept that no sweep requested: {never}"
