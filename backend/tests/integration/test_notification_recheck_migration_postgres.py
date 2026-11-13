"""Migration 0036 against real PostgreSQL: one transition is added and nothing else is loosened.

The notification guard must accept an inconclusive-lookup recheck (``unknown`` -> ``unknown`` with
the next revision) and keep refusing every other mutation it refused under 0032. Downgrading must
restore the 0032 function body exactly.
"""

import re
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_notification_restart_postgres import retire
from test_notifications_postgres import enqueued

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
VERSIONS = BACKEND / "alembic" / "versions"
FUNCTION = re.compile(
    r"CREATE (?:OR REPLACE )?FUNCTION public\.butler_seal_notification\(\).*?AS \$\$(.*?)\$\$;",
    re.DOTALL,
)
PREVIOUS, CURRENT = "0035_calendar_provider_sync", "0036_notification_recheck"


SEALED = "Notification identity or revision is sealed"
STILL_REFUSED = {  # each refusal is for the intended rule, not an incidental constraint
    "no_revision_bump": SEALED,
    "revision_skip": SEALED,
    "identity_change": SEALED,
    "attempts_decrease_or_jump": SEALED,
    "time_backwards": SEALED,
    "delete": "Notification deletion is sealed",
    "terminal_to_unknown": "Invalid notification transition",
    "terminal_to_terminal": "Invalid notification transition",
}


def migrate(*args):
    result = subprocess.run(
        ["alembic", *args], cwd=BACKEND, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def deployed_body(admin):
    with admin() as db:
        return db.execute(
            text("SELECT prosrc FROM pg_proc WHERE proname='butler_seal_notification'")
        ).scalar_one()


def declared_body(name):
    return FUNCTION.search((VERSIONS / name).read_text()).group(1)


def update(db, identifier, **values):
    assignments = ", ".join(f"{column}=:{column}" for column in values)
    db.execute(
        text(f"UPDATE notification_deliveries SET {assignments} WHERE id=:id"),
        {"id": identifier, **values},
    )


def refused(db, identifier, **values):
    try:
        with db.begin_nested():
            update(db, identifier, **values)
    except DBAPIError as error:
        return str(error.orig).splitlines()[0]
    return None


def exercise(admin, row):
    """Return what the guard accepts/refuses; every change is rolled back."""
    outcome = {}
    with admin() as db:
        db.execute(text("SELECT 1"))
        current = db.execute(
            text("SELECT revision, updated_at FROM notification_deliveries WHERE id=:i"),
            {"i": row.id},
        ).one()
        later = current.updated_at + timedelta(seconds=1)
        # pending -> unknown is the established claim-reaping transition
        update(
            db,
            row.id,
            state="unknown",
            reason="ambiguous_outcome",
            attempt_started_at=None,
            next_attempt_at=later,
            revision=current.revision + 1,
            updated_at=later,
        )
        revision = current.revision + 1
        outcome["recheck"] = refused(
            db,
            row.id,
            reason="ambiguous_outcome",
            next_attempt_at=later,
            revision=revision + 1,
            updated_at=later,
        )
        if outcome["recheck"] is None:
            revision += 1
        outcome["no_revision_bump"] = refused(db, row.id, next_attempt_at=later)
        outcome["revision_skip"] = refused(db, row.id, revision=revision + 2, updated_at=later)
        outcome["identity_change"] = refused(
            db, row.id, recipient_ref="someone-else", revision=revision + 1, updated_at=later
        )
        outcome["attempts_decrease_or_jump"] = refused(
            db, row.id, attempts=2, revision=revision + 1, updated_at=later
        )
        outcome["time_backwards"] = refused(
            db, row.id, revision=revision + 1, updated_at=current.updated_at
        )
        outcome["delete"] = None
        try:
            with db.begin_nested():
                db.execute(text("DELETE FROM notification_deliveries WHERE id=:i"), {"i": row.id})
        except DBAPIError as error:
            outcome["delete"] = str(error.orig).splitlines()[0]
        # terminal states stay terminal: delivered -> unknown and delivered -> delivered
        update(
            db,
            row.id,
            state="delivered",
            reason=None,
            attempt_started_at=None,
            next_attempt_at=None,
            resolved_at=later,
            revision=revision + 1,
            updated_at=later,
        )
        revision += 1
        outcome["terminal_to_unknown"] = refused(
            db,
            row.id,
            state="unknown",
            reason="ambiguous_outcome",
            resolved_at=None,
            next_attempt_at=later,
            revision=revision + 1,
            updated_at=later,
        )
        outcome["terminal_to_terminal"] = refused(
            db, row.id, state="delivered", revision=revision + 1, updated_at=later
        )
        db.rollback()
    return outcome


def test_0036_allows_only_the_recheck_and_downgrade_restores_0032_exactly(
    scenario, runtime_engine, monkeypatch
):
    _, admin, _, _, row = enqueued(runtime_engine, scenario, monkeypatch)
    try:
        assert deployed_body(admin) == declared_body("0036_notification_recheck.py")
        after = exercise(admin, row)
        assert after["recheck"] is None, "0036 must accept unknown -> unknown (next revision)"
        assert {k: v for k, v in after.items() if k != "recheck"} == STILL_REFUSED

        migrate("downgrade", PREVIOUS)
        assert deployed_body(admin) == declared_body("0032_notification_delivery.py")
        before = exercise(admin, row)
        assert before["recheck"] == "Invalid notification transition"
        assert {k: v for k, v in before.items() if k != "recheck"} == STILL_REFUSED
    finally:
        migrate("upgrade", "head")
        retire(admin, [row.id])
    assert deployed_body(admin) == declared_body("0036_notification_recheck.py")
