"""Actual refusal on a nonmatching scope contract leaves the runtime role untouched."""

import pytest
from sqlalchemy import text

from app.runtime_role import configure

pytestmark = pytest.mark.integration


def test_public_namespace_refusal_is_read_only_before_role_changes(postgres_engine, runtime_engine):
    with postgres_engine.connect() as db:
        transaction = db.begin()
        try:
            before = db.execute(
                text(
                    "SELECT xmin::text,rolsuper,rolcreaterole,rolcanlogin FROM pg_authid WHERE rolname='butler_runtime'"
                )
            ).one()
            db.execute(
                text(
                    "UPDATE scopes SET key='synthetic-other-namespace' WHERE key='member_a_private'"
                )
            )
            with pytest.raises(ValueError, match="fresh generic-scope database"):
                configure(
                    db.connection.driver_connection,
                    "synthetic-other-runtime-password-only-0123456789",
                )
            after = db.execute(
                text(
                    "SELECT xmin::text,rolsuper,rolcreaterole,rolcanlogin FROM pg_authid WHERE rolname='butler_runtime'"
                )
            ).one()
            assert before == after
        finally:
            transaction.rollback()


def test_migration_namespace_refusal_prevents_destructive_downgrade(
    postgres_engine, runtime_engine
):
    import subprocess
    from pathlib import Path

    with postgres_engine.begin() as db:
        version = db.scalar(text("SELECT version_num FROM alembic_version"))
        scope_count = db.scalar(text("SELECT count(*) FROM scopes"))
        db.execute(
            text("UPDATE scopes SET key='synthetic-other-namespace' WHERE key='member_a_private'")
        )
    try:
        result = subprocess.run(
            ["alembic", "downgrade", "base"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0 and "namespace mismatch" in result.stderr
        with postgres_engine.connect() as db:
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == version
            assert db.scalar(text("SELECT count(*) FROM scopes")) == scope_count
    finally:
        with postgres_engine.begin() as db:
            db.execute(
                text(
                    "UPDATE scopes SET key='member_a_private' WHERE key='synthetic-other-namespace'"
                )
            )
