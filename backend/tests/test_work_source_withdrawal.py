"""Source withdrawal requires a bounded explicit selection and review authority."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.work_source_withdrawal import Request


def request(**changes):
    return Request(
        **(
            {
                "database": "butler_test",
                "operator_id": uuid4(),
                "workspace_id": uuid4(),
                "source_ids": (UUID(int=1),),
            }
            | changes
        )
    )


@pytest.mark.parametrize(
    "sources",
    [
        (),
        (UUID(int=2), UUID(int=1)),
        (UUID(int=1), UUID(int=1)),
        tuple(UUID(int=n) for n in range(1, 12)),
        ("bad",),
    ],
)
def test_invalid_source_selection(sources):
    with pytest.raises(ValueError):
        request(source_ids=sources)


@pytest.mark.parametrize(
    "changes",
    [
        {"database": "db;drop table x"},
        {"decision": "withdraw_sources"},
        {"decision": "withdraw_sources", "issued_at": datetime.now(UTC)},
        {"reviewed_hash": "a" * 64},
        {"issued_at": datetime.now()},
        {"extra": "ignored"},
    ],
)
def test_invalid_review(changes):
    with pytest.raises(ValueError):
        request(**changes)


def test_explicit_typed_apply():
    assert request(
        decision="withdraw_sources", issued_at=datetime.now(UTC), reviewed_hash="a" * 64
    ).source_ids == (UUID(int=1),)
