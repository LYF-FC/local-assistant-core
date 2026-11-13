"""Portable schema tests: SQLite create_all, migration literals versus the shared code module."""

import importlib.util
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import calendar_codes as codes
from app import models
from app.db import Base

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
MIGRATION = VERSIONS / "0035_calendar_provider_sync.py"
NEW_TABLES = {
    "calendar_provider_links",
    "calendar_series",
    "calendar_overrides",
    "calendar_changes",
    "calendar_sync_state",
}


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("migration_0035", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_literals_equal_the_shared_code_lists(migration):
    assert migration.BLOCKED_REASONS == codes.BLOCKED_REASONS
    assert migration.LAST_ERROR_CODES == codes.LAST_ERROR_CODES
    assert migration.TOMBSTONE_HASH == codes.TOMBSTONE_HASH
    assert len(set(migration.BLOCKED_REASONS)) == len(migration.BLOCKED_REASONS)
    # the rendered check constraint really contains every code, and nothing else
    rendered = migration.TABLES
    block = re.search(r"blocked_reason IN \(([^)]*)\)", rendered).group(1)
    assert re.findall(r"'([a-z_]+)'", block) == list(codes.BLOCKED_REASONS)
    error = re.search(r"last_error_code IN \(([^)]*)\)", rendered).group(1)
    assert re.findall(r"'([a-z_]+)'", error) == list(codes.LAST_ERROR_CODES)
    assert f"content_hash = '{codes.TOMBSTONE_HASH}'" in rendered


def test_migration_has_the_expected_revision_and_no_application_imports(migration):
    assert migration.revision == "0035_calendar_provider_sync"
    assert migration.down_revision == "0034_invoice_filing_execution"
    source = MIGRATION.read_text()
    assert not re.search(r"^\s*(from|import)\s+app\b", source, re.MULTILINE)
    assert set(migration.SEALED_TABLES) == NEW_TABLES


def test_migration_is_the_single_head():
    revisions = {}
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        match = re.search(r'^revision = "([^"]+)"', text, re.MULTILINE)
        down = re.search(r'^down_revision = "?([^"\n]+)"?', text, re.MULTILINE)
        if match:
            revisions[match.group(1)] = down.group(1) if down else None
    heads = set(revisions) - {value for value in revisions.values() if value}
    assert heads == {"0036_notification_recheck"}


def test_model_constraints_exist_in_the_migration(migration):
    sql = migration.TABLES
    for name in NEW_TABLES:
        table = Base.metadata.tables[name]
        for constraint in table.constraints:
            if constraint.name:
                assert constraint.name in sql, (name, constraint.name)
        for index in table.indexes:
            assert index.name in sql, (name, index.name)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    assert NEW_TABLES <= set(inspect(engine).get_table_names())
    with Session(engine) as session:
        yield session
    engine.dispose()


def row_values(**extra):
    now = datetime.now(UTC)
    return {"created_at": now, "updated_at": now, "revision": 1, **extra}


def seed_series(db, **extra):
    owner, source = uuid4(), uuid4()
    series = models.CalendarSeries(
        id=uuid4(),
        source_id=source,
        owner_id=owner,
        scope_key="household_shared",
        uid="u1",
        state="active",
        kind="timed",
        status="confirmed",
        sequence=1,
        title="Synthetic",
        zone="Europe/Paris",
        duration_seconds=3600,
        exdates=[],
        rdates=[],
        **row_values(),
    )
    for key, value in extra.items():
        setattr(series, key, value)
    series.start_local = series.start_local or datetime(2026, 3, 15, 9)
    return series


def test_sqlite_create_all_accepts_valid_rows_and_enforces_the_portable_checks(db):
    db.add(seed_series(db))
    db.flush()
    for bad in (
        {"state": "deleted"},  # content present on a tombstone, no deleted_at
        {"kind": "all_day"},  # timed columns on an all-day series
        {"sequence": -1},
        {"duration_seconds": 2_678_401},
        {"uid": None},
        {"scope_key": "elsewhere"},
        {"title": "   "},
    ):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(seed_series(db, **bad))
            db.flush()


def test_the_override_cascade_flag_check_is_portable(db):
    now = datetime.now(UTC)
    base = {
        "id": uuid4(),
        "series_id": uuid4(),
        "source_id": uuid4(),
        "owner_id": uuid4(),
        "scope_key": "household_shared",
        "recurrence_id": "2026-03-22T09:00:00",
        "sequence": 1,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
    }
    # cascade flag on an active row
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            models.CalendarOverride(
                **base, state="active", status="confirmed", deleted_by_cascade=True
            )
        )
        db.flush()
