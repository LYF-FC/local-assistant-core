"""Exercise each recovery downgrade guard even when a later guard blocks first."""

import importlib.util
import subprocess
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from app.config import settings


def assert_downgrade_refused(target, revision, message):
    assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
    backend = Path(__file__).resolve().parents[1]
    blocked = subprocess.run(
        ["alembic", "downgrade", target],
        cwd=backend,
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode != 0 and "evidence exists" in blocked.stderr.lower()
    spec = importlib.util.spec_from_file_location(
        "synthetic_downgrade_guard", backend / "alembic" / "versions" / f"{revision}.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(settings.database_url)
    try:
        with (
            engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
            pytest.raises(RuntimeError, match=message),
        ):
            migration.downgrade()
    finally:
        engine.dispose()
