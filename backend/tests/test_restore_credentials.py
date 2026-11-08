"""Credential recovery contracts reject ambiguous authority before database access."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.restore_credentials import Request


def request(**changes):
    return Request(
        **(
            {
                "restored_database": "butler_test_restore",
                "operator_id": uuid4(),
                "workspace_id": uuid4(),
                "namespace_oids": [1],
            }
            | changes
        )
    )


@pytest.mark.parametrize(
    "oids", [[2, 1], [1, 1], [0], [-1], [4294967296], list(range(1, 12)), [True], ["1"]]
)
def test_invalid_selection(oids):
    with pytest.raises(ValueError):
        request(namespace_oids=oids)


@pytest.mark.parametrize(
    "changes",
    [
        {"restored_database": "db;DROP ROLE x"},
        {"decision": "revoke_restored_credentials"},
        {"decision": "revoke_restored_credentials", "issued_at": datetime.now(UTC)},
        {"reviewed_hash": "a" * 64},
        {"issued_at": datetime.now()},
        {"extra": "ignored"},
    ],
)
def test_invalid_authority(changes):
    with pytest.raises(ValueError):
        request(**changes)


def test_explicit_apply_contract():
    assert request(
        decision="revoke_restored_credentials", issued_at=datetime.now(UTC), reviewed_hash="a" * 64
    ).namespace_oids == [1]


def test_inventory_without_selection_grants_no_apply_authority():
    assert request(namespace_oids=[]).namespace_oids == []
    with pytest.raises(ValueError):
        request(
            namespace_oids=[],
            decision="revoke_restored_credentials",
            issued_at=datetime.now(UTC),
            reviewed_hash="a" * 64,
        )
