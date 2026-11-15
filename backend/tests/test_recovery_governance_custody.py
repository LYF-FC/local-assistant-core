"""Spec 074 Phase C, C1 and C5: custody role register and key-event records. Synthetic only.

No key is generated, stored or read; people are never named.
"""

import pytest

from app.recovery_governance import custody
from app.recovery_governance.common import GovernanceError


def code(call):
    with pytest.raises(GovernanceError) as caught:
        call()
    return caught.value.code


def register(**roles):
    base = {role: None for role in custody.ROLES}
    base.update(roles)
    return {"schema_version": 1, "assignments": base, "degraded_arrangement_acceptance_ref": None}


def test_unassigned_register_is_undecided_and_names_no_one():
    report = custody.parse_role_register(register())
    assert report["status"] == "undecided" and report["key_holders_at_rest"] == []
    assert set(report["undecided_roles"]) == set(custody.ROLES)


def test_distinct_register_lists_both_custodians_as_key_holders_and_no_independence():
    full = register(
        primary_custodian="p1", recovery_custodian="p2", operator="p3", record_keeper="p4"
    )
    report = custody.parse_role_register(full)
    assert report["status"] == "complete_distinct" and report["conflicts"] == []
    assert report["key_holders_at_rest"] == ["p1", "p2"]
    assert report["operator_key_access"] == "temporary_during_authorized_session_only"
    assert (
        "every_key_holder_can_forge" in report["note"] and "not_non_repudiation" in report["note"]
    )
    assert "p3" not in report["key_holders_at_rest"]
    assert custody.key_holders(full) == {"p1", "p2"}


def test_conflicting_roles_are_degraded_until_the_owner_reference_is_given():
    shared = register(
        primary_custodian="p1", recovery_custodian="p1", operator="p3", record_keeper="p4"
    )
    assert custody.parse_role_register(shared)["status"] == "degraded_not_accepted"
    keeper_is_holder = register(
        primary_custodian="p1", recovery_custodian="p2", operator="p3", record_keeper="p2"
    )
    report = custody.parse_role_register(keeper_is_holder)
    assert (
        report["status"] == "degraded_not_accepted"
        and ["record_keeper", "recovery_custodian"] in report["conflicts"]
    )
    shared["degraded_arrangement_acceptance_ref"] = "owner-decision-ref"
    assert custody.parse_role_register(shared)["status"] == "degraded_accepted_by_owner_reference"


def test_operator_may_share_an_actor_without_becoming_a_conflict():
    same = register(
        primary_custodian="p1", recovery_custodian="p2", operator="p1", record_keeper="p4"
    )
    assert custody.parse_role_register(same)["status"] == "complete_distinct"


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"schema_version": 1},
        {**register(), "schema_version": 2},
        {**register(), "extra": 1},
        {
            "schema_version": 1,
            "assignments": {"primary_custodian": None},
            "degraded_arrangement_acceptance_ref": None,
        },
        register(primary_custodian="bad value"),
        register(primary_custodian=7),
        {**register(), "degraded_arrangement_acceptance_ref": "bad ref"},
    ],
)
def test_malformed_registers_are_rejected(bad):
    assert code(lambda: custody.parse_role_register(bad)) == "role_register_invalid"


def key_event(number=1, **extra):
    base = {
        "event_id": f"00000000-0000-4000-8000-{number:012d}",
        "event": "released_for_session",
        "key_id": "00000000-0000-4000-8000-00000000000a",
        "key_fingerprint": "0" * 64,
        "installation_id": "11111111-1111-4111-8111-111111111111",
        "occurred_on": "2026-01-01",
        "role": "primary_custodian",
        "actor_ref": "p1",
    }
    base.update(extra)
    return base


def test_key_events_are_metadata_only_and_ordered():
    assert validate_ok([key_event(1), key_event(2, occurred_on="2026-01-02")])["valid"]


def validate_ok(events):
    return custody.validate_key_events(events)


@pytest.mark.parametrize(
    "bad",
    [
        [key_event(1), key_event(1)],
        [key_event(1, occurred_on="2026-02-01"), key_event(2, occurred_on="2026-01-01")],
        [key_event(1, material="0" * 64)],
        [key_event(1, secret="x")],
        [key_event(1, event="exported")],
        [key_event(1, key_fingerprint="g" * 64)],
        [key_event(1, occurred_on="2026-02-30")],
        [key_event(1, role="auditor")],
        "not a list",
    ],
)
def test_key_event_negative_cases(bad):
    assert code(lambda: custody.validate_key_events(bad)) == "key_event_invalid"


def test_key_event_model_has_no_field_that_could_carry_key_material():
    names = set(custody.KeyEventRecord.model_fields)
    assert not {n for n in names if "material" in n or "secret" in n or "key_bytes" in n}


def test_future_operations_interface_is_a_protocol_with_no_implementation():
    from typing import Protocol

    assert Protocol in custody.FutureKeyOperations.__mro__
    assert [n for n in vars(custody.FutureKeyOperations) if not n.startswith("_")] == [
        "record_event"
    ]
