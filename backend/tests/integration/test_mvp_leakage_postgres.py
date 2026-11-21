"""Whole-MVP cross-user leakage sweep through the restricted PostgreSQL runtime role (Gate 1).

The same behavior as ``test_mvp_leakage.py`` runs here. Privileged sessions (``postgres_engine``)
only provision synthetic users, change grants and read audit rows; every request under test is
served by a client whose database session is bound to ``runtime_engine``, the restricted runtime
role. Records are unique per test; shared-scope records are forgotten at the end because the
disposable database keeps committed rows for the rest of the run.
"""

from contextlib import ExitStack

import mvp_leakage_support as lk
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.runtime_role import ROLE

pytestmark = pytest.mark.integration


@pytest.fixture
def world(postgres_engine, runtime_engine):
    admin = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with ExitStack() as stack:
        env = lk.support.postgres_environment(admin, runtime_engine, stack)
        world = lk.build_world(env)
        yield world
        lk.cleanup(world)


@pytest.fixture
def new_world(postgres_engine, runtime_engine):
    admin = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with ExitStack() as stack:
        env = lk.support.postgres_environment(admin, runtime_engine, stack)
        made = []

        def build():
            made.append(lk.build_world(env))
            return made[-1]

        yield build
        for built in made:
            lk.cleanup(built)


# Every page-boundary scenario of every listing keyed by record id runs through the restricted role,
# the same cases as the SQLite module. Calendars and routines have the two scenarios the harness
# defines for them (a creator may hold at most ten records, so no short page is possible there).
SCENARIOS = ("exactly one page", "one record over a page", "a short page")
BOUNDARY_CASES = [
    (name, scenario_name)
    for name in sorted(lk.ADAPTERS)
    if lk.ADAPTERS[name].boundary_model is not None
    for scenario_name in SCENARIOS[
        : 2 if lk.ADAPTERS[name].boundary_layout == "shared_spread" else 3
    ]
]


def test_boundary_cases_cover_every_paginated_listing():
    assert sorted({name for name, _ in BOUNDARY_CASES}) == [
        "approvals", "calendars", "context", "documents", "finance",
        "memory", "reminders", "routines", "tasks",
    ]  # fmt: skip
    assert len(BOUNDARY_CASES) == 25


@pytest.mark.parametrize(("name", "scenario_name"), BOUNDARY_CASES)
def test_page_boundaries(new_world, name, scenario_name):
    lk.sweep_boundaries(new_world, lk.ADAPTERS[name], only={scenario_name})


@pytest.mark.parametrize("name", sorted(lk.ADAPTERS))
def test_sweep(world, name, caplog):
    lk.run_sweep(world, name, caplog)


def test_operations_observations_carry_no_record_content(world, caplog):
    lk.run_operations_sweep(world, caplog)


def test_requests_under_test_use_the_restricted_runtime_role(
    world, runtime_engine, postgres_engine
):
    """The clients above are served by ``runtime_engine``; show that engine is the restricted role,
    that the provisioning engine is a different, privileged role, and that a request made by this
    harness reaches the database through the runtime role."""
    assert world.env.label == "postgres-runtime"
    with postgres_engine.connect() as privileged:
        assert privileged.scalar(text("SELECT current_user")) != ROLE
        assert privileged.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user"))
    with runtime_engine.connect() as runtime:
        assert runtime.scalar(text("SELECT current_user")) == ROLE
        assert not runtime.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user"))
    with runtime_engine.connect() as runtime, pytest.raises(DBAPIError):
        runtime.execute(text("SELECT count(*) FROM audit_events"))  # runtime has no audit SELECT
    statements, roles = [], set()

    def count(connection, cursor, statement, *rest):
        statements.append(statement)
        roles.add(connection.engine.url.username)

    event.listen(runtime_engine, "before_cursor_execute", count)
    try:
        adapter = lk.ADAPTERS["tasks"]
        record = lk.make(world, adapter, lk.OWNER, adapter.private_scope, lk.mark("role-"))
        assert adapter.read(world.callers[lk.OWNER], record).status_code == 200
    finally:
        event.remove(runtime_engine, "before_cursor_execute", count)
    assert any("tasks" in statement for statement in statements)
    assert roles == {ROLE}
