"""Exact target and deliberate quarantine review are required."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.work_restore import Request


@pytest.mark.parametrize(
    "change",
    [
        {"restored_database": ""},
        {"restored_database": "a" * 64},
        {"restored_database": "db;drop"},
        {"issued_at": datetime(2026, 1, 1)},
        {"decision": "apply"},
        {"decision": "quarantine_restored_workspace"},
        {"reviewed_hash": "a" * 64},
        {
            "decision": "quarantine_restored_workspace",
            "issued_at": datetime.now(UTC),
            "reviewed_hash": "A" * 64,
        },
        {"unknown": "synthetic"},
    ],
)
def test_rejects_ambiguous_target_or_review(change):
    values = {
        "workspace_id": uuid4(),
        "operator_id": uuid4(),
        "restored_database": "butler_test_restore",
    }
    values.update(change)
    with pytest.raises(ValidationError):
        Request(**values)


def test_explicit_preview_and_apply():
    request = Request(
        workspace_id=uuid4(), operator_id=uuid4(), restored_database="butler_test_restore"
    )
    assert request.decision == "preview"
    applied = Request(
        **request.model_dump(exclude={"decision", "issued_at", "reviewed_hash"}),
        decision="quarantine_restored_workspace",
        issued_at=datetime.now(UTC),
        reviewed_hash="a" * 64,
    )
    assert applied.reviewed_hash == "a" * 64
