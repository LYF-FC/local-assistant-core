"""Explicit bounded selections and current review are required before connection."""

import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app import restore_execution as recovery


def values():
    return {
        "restored_database": "butler_test_restore",
        "operator_id": uuid4(),
        "scope_key": "household_shared",
        "approval_ids": (uuid4(),),
    }


@pytest.mark.parametrize(
    "change",
    [
        {"restored_database": ""},
        {"restored_database": "db;drop"},
        {"scope_key": "unknown"},
        {"approval_ids": ()},
        {"approval_ids": tuple(sorted(uuid4() for _ in range(26)))},
        {
            "approval_ids": tuple(sorted(uuid4() for _ in range(13))),
            "job_ids": tuple(sorted(uuid4() for _ in range(13))),
        },
        {"decision": "quarantine_restored_execution"},
        {"reviewed_hash": "a" * 64},
        {"issued_at": datetime(2026, 1, 1)},
        {"decision": "execute"},
        {"extra": "unexpected"},
    ],
)
def test_invalid_request(change):
    with pytest.raises(ValueError):
        recovery.Request(**(values() | change))


def test_selection_uniqueness_order_and_exact_apply():
    first, second = sorted((uuid4(), uuid4()))
    for selected in ((first, first), (second, first)):
        with pytest.raises(ValueError):
            recovery.Request(**(values() | {"approval_ids": selected}))
    request = recovery.Request(
        **values(),
        issued_at=datetime.now(UTC),
        reviewed_hash="a" * 64,
        decision="quarantine_restored_execution",
    )
    assert request.decision == "quarantine_restored_execution"


def test_cli_empty_selection_never_connects(monkeypatch, capsys):
    monkeypatch.setattr(recovery, "validate_target", lambda _: None)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Invalid selection reached database")

    monkeypatch.setattr(recovery.psycopg, "connect", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore_execution",
            "--environment",
            "test",
            "--restored-database",
            "butler_test",
            "--operator",
            str(uuid4()),
            "--scope",
            "household_shared",
        ],
    )
    with pytest.raises(SystemExit) as error:
        recovery.main()
    assert error.value.code == 1 and not capsys.readouterr().out
