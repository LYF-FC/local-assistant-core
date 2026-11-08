"""Deliberate target, bounded batch and current exact review are required."""

import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app import restore_sessions as recovery


@pytest.mark.parametrize(
    "change",
    [
        {"restored_database": ""},
        {"restored_database": "db;drop"},
        {"limit": 0},
        {"limit": 101},
        {"limit": True},
        {"limit": "1"},
        {"issued_at": datetime(2026, 1, 1)},
        {"decision": "apply"},
        {"decision": "revoke_restored_sessions"},
        {"reviewed_hash": "a" * 64},
        {"extra": "unexpected"},
    ],
)
def test_invalid_review(change):
    with pytest.raises(ValueError):
        recovery.Request(**({"restored_database": "butler_test", "operator_id": uuid4()} | change))


def test_explicit_apply_and_default_batch():
    request = recovery.Request(
        restored_database="butler_test",
        operator_id=uuid4(),
        issued_at=datetime.now(UTC),
        reviewed_hash="a" * 64,
        decision="revoke_restored_sessions",
    )
    assert request.limit == 100


def test_bad_cli_batch_never_connects(monkeypatch, capsys):
    monkeypatch.setattr(recovery, "validate_target", lambda _: None)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Invalid batch reached database")

    monkeypatch.setattr(recovery.psycopg, "connect", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore_sessions",
            "--environment",
            "test",
            "--restored-database",
            "butler_test",
            "--operator",
            str(uuid4()),
            "--limit",
            "101",
        ],
    )
    with pytest.raises(SystemExit) as error:
        recovery.main()
    assert error.value.code == 1 and not capsys.readouterr().out
