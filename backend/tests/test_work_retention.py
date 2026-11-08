"""Retention commands require deliberate bounded, aware review bindings."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.work_retention import Request


@pytest.mark.parametrize(
    "change",
    [
        {"limit": 0},
        {"limit": 26},
        {"limit": True},
        {"limit": "2"},
        {"cutoff": datetime(2026, 1, 1)},
        {"decision": "apply"},
        {"decision": "apply_expired_cleanup"},
        {"reviewed_hash": "a" * 64},
        {
            "decision": "apply_expired_cleanup",
            "cutoff": datetime.now(UTC),
            "reviewed_hash": "A" * 64,
        },
        {"unexpected": "synthetic"},
    ],
)
def test_rejects_ambiguous_or_unbounded_commands(change):
    with pytest.raises(ValidationError):
        Request(workspace_id=uuid4(), operator_id=uuid4(), **change)


def test_explicit_reviewed_apply_and_preview():
    request = Request(workspace_id=uuid4(), operator_id=uuid4())
    assert request.decision == "preview" and request.limit == 25
    applied = Request(
        **request.model_dump(exclude={"decision", "cutoff", "reviewed_hash"}),
        decision="apply_expired_cleanup",
        cutoff=datetime.now(UTC),
        reviewed_hash="a" * 64,
    )
    assert applied.reviewed_hash == "a" * 64
