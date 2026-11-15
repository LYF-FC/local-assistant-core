"""Spec 074 Phase C: key-like substring rejection and evidence object-identifier rejection.

Synthetic strings only. Opaque references, tokens and identifiers may not contain a run of 32 or
more hexadecimal characters anywhere (prefix, suffix or middle); the explicit exceptions (Git
commit SHA, manifest hash, fixed-format UUIDs) keep their own validation and are not claimed to be
distinguishable from key material. Evidence records additionally reject archive object names and
bare 32-hex document identifiers in any field, nested or not.
"""

import copy

import pytest
from test_recovery_governance_capacity import evidence
from test_recovery_governance_custody import key_event, register
from test_recovery_governance_hash_record import comparison, entry
from test_recovery_governance_retention import UNDECIDED, destruction, inventory, item

from app.recovery_governance import capacity, custody, hash_record, retention
from app.recovery_governance.common import GovernanceError, is_key_like, is_ref, not_key_like

HEX32 = "0123456789abcdef" * 2
HEX64 = "0123456789abcdef" * 4
OBJECT_NAME = HEX32 + "-v1.original"
VARIANTS = {
    "whole 64": HEX64,
    "prefixed 32": "prefix-" + HEX32,
    "suffixed 32": HEX32 + "-suffix",
    "prefixed 64": "x" + HEX64,
    "suffixed 64": HEX64 + "z",
    "middle 64": "left." + HEX64 + ".right",
    "uppercase prefixed": "p" + HEX32.upper(),
    "33 hex": "a" + HEX32,
}
REJECT = {
    "record_malformed",
    "inventory_invalid",
    "role_register_invalid",
    "key_event_invalid",
    "object_identifier_rejected",
}


def code(call):
    with pytest.raises(GovernanceError) as caught:
        call()
    return caught.value.code


def test_helpers_detect_a_long_hex_run_anywhere_and_keep_short_runs_legitimate():
    for value in VARIANTS.values():
        assert is_key_like(value) and not is_ref(value)
        with pytest.raises(ValueError):
            not_key_like(value)
    for fine in [
        "SYNTHETIC-SET-0001",
        "a" * 31,
        "role-recorder",
        "0123456789abcdef-0123456789abcdef",
        "x" * 64,
    ]:
        assert not is_key_like(fine)
    assert is_ref("a" * 31) and not is_ref("a" * 32) and not is_ref("pre" + "a" * 40)
    assert not is_ref(5) and not is_key_like(None)


@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize(
    "field",
    ["set_id", "recorded_by", "witnessed_by", "approved_by", "approval_process_ref", "schema_head"],
)
def test_hash_record_fields_reject_key_like_substrings(field, variant):
    base = entry(1, approved_by="role-owner", approval_process_ref="process-1")
    base[field] = VARIANTS[variant]
    if field == "recorded_by":
        base["witnessed_by"] = "role-witness"
    assert code(lambda: hash_record.parse_entry(base)) in REJECT


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_comparison_actor_rejects_key_like_substrings(variant):
    assert code(lambda: hash_record.parse_comparison(comparison(who=VARIANTS[variant]))) in REJECT


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_retention_fields_reject_key_like_substrings(variant):
    value = VARIANTS[variant]
    for bad in (
        inventory([item(value)]),
        inventory([item("SET-1", evidence_ref=value)]),
        inventory(
            [item("SET-1")], [{"obligation_ref": value, "applies_to": ["SET-1"], "status": "open"}]
        ),
        inventory(
            [item("SET-1")], [{"obligation_ref": "O", "applies_to": [value], "status": "open"}]
        ),
    ):
        assert code(lambda bad=bad: retention.parse_inventory(bad)) in REJECT
    for field in ("set_id", "authorized_by_ref", "method_ref", "copy_inventory_ref"):
        assert (
            code(lambda f=field: retention.parse_destruction_record(destruction(**{f: value})))
            in REJECT
        )


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_custody_fields_reject_key_like_substrings(variant):
    value = VARIANTS[variant]
    for role in custody.ROLES:
        assert code(lambda r=role: custody.parse_role_register(register(**{r: value}))) in REJECT
    accept = dict(register(), degraded_arrangement_acceptance_ref=value)
    assert code(lambda: custody.parse_role_register(accept)) in REJECT
    for field in ("actor_ref", "ceremony_ref", "fingerprint_record_ref"):
        assert (
            code(lambda f=field: custody.validate_key_events([key_event(1, **{f: value})]))
            in REJECT
        )


EVIDENCE_TEXT_FIELDS = [
    ("run_id",),
    ("tool_output_ref",),
    ("operator",),
    ("reviewer",),
    ("host", "profile_ref"),
    ("host", "kernel"),
    ("host", "os"),
    ("host", "python"),
    ("dataset", "generator"),
    ("dataset", "seed"),
    ("anomalies", 0),
    ("tool_reason_codes", 0),
]


def with_value(path, value):
    entry_ = copy.deepcopy(evidence())
    target = entry_
    for step in path[:-1]:
        target = target[step]
    if path[-1] == 0:  # list fields hold one coded value
        entry_[path[0]] = [value]
    else:
        target[path[-1]] = value
    return entry_


@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("path", EVIDENCE_TEXT_FIELDS, ids=lambda p: ".".join(map(str, p)))
def test_every_evidence_text_field_rejects_key_like_substrings(path, variant):
    value = (
        VARIANTS[variant].lower()
        if path[0] in {"anomalies", "tool_reason_codes"}
        else VARIANTS[variant]
    )
    if path[0] in {"anomalies", "tool_reason_codes"}:
        value = "a_" + value.replace("-", "_").replace(".", "_")  # satisfy the code pattern
    assert code(lambda: capacity.parse_evidence_entry(with_value(path, value))) in REJECT


@pytest.mark.parametrize("path", EVIDENCE_TEXT_FIELDS, ids=lambda p: ".".join(map(str, p)))
@pytest.mark.parametrize(
    "identifier", [OBJECT_NAME, HEX32, "ab" + OBJECT_NAME, OBJECT_NAME + ".bak"]
)
def test_archive_object_names_and_bare_document_ids_cannot_pass_through_any_evidence_field(
    path, identifier
):
    assert (
        code(lambda: capacity.parse_evidence_entry(with_value(path, identifier)))
        == "object_identifier_rejected"
    )


@pytest.mark.parametrize("identifier", [OBJECT_NAME, HEX32])
def test_object_identifiers_are_rejected_in_unknown_keys_and_other_value_positions(identifier):
    extra_key = dict(evidence(), **{identifier: 1})
    assert code(lambda: capacity.parse_evidence_entry(extra_key)) == "object_identifier_rejected"
    nested_key = copy.deepcopy(evidence())
    nested_key["dataset"][identifier] = "x"
    assert code(lambda: capacity.parse_evidence_entry(nested_key)) == "object_identifier_rejected"
    for bad in (
        evidence(date_utc=identifier),
        evidence(git_sha=identifier),
        evidence(cache_state=identifier),
        evidence(disposition=identifier),
    ):
        assert (
            code(lambda bad=bad: capacity.parse_evidence_entry(bad)) == "object_identifier_rejected"
        )


def test_the_explicit_exceptions_keep_their_own_validation():
    assert capacity.parse_evidence_entry(
        evidence(git_sha="0123456789abcdef0123456789abcdef01234567")
    )["valid"]
    assert capacity.parse_evidence_entry(evidence(git_sha="0" * 40))["valid"]
    for bad in ("0" * 39, "0" * 41, "g" * 40, "0" * 40 + "x", "x" + "0" * 40):
        assert code(lambda bad=bad: capacity.parse_evidence_entry(evidence(git_sha=bad))) in REJECT
    assert hash_record.parse_entry(entry(1, digest="f" * 64))  # manifest hash: 64 hex by design
    assert hash_record.parse_entry(entry(1, digest=HEX64))
    assert code(lambda: hash_record.parse_entry(entry(1, digest=HEX64 + "0"))) == "record_malformed"
    assert (
        code(lambda: hash_record.parse_entry(entry(1, digest="x" + HEX64[1:])))
        == "record_malformed"
    )
    assert retention.parse_destruction_record(destruction(manifest_hash=HEX64))["valid"]


def test_legitimate_identifiers_are_still_accepted_everywhere():
    assert capacity.parse_evidence_entry(evidence())["valid"]
    ok = evidence(run_id="RUN-0001", tool_output_ref="output-record-1")
    ok["host"]["kernel"] = "6.1.0-rc1+custom"
    ok["anomalies"] = ["cache_cold", "low_free_space"]
    ok["tool_reason_codes"] = ["set_member_missing"]
    assert capacity.parse_evidence_entry(ok)["valid"]
    assert hash_record.validate_ledger([entry(1, schema_head="SYNTHETIC_HEAD")])["valid"]
    assert retention.parse_policy(UNDECIDED)
    assert custody.parse_role_register(register(primary_custodian="p1"))["status"] == "undecided"
    assert custody.validate_key_events([key_event(1)])["valid"]
    assert is_ref("00000000-0000-4000-8000-000000000000")  # hyphen-split runs are shorter than 32


@pytest.mark.parametrize("identifier", [OBJECT_NAME, HEX32, "ab" + OBJECT_NAME])
def test_object_identifiers_get_the_specific_code_in_ledger_register_and_key_event_records(
    identifier,
):
    assert (
        code(lambda: hash_record.parse_entry(entry(1, set_id=identifier)))
        == "object_identifier_rejected"
    )
    assert (
        code(lambda: hash_record.parse_entry(dict(entry(1), **{identifier: 1})))
        == "object_identifier_rejected"
    )
    assert (
        code(lambda: hash_record.parse_comparison(comparison(who=identifier)))
        == "object_identifier_rejected"
    )
    assert (
        code(lambda: hash_record.validate_ledger([entry(1, set_id=identifier)]))
        == "object_identifier_rejected"
    )
    assert (
        code(lambda: custody.parse_role_register(register(operator=identifier)))
        == "object_identifier_rejected"
    )
    bad_register = dict(register(), degraded_arrangement_acceptance_ref=identifier)
    assert code(lambda: custody.parse_role_register(bad_register)) == "object_identifier_rejected"
    assert (
        code(lambda: custody.validate_key_events([key_event(1, actor_ref=identifier)]))
        == "object_identifier_rejected"
    )
    assert (
        code(lambda: custody.validate_key_events([key_event(1, ceremony_ref=identifier)]))
        == "object_identifier_rejected"
    )
    assert (
        code(lambda: custody.validate_key_events([dict(key_event(1), **{identifier: 1})]))
        == "object_identifier_rejected"
    )
