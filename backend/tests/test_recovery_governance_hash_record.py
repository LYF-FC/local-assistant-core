"""Spec 074 Phase C, C2: hash-record ledger validation. Synthetic values only; no key is used."""

import copy

import pytest

from app.recovery_governance.common import GovernanceError, loads_strict
from app.recovery_governance.hash_record import (
    EVIDENCE_CLASS,
    parse_comparison,
    parse_entry,
    validate_ledger,
)

H1 = "0" * 63 + "1"
H2 = "0" * 63 + "2"
KEY = "00000000-0000-4000-8000-000000000000"
INST = "11111111-1111-4111-8111-111111111111"


def entry(number=1, set_id="SYNTHETIC-SET-0001", digest=H1, **extra):
    base = {
        "entry": number,
        "set_id": set_id,
        "manifest_hash": digest,
        "key_id": KEY,
        "installation_id": INST,
        "schema_head": "SYNTHETIC_HEAD",
        "recorded_on": "2026-01-01",
        "recorded_by": "role-recorder",
        "witnessed_by": "role-witness",
        "supersedes": None,
    }
    base.update(extra)
    return base


def comparison(number=1, digest=H1, result="freshness_match", who="holder-a", **extra):
    base = {
        "entry": number,
        "compared_on": "2026-01-02",
        "basis": "key_holder_check",
        "performed_by": who,
        "presented_manifest_hash": digest,
        "result": result,
    }
    base.update(extra)
    return base


def code(call):
    with pytest.raises(GovernanceError) as caught:
        call()
    return caught.value.code


def test_valid_ledger_reports_recording_and_key_holder_checks_separately():
    ledger = [entry(1), entry(2, digest=H2, supersedes=1, recorded_on="2026-01-03")]
    report = validate_ledger(
        ledger, [comparison(1, H1), comparison(2, H1, "freshness_mismatch")], {"holder-a"}
    )
    assert report["valid"] and report["entries"] == 2
    assert report["latest_entry_by_set"] == {"SYNTHETIC-SET-0001": 2}
    assert [c["reference"] for c in report["comparisons"]] == ["superseded", "latest"]
    assert {c["evidence_class"] for c in report["comparisons"]} == {EVIDENCE_CLASS}
    assert "independent" not in str(report["comparisons"]).replace("not_independent", "")


def test_witness_must_differ_from_recorder():
    assert code(lambda: parse_entry(entry(witnessed_by="role-recorder"))) == "witness_not_distinct"


def test_approver_requires_a_defined_process_and_not_the_reverse():
    assert (
        code(lambda: parse_entry(entry(approved_by="role-owner")))
        == "approver_without_defined_process"
    )
    assert code(lambda: parse_entry(entry(approval_process_ref="process-1"))) == "record_malformed"
    assert parse_entry(entry(approved_by="role-owner", approval_process_ref="process-1"))


@pytest.mark.parametrize("key", ["independent", "independently_verified", "Independent_Check"])
def test_any_independence_claim_is_rejected(key):
    assert code(lambda: parse_entry(entry(**{key: True}))) == "independence_claim_rejected"
    assert (
        code(lambda: parse_comparison(comparison(**{key: True}))) == "independence_claim_rejected"
    )


def test_comparison_basis_can_only_be_key_holder_check():
    assert (
        code(lambda: parse_comparison(comparison(basis="independent_verification")))
        == "record_malformed"
    )
    assert (
        code(lambda: parse_comparison(comparison(basis="witnessed_comparison")))
        == "record_malformed"
    )


def test_comparison_by_a_non_key_holder_is_rejected():
    assert (
        code(lambda: validate_ledger([entry(1)], [comparison(who="someone-else")], {"holder-a"}))
        == "comparison_not_key_holder"
    )


def test_comparisons_fail_closed_without_the_key_holder_set():
    assert code(lambda: validate_ledger([entry(1)], [comparison()], None)) == "input_missing"


def test_comparison_results_must_match_the_hashes():
    assert (
        code(lambda: validate_ledger([entry(1)], [comparison(digest=H2)], {"holder-a"}))
        == "comparison_inconsistent"
    )
    mismatch_equal = comparison(digest=H1, result="freshness_mismatch")
    assert (
        code(lambda: validate_ledger([entry(1)], [mismatch_equal], {"holder-a"}))
        == "comparison_inconsistent"
    )
    assert (
        code(lambda: validate_ledger([entry(1)], [comparison(number=9)], {"holder-a"}))
        == "comparison_inconsistent"
    )


def test_not_evaluated_is_allowed_and_states_are_closed():
    ok = comparison(digest=H2, result="freshness_not_evaluated")
    assert (
        validate_ledger([entry(1)], [ok], {"holder-a"})["comparisons"][0]["result"]
        == "freshness_not_evaluated"
    )
    assert (
        code(lambda: parse_comparison(comparison(result="freshness_current"))) == "record_malformed"
    )


def test_sequence_must_be_contiguous_and_dated_in_order():
    assert code(lambda: validate_ledger([entry(2)])) == "ledger_sequence_invalid"
    assert (
        code(lambda: validate_ledger([entry(1), entry(1, set_id="SET-B")]))
        == "ledger_sequence_invalid"
    )
    late = [entry(1, recorded_on="2026-02-01"), entry(2, set_id="SET-B", recorded_on="2026-01-01")]
    assert code(lambda: validate_ledger(late)) == "ledger_sequence_invalid"


def test_supersession_must_chain_within_one_set_without_forks():
    assert (
        code(lambda: validate_ledger([entry(1), entry(2, digest=H2)]))
        == "ledger_supersession_invalid"
    )
    fork = [entry(1), entry(2, digest=H2, supersedes=1), entry(3, digest=H2, supersedes=1)]
    assert code(lambda: validate_ledger(fork)) == "ledger_supersession_invalid"
    cross = [entry(1), entry(2, set_id="SET-B"), entry(3, set_id="SET-B", digest=H2, supersedes=1)]
    assert code(lambda: validate_ledger(cross)) == "ledger_supersession_invalid"
    forward = entry(1, supersedes=1)
    assert code(lambda: parse_entry(forward)) == "record_malformed"


@pytest.mark.parametrize(
    "change",
    [
        {"manifest_hash": "A" * 64},
        {"manifest_hash": "0" * 63},
        {"key_id": "not-a-uuid"},
        {"set_id": "../x"},
        {"recorded_on": "2026-13-40"},
        {"recorded_on": "yesterday"},
        {"entry": 0},
        {"unexpected": 1},
        {"entry": True},
    ],
)
def test_malformed_entries_are_rejected_with_a_closed_code(change):
    assert code(lambda: parse_entry(entry(**change))) == "record_malformed"


def test_non_mapping_and_non_list_inputs_are_rejected():
    assert code(lambda: parse_entry(["x"])) == "record_malformed"
    assert code(lambda: validate_ledger({"entry": 1})) == "record_malformed"


def test_errors_carry_only_a_closed_code_never_input_text():
    secret_like = "SECRET-LOOKING-VALUE-123"
    with pytest.raises(GovernanceError) as caught:
        parse_entry(entry(set_id=secret_like + "/"))
    assert secret_like not in str(caught.value) and str(caught.value) == "record_malformed"


def test_json_loader_rejects_duplicate_keys_and_non_finite_numbers():
    assert code(lambda: loads_strict('{"a": 1, "a": 2}')) == "json_malformed"
    assert code(lambda: loads_strict('{"a": NaN}')) == "json_malformed"
    assert code(lambda: loads_strict("{")) == "json_malformed"
    assert loads_strict('{"a": 1}') == {"a": 1}


def test_entries_are_not_mutated_by_validation():
    ledger = [entry(1)]
    before = copy.deepcopy(ledger)
    validate_ledger(ledger)
    assert ledger == before


def test_the_comparison_model_cannot_express_any_basis_but_a_key_holder_check():
    from typing import get_args

    from app.recovery_governance.hash_record import FRESHNESS_STATES, ComparisonEvent

    assert get_args(ComparisonEvent.model_fields["basis"].annotation) == ("key_holder_check",)
    assert get_args(ComparisonEvent.model_fields["result"].annotation) == FRESHNESS_STATES


def approved(number=1, process="process-1", **extra):
    return entry(number, approved_by="role-owner", approval_process_ref=process, **extra)


def test_approval_process_reference_is_format_checked_only_and_never_authority():
    report = validate_ledger([approved()])
    assert report["approvals"] == [
        {
            "entry": 1,
            "approval_process": "reference_unverified",
            "authority_verification": "not_performed_by_this_package",
        }
    ]
    assert (
        validate_ledger([approved()], verified_approval_processes={"other"})["approvals"][0][
            "approval_process"
        ]
        == "reference_unverified"
    )


def test_only_a_process_the_caller_states_was_verified_is_reported_as_such():
    report = validate_ledger([approved()], verified_approval_processes={"process-1"})
    assert report["approvals"][0]["approval_process"] == "reference_caller_verified"
    assert report["approvals"][0]["authority_verification"] == "not_performed_by_this_package"


def test_entries_without_an_approver_report_no_approval():
    assert validate_ledger([entry(1)])["approvals"] == []


@pytest.mark.parametrize(
    "field", ["recorded_by", "witnessed_by", "set_id", "approved_by", "approval_process_ref"]
)
def test_key_like_values_are_not_accepted_as_references(field):
    base = entry(1, approved_by="role-owner", approval_process_ref="process-1")
    base[field] = "0123456789abcdef" * 4
    assert code(lambda: parse_entry(base)) == "record_malformed"


def test_comparison_actor_may_not_be_key_like():
    assert (
        code(lambda: parse_comparison(comparison(who="0123456789abcdef" * 2 + "ab")))
        == "record_malformed"
    )


def test_the_manifest_hash_field_is_the_documented_residual_limitation():
    # A 64-hex manifest hash is required by design and cannot be told apart from key material by
    # syntax; this test pins that the field exists and stays the only 64-hex typed field.
    from app.recovery_governance.hash_record import HashRecordEntry

    assert "manifest_hash" in HashRecordEntry.model_fields
    assert parse_entry(entry(1))
