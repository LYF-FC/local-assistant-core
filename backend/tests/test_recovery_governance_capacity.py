"""Spec 074 Phase C, C4: capacity model and evidence-log validation. Nothing is measured or run."""

import json

import pytest

from app.recovery_governance import capacity
from app.recovery_governance.common import GovernanceError

GIB = 1024**3
INUSE = {
    "schema_version": 1,
    "threshold_status": "provisional-unapproved",
    "dump_bytes": 10 * GIB,
    "archive_bytes": 64 * 1024 * 1024,
    "manifest_bytes": 4 * 1024 * 1024,
    "restore_ratio_per_mille": 3000,
    "restore_working_per_mille": 500,
    "margin_per_mille": 200,
    "available_disk_bytes": 200 * GIB,
}


def code(call):
    with pytest.raises(GovernanceError) as caught:
        call()
    return caught.value.code


def test_placeholder_ceiling_is_pinned_to_the_unapproved_phase_b_value():
    from app.recovery_set.format import PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES as phase_b

    assert capacity.PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES == phase_b == 64 * GIB


def test_model_arithmetic_and_labels():
    report = capacity.model(capacity.parse_inputs(INUSE))
    parts = report["components_bytes"]
    assert parts["staged_set"] == 10 * GIB + 64 * 1024 * 1024
    assert parts["restored_database"] == 30 * GIB and parts["restore_working_space"] == 15 * GIB
    subtotal = sum(v for k, v in parts.items() if k != "safety_margin")
    assert parts["safety_margin"] == -(-subtotal * 200 // 1000)
    assert report["required_bytes"] == subtotal + parts["safety_margin"]
    assert (
        report["fits_available_disk_under_assumptions"] is True and report["shortfall_bytes"] == 0
    )
    assert (report["measured"], report["validated"], report["approved"]) == (False, False, False)
    assert report["basis"] == "model_calculation"
    assert report["ceiling"]["status"] == "unapproved_placeholder"


def test_shortfall_and_placeholder_exceeded_are_reported_without_claiming_validity():
    small = dict(INUSE, available_disk_bytes=GIB, dump_bytes=70 * GIB)
    report = capacity.model(capacity.parse_inputs(small))
    assert report["fits_available_disk_under_assumptions"] is False
    assert report["shortfall_bytes"] == report["required_bytes"] - GIB > 0
    assert report["ceiling"]["dump_exceeds_placeholder"] is True
    text = json.dumps(report)
    assert 'validated": true' not in text and 'approved": true' not in text


@pytest.mark.parametrize("name", list(INUSE))
def test_every_input_is_required_and_none_is_defaulted(name):
    partial = {k: v for k, v in INUSE.items() if k != name}
    assert code(lambda: capacity.parse_inputs(partial)) == "input_missing"


@pytest.mark.parametrize(
    "change",
    [
        {"threshold_status": "approved"},
        {"threshold_status": "validated"},
        {"dump_bytes": 0},
        {"dump_bytes": -1},
        {"dump_bytes": 1.5},
        {"dump_bytes": True},
        {"restore_ratio_per_mille": 0},
        {"margin_per_mille": -1},
        {"available_disk_bytes": "100"},
        {"schema_version": 2},
        {"extra": 1},
    ],
)
def test_malformed_or_approval_claiming_inputs_are_rejected(change):
    assert code(lambda: capacity.parse_inputs(dict(INUSE, **change))) in {
        "record_malformed",
        "input_missing",
    }


def test_non_mapping_input_is_rejected():
    assert code(lambda: capacity.parse_inputs([1])) == "record_malformed"


def evidence(**extra):
    base = {
        "run_id": "RUN-0001",
        "date_utc": "2026-01-01T00:00:00Z",
        "git_sha": "0" * 40,
        "env_class": "disposable-nonprod",
        "host": {
            "profile_ref": "host-profile-1",
            "cores": 1,
            "ram_bytes": 1,
            "swap_bytes": 0,
            "kernel": "6.1.0",
            "os": "synthetic-os-1",
            "python": "3.13.0",
        },
        "storage": {
            "device_type": "ssd",
            "fs_type": "ext4",
            "mount_options": ["rw", "noatime"],
            "free_before": 2,
            "free_after": 1,
        },
        "dataset": {
            "size_bytes": 1,
            "generator": "gen-1",
            "seed": "seed-1",
            "sparse": False,
            "entries": 0,
        },
        "cache_state": "unknown",
        "command_shape": "verify",
        "tool_output_ref": "output-record-1",
        "tool_exit_status": 0,
        "tool_reason_codes": [],
        "measurements": {"wall_ms": 1, "peak_rss_bytes": 1, "throughput_bytes_s": 1},
        "anomalies": [],
        "operator": "role-operator",
        "reviewer": "role-reviewer",
        "disposition": "informational",
    }
    base.update(extra)
    return base


def test_evidence_entry_is_informational_only():
    result = capacity.parse_evidence_entry(evidence())
    assert result["classification"] == "informational" and "not an RPO/RTO" in result["statement"]


@pytest.mark.parametrize("env", ["production", "nas", "ci", "", "disposable"])
def test_evidence_from_any_other_environment_is_rejected(env):
    assert (
        code(lambda: capacity.parse_evidence_entry(evidence(env_class=env)))
        == "evidence_environment_rejected"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"disposition": "accepted"},
        {"disposition": "validated"},
        {"unknown": 1},
        {"cache_state": "hot"},
        {"operator": "a b"},
    ],
)
def test_evidence_negative_cases(change):
    assert code(lambda: capacity.parse_evidence_entry(evidence(**change))) == "record_malformed"


def nested(section, **change):
    value = evidence()
    value[section] = dict(value[section], **change)
    return value


KEYLIKE = "0123456789abcdef" * 4


@pytest.mark.parametrize(
    "bad",
    [
        evidence(tool_output_verbatim={"anything": "goes"}),  # the unrestricted dict is gone
        evidence(anomalies=[{"free": "form"}]),
        evidence(anomalies=["free text with spaces"]),
        evidence(anomalies=["Upper"]),
        evidence(anomalies=["a"] * 17),
        evidence(tool_reason_codes=["has space"]),
        evidence(tool_reason_codes=["x"] * 9),
        evidence(tool_exit_status=3),
        evidence(tool_exit_status=True),
        evidence(tool_output_ref=KEYLIKE),
        evidence(tool_output_ref="a b"),
        nested("host", profile_ref=KEYLIKE),
        nested("host", kernel="free text kernel"),
        nested("host", os=KEYLIKE + "!"),
        nested("host", cpu="Intel(R) Xeon(R)"),  # unknown nested field
        nested("host", cores=0),
        nested("host", ram_bytes=2**61),
        nested("storage", fs_type="nfs"),
        nested("storage", device_type="nas"),
        nested("storage", mount_options=["rw", "uid=1000"]),
        nested("storage", mount_options=["rw"] * 9),
        nested("storage", free_after=-1),
        nested("dataset", generator=KEYLIKE),
        nested("dataset", seed=KEYLIKE),
        nested("dataset", entries=-1),
        nested("dataset", note="free text"),
        nested("measurements", wall_ms=2**41),
        nested("measurements", peak_rss_bytes=-1),
        evidence(git_sha="g" * 40),
        evidence(git_sha="0" * 41),
        evidence(git_sha="0" * 39 + "\n"),
    ],
)
def test_evidence_records_are_closed_and_cannot_carry_arbitrary_data(bad):
    assert code(lambda: capacity.parse_evidence_entry(bad)) == "record_malformed"


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-01-01",
        "2026-01-01T00:00:00",
        "2026-01-01 00:00:00Z",
        "2026-13-01T00:00:00Z",
        "2026-01-01T25:00:00Z",
        "yesterday",
        "",
        5,
    ],
)
def test_date_utc_must_be_a_complete_timezone_aware_timestamp(stamp):
    assert (
        code(lambda: capacity.parse_evidence_entry(evidence(date_utc=stamp))) == "record_malformed"
    )


@pytest.mark.parametrize(
    "stamp", ["2026-01-01T00:00:00Z", "2026-01-01T10:30:00+01:00", "2026-01-01T00:00:00.123456Z"]
)
def test_complete_timestamps_are_accepted(stamp):
    assert capacity.parse_evidence_entry(evidence(date_utc=stamp))["valid"]


@pytest.mark.parametrize("version", [True, 1.0, "1", 2, 0, None])
def test_capacity_schema_version_must_be_the_integer_one(version):
    assert (
        code(lambda: capacity.parse_inputs(dict(INUSE, schema_version=version)))
        == "record_malformed"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"restore_ratio_per_mille": capacity.MAX_RATIO_PER_MILLE + 1},
        {"restore_working_per_mille": capacity.MAX_RATIO_PER_MILLE + 1},
        {"margin_per_mille": capacity.MAX_MARGIN_PER_MILLE + 1},
        {"dump_bytes": capacity.MAX_BYTES + 1},
        {"available_disk_bytes": capacity.MAX_BYTES + 1},
        {"archive_bytes": capacity.MAX_BYTES + 1},
    ],
)
def test_inputs_beyond_the_sanity_bounds_are_rejected(change):
    assert code(lambda: capacity.parse_inputs(dict(INUSE, **change))) == "record_malformed"


def test_bounds_are_accepted_exactly_at_the_limit_where_arithmetic_stays_defined():
    edge = dict(INUSE, dump_bytes=2**40, restore_ratio_per_mille=capacity.MAX_RATIO_PER_MILLE)
    report = capacity.model(capacity.parse_inputs(edge))
    assert report["required_bytes"] <= capacity.MAX_MODEL_BYTES


def test_intermediate_arithmetic_that_exceeds_the_model_bound_is_rejected_not_wrapped():
    huge = dict(
        INUSE,
        dump_bytes=capacity.MAX_BYTES,
        restore_ratio_per_mille=capacity.MAX_RATIO_PER_MILLE,
    )
    assert code(lambda: capacity.model(capacity.parse_inputs(huge))) == "input_out_of_range"
    margin_overflow = dict(
        INUSE,
        dump_bytes=capacity.MAX_BYTES // 2,
        restore_ratio_per_mille=2000,
        margin_per_mille=capacity.MAX_MARGIN_PER_MILLE,
    )
    assert (
        code(lambda: capacity.model(capacity.parse_inputs(margin_overflow))) == "input_out_of_range"
    )
