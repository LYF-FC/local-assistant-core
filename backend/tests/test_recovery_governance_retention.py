"""Spec 074 Phase C, C3: retention policy and report-only reconciliation. Synthetic only."""

import copy
import json
import os

import pytest

from app.recovery_governance.common import GovernanceError, read_json_file
from app.recovery_governance.retention import (
    ARTIFACT_CLASSES,
    RESTORE_ELIGIBILITY,
    parse_destruction_record,
    parse_inventory,
    parse_policy,
    reconcile,
)

UNDECIDED = {"schema_version": 1, "periods": {name: "undecided" for name in ARTIFACT_CLASSES}}
H = "0" * 64


def policy(**periods):
    value = copy.deepcopy(UNDECIDED)
    value["periods"].update(periods)
    return value


def item(identifier, klass="recovery_set", created="2026-01-01", state="active", **extra):
    base = {
        "artifact_id": identifier,
        "artifact_class": klass,
        "created_on": created,
        "state": state,
    }
    base.update(extra)
    return base


def inventory(items, obligations=()):
    return {"schema_version": 1, "items": list(items), "obligations": list(obligations)}


def code(call):
    with pytest.raises(GovernanceError) as caught:
        call()
    return caught.value.code


def run(pol, inv, as_of="2026-06-01"):
    items, obligations = parse_inventory(inv)
    return reconcile(parse_policy(pol), items, obligations, as_of)


def test_every_period_may_remain_undecided_and_nothing_is_decided_by_default():
    parsed = parse_policy(UNDECIDED)
    assert parsed == {name: None for name in ARTIFACT_CLASSES}
    report = run(UNDECIDED, inventory([item("SET-1")]))
    assert report["items"][0]["status"] == "undecided_period"
    assert report["actions_taken"] == "none"


def test_missing_unknown_and_malformed_periods_are_rejected_never_defaulted():
    missing = copy.deepcopy(UNDECIDED)
    del missing["periods"]["manifest"]
    assert code(lambda: parse_policy(missing)) == "policy_class_missing"
    extra = policy()
    extra["periods"]["new_class"] = "undecided"
    assert code(lambda: parse_policy(extra)) == "policy_class_unknown"
    for bad in [
        {"days": 0},
        {"days": -1},
        {"days": True},
        {"days": 36501},
        {"days": "30"},
        30,
        "30d",
        {"d": 1},
        None,
    ]:
        assert (
            code(lambda bad=bad: parse_policy(policy(recovery_set=bad))) == "policy_period_invalid"
        )
    assert (
        code(lambda: parse_policy({"schema_version": 2, "periods": {}})) == "policy_period_invalid"
    )
    assert code(lambda: parse_policy([])) == "policy_period_invalid"


def test_elapsed_period_means_owner_review_only_never_deletion():
    pol = policy(recovery_set={"days": 30}, manifest={"days": 400})
    report = run(pol, inventory([item("SET-1"), item("MAN-1", klass="manifest")]))
    status = {entry["artifact_id"]: entry["status"] for entry in report["items"]}
    assert status == {"MAN-1": "within_retention", "SET-1": "period_elapsed_owner_review_required"}
    assert "delete" not in json.dumps(report).replace("no_deletion", "")
    assert report["actions_taken"] == "none"


def test_restore_eligibility_is_never_established_for_sets_and_manifests():
    pol = policy(recovery_set={"days": 1}, manifest={"days": 1})
    for state in ("active", "superseded"):
        report = run(pol, inventory([item("SET-1", state=state), item("MAN-1", klass="manifest")]))
        for entry in report["items"]:
            assert entry["restore_eligibility"] == RESTORE_ELIGIBILITY
        assert report["blockers"] == ["doc_x02_open"]
    other = run(UNDECIDED, inventory([item("REC-1", klass="expected_hash_record")]))
    assert "restore_eligibility" not in other["items"][0]


def test_open_forgetting_obligation_takes_precedence_and_closed_ones_need_evidence():
    pol = policy(recovery_set={"days": 1})
    obligation = {"obligation_ref": "OBL-1", "applies_to": ["SET-1"], "status": "open"}
    assert (
        run(pol, inventory([item("SET-1")], [obligation]))["items"][0]["status"]
        == "forgetting_obligation_open"
    )
    closed = dict(obligation, status="closed")
    assert (
        code(lambda: parse_inventory(inventory([item("SET-1")], [closed]))) == "inventory_invalid"
    )
    closed["evidence_ref"] = "EVID-1"
    assert parse_inventory(inventory([item("SET-1")], [closed]))


def test_expired_or_destroyed_without_evidence_is_flagged():
    report = run(
        UNDECIDED,
        inventory(
            [
                item("A", state="destroyed"),
                item("B", state="destroyed", evidence_ref="E-1"),
                item("C", state="expired"),
            ]
        ),
    )
    status = {entry["artifact_id"]: entry["status"] for entry in report["items"]}
    assert status == {
        "A": "recorded_without_evidence",
        "B": "recorded_destroyed",
        "C": "recorded_without_evidence",
    }


@pytest.mark.parametrize(
    "bad",
    [
        inventory([item("SET-1"), item("SET-1")]),
        inventory([item("SET-1", created="2026-13-01")]),
        inventory([item("SET-1", state="deleted")]),
        inventory([item("SET-1", klass="backup")]),
        inventory([item("a b")]),
        {"schema_version": 1, "items": "x"},
        {"schema_version": 2, "items": []},
        {"schema_version": 1, "items": [], "extra": 1},
        inventory(
            [item("SET-1")], [{"obligation_ref": "O", "applies_to": ["NOPE"], "status": "open"}]
        ),
        inventory([item("SET-1")], [{"obligation_ref": "O", "applies_to": [], "status": "open"}]),
    ],
)
def test_malformed_inventories_are_rejected(bad):
    assert code(lambda: parse_inventory(bad)) == "inventory_invalid"


def test_archive_object_names_and_bare_document_ids_are_rejected_everywhere():
    object_name = "0123456789abcdef0123456789abcdef-v1.original"
    bare = "0123456789abcdef0123456789abcdef"
    assert (
        code(lambda: parse_inventory(inventory([item(object_name)])))
        == "object_identifier_rejected"
    )
    assert code(lambda: parse_inventory(inventory([item(bare)]))) == "object_identifier_rejected"
    obligation = {"obligation_ref": object_name, "applies_to": ["SET-1"], "status": "open"}
    assert (
        code(lambda: parse_inventory(inventory([item("SET-1")], [obligation])))
        == "object_identifier_rejected"
    )


def test_bad_as_of_date_is_rejected():
    items, obligations = parse_inventory(inventory([item("SET-1")]))
    assert (
        code(lambda: reconcile(parse_policy(UNDECIDED), items, obligations, "2026-02-30"))
        == "inventory_invalid"
    )
    assert (
        code(lambda: reconcile(parse_policy(UNDECIDED), items, obligations, "soon"))
        == "inventory_invalid"
    )


def destruction(**extra):
    base = {
        "record_id": "22222222-2222-4222-8222-222222222222",
        "set_id": "SYNTHETIC-SET-0001",
        "manifest_hash": H,
        "destroyed_on": "2026-03-01",
        "authorized_by_ref": "authority-1",
        "method_ref": "method-1",
        "copy_inventory_ref": "inventory-1",
    }
    base.update(extra)
    return base


def test_destruction_record_validates_without_performing_or_authorizing_anything():
    result = parse_destruction_record(destruction())
    assert result["valid"] and "no_deletion_performed" in result["note"]


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"set_id": "0123456789abcdef0123456789abcdef-v2.original"}, "object_identifier_rejected"),
        ({"set_id": "0123456789abcdef0123456789abcdef"}, "object_identifier_rejected"),
        ({"manifest_hash": "xyz"}, "record_malformed"),
        ({"record_id": "nope"}, "record_malformed"),
        ({"destroyed_on": "2026-99-99"}, "record_malformed"),
        ({"method_ref": ""}, "record_malformed"),
        ({"free_text": "note"}, "record_malformed"),
    ],
)
def test_destruction_record_negative_cases(change, expected):
    assert code(lambda: parse_destruction_record(destruction(**change))) == expected


def test_file_loader_is_bounded_read_only_and_refuses_links_and_non_files(tmp_path):
    good = tmp_path / "policy.json"
    good.write_text(json.dumps(UNDECIDED))
    before = good.read_bytes()
    assert read_json_file(str(good)) == UNDECIDED
    assert good.read_bytes() == before
    link = tmp_path / "link.json"
    os.symlink(good, link)
    assert code(lambda: read_json_file(str(link))) == "input_unreadable"
    assert code(lambda: read_json_file(str(tmp_path))) == "input_unreadable"
    assert code(lambda: read_json_file(str(tmp_path / "missing.json"))) == "input_unreadable"
    big = tmp_path / "big.json"
    big.write_text(" " * 100)
    assert code(lambda: read_json_file(str(big), limit=10)) == "input_unreadable"
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe")
    assert code(lambda: read_json_file(str(bad))) == "json_malformed"


@pytest.mark.parametrize("version", [True, 1.0, "1", 0, 2, None])
def test_boolean_and_non_integer_schema_versions_are_rejected(version):
    bad_policy = dict(UNDECIDED, schema_version=version)
    assert code(lambda: parse_policy(bad_policy)) == "policy_period_invalid"
    bad_inventory = dict(inventory([item("SET-1")]), schema_version=version)
    assert code(lambda: parse_inventory(bad_inventory)) == "inventory_invalid"


@pytest.mark.parametrize("value", ["0123456789abcdef" * 4, "0123456789abcdef" * 2, "A" * 40])
def test_key_like_references_are_rejected_in_every_reference_field(value):
    rejected = {"inventory_invalid", "object_identifier_rejected"}
    assert code(lambda: parse_inventory(inventory([item(value)]))) in rejected
    with_evidence = inventory([item("SET-1", evidence_ref=value)])
    assert code(lambda: parse_inventory(with_evidence)) in rejected
    obligation = {"obligation_ref": value, "applies_to": ["SET-1"], "status": "open"}
    assert code(lambda: parse_inventory(inventory([item("SET-1")], [obligation]))) in rejected
    assert code(lambda: parse_destruction_record(destruction(method_ref=value))) in {
        "record_malformed",
        "object_identifier_rejected",
    }


def test_reports_state_that_references_are_format_checked_not_verified():
    report = run(UNDECIDED, inventory([item("SET-1")]))
    assert report["references"] == "format_checked_only_not_verified"
    assert (
        parse_destruction_record(destruction())["authority_verification"]
        == "not_performed_by_this_package"
    )
