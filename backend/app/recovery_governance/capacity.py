"""Capacity model and evidence-log validation (spec 074 Phase C, C4). No measurement is made.

The model is arithmetic over caller-supplied assumptions. Every figure that is still an owner
decision (restore-size ratio, restore working space, safety margin, available disk) is a required
input with no default. The result is stamped as a model calculation: not measured, not
validated, not approved. The 64 GiB dump ceiling is an unapproved placeholder, reproduced here
only so the model can say when a dump size exceeds it; it is pinned by a test against
``app.recovery_set.format.PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES`` and is not changed here.
"""

from typing import Literal

from pydantic import field_validator

from app.recovery_governance.common import (
    DATE,
    REF,
    Closed,
    GovernanceError,
    require_mapping,
)

PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES = 64 * 1024**3
_MAX = 2**63 - 1
INPUT_FIELDS = (
    "schema_version",
    "threshold_status",
    "dump_bytes",
    "archive_bytes",
    "manifest_bytes",
    "restore_ratio_per_mille",
    "restore_working_per_mille",
    "margin_per_mille",
    "available_disk_bytes",
)
STATEMENT = "informational; not an RPO/RTO or recovery-readiness measure"


def _ceil_div(numerator, denominator):
    return -(-numerator // denominator)


class CapacityInputs(Closed):
    schema_version: Literal[1]
    threshold_status: Literal["provisional-unapproved"]
    dump_bytes: int
    archive_bytes: int
    manifest_bytes: int
    restore_ratio_per_mille: int
    restore_working_per_mille: int
    margin_per_mille: int
    available_disk_bytes: int

    @field_validator(
        "dump_bytes",
        "manifest_bytes",
        "restore_ratio_per_mille",
    )
    @classmethod
    def _positive(cls, value):
        if not 1 <= value <= _MAX:
            raise ValueError("range")
        return value

    @field_validator(
        "archive_bytes",
        "restore_working_per_mille",
        "margin_per_mille",
        "available_disk_bytes",
    )
    @classmethod
    def _non_negative(cls, value):
        if not 0 <= value <= _MAX:
            raise ValueError("range")
        return value


def parse_inputs(raw):
    """Every input is required; a missing one is never replaced by an assumed value."""
    raw = require_mapping(raw)
    if any(name not in raw for name in INPUT_FIELDS):
        raise GovernanceError("input_missing")
    try:
        return CapacityInputs.model_validate(raw)
    except ValueError:
        raise GovernanceError("record_malformed") from None


def model(inputs):
    staged = inputs.dump_bytes + inputs.archive_bytes
    restored = _ceil_div(inputs.dump_bytes * inputs.restore_ratio_per_mille, 1000)
    working = _ceil_div(restored * inputs.restore_working_per_mille, 1000)
    subtotal = staged + inputs.manifest_bytes + restored + working
    margin = _ceil_div(subtotal * inputs.margin_per_mille, 1000)
    required = subtotal + margin
    return {
        "basis": "model_calculation",
        "measured": False,
        "validated": False,
        "approved": False,
        "threshold_status": inputs.threshold_status,
        "ceiling": {
            "placeholder_bytes": PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES,
            "status": "unapproved_placeholder",
            "dump_exceeds_placeholder": inputs.dump_bytes
            > PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES,
        },
        "components_bytes": {
            "staged_set": staged,
            "manifest_and_temporary": inputs.manifest_bytes,
            "restored_database": restored,
            "restore_working_space": working,
            "safety_margin": margin,
        },
        "required_bytes": required,
        "available_bytes": inputs.available_disk_bytes,
        "shortfall_bytes": max(0, required - inputs.available_disk_bytes),
        "fits_available_disk_under_assumptions": inputs.available_disk_bytes >= required,
        "statement": "assumptions_are_caller_supplied; " + STATEMENT,
    }


class _Host(Closed):
    model: str
    cpu: str
    cores: int
    ram_bytes: int
    swap_bytes: int
    kernel: str
    os: str
    python: str


class _Storage(Closed):
    device_type: str
    fs_type: str
    mount_options: str
    free_before: int
    free_after: int


class _Dataset(Closed):
    size_bytes: int
    generator: str
    seed: str
    sparse: bool
    entries: int


class _Measurements(Closed):
    wall_ms: int
    peak_rss_bytes: int
    throughput_bytes_s: int


class EvidenceLogEntry(Closed):
    run_id: str
    date_utc: str
    git_sha: str
    env_class: Literal["disposable-nonprod"]
    host: _Host
    storage: _Storage
    dataset: _Dataset
    cache_state: Literal["cold", "warm", "unknown"]
    command_shape: Literal["generate", "verify"]
    tool_output_verbatim: dict
    measurements: _Measurements
    anomalies: list
    operator: str
    reviewer: str
    disposition: Literal["informational"]

    @field_validator("operator", "reviewer", "run_id")
    @classmethod
    def _ref(cls, value):
        if not REF.fullmatch(value):
            raise ValueError("ref")
        return value

    @field_validator("date_utc")
    @classmethod
    def _date(cls, value):
        if not DATE.fullmatch(value[:10]):
            raise ValueError("date")
        return value


def parse_evidence_entry(raw):
    """Validate one evidence-log entry. It records an observation; it validates nothing."""
    raw = require_mapping(raw)
    if raw.get("env_class") not in (None, "disposable-nonprod"):
        raise GovernanceError("evidence_environment_rejected")
    try:
        EvidenceLogEntry.model_validate(raw)
    except ValueError:
        raise GovernanceError("record_malformed") from None
    return {"valid": True, "classification": "informational", "statement": STATEMENT}
