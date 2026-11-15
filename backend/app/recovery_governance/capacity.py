"""Capacity model and evidence-log validation (spec 074 Phase C, C4). No measurement is made.

The model is arithmetic over caller-supplied assumptions. Every figure that is still an owner
decision (restore-size ratio, restore working space, safety margin, available disk) is a required
input with no default. The result is stamped as a model calculation: not measured, not
validated, not approved. The bounds on the inputs are engineering sanity limits that keep the
arithmetic well-defined; they are not capacity thresholds and nothing here is an approved limit.
The 64 GiB dump ceiling is an unapproved placeholder, reproduced here only so the model can say
when a dump size exceeds it; it is pinned by a test against
``app.recovery_set.format.PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES`` and is not changed here.

Evidence-log entries are closed: every field is a number within bounds, a closed vocabulary value,
a constrained token or an opaque reference, and no token or reference may contain a run of 32 or
more hexadecimal characters (the Git commit SHA is the one explicit, fixed-format exception). There is no free-text field and no embedded tool
output, so an entry cannot become a channel for arbitrary or sensitive data. Verbatim tool output
and host descriptions live outside the record and are referenced by opaque references only.
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, Field, field_validator

from app.recovery_governance.common import (
    Closed,
    GovernanceError,
    is_ref,
    is_schema_one,
    not_key_like,
    reject_object_identifiers,
    require_mapping,
    valid_timestamp,
)

PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES = 64 * 1024**3
MAX_BYTES = 2**60  # sanity bound (1 EiB), not a capacity limit
MAX_MODEL_BYTES = 2**63 - 1  # every intermediate and the total must stay within this
MAX_RATIO_PER_MILLE = 100_000  # 100x, sanity bound
MAX_MARGIN_PER_MILLE = 1_000_000  # 1000 percent, sanity bound
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

PositiveBytes = Annotated[int, Field(ge=1, le=MAX_BYTES)]
Bytes = Annotated[int, Field(ge=0, le=MAX_BYTES)]
Ratio = Annotated[int, Field(ge=1, le=MAX_RATIO_PER_MILLE)]
WorkingRatio = Annotated[int, Field(ge=0, le=MAX_RATIO_PER_MILLE)]
Margin = Annotated[int, Field(ge=0, le=MAX_MARGIN_PER_MILLE)]


def _ceil_div(numerator, denominator):
    return -(-numerator // denominator)


def _bounded(value):
    if value > MAX_MODEL_BYTES:
        raise GovernanceError("input_out_of_range")
    return value


class CapacityInputs(Closed):
    schema_version: Literal[1]
    threshold_status: Literal["provisional-unapproved"]
    dump_bytes: PositiveBytes
    archive_bytes: Bytes
    manifest_bytes: PositiveBytes
    restore_ratio_per_mille: Ratio
    restore_working_per_mille: WorkingRatio
    margin_per_mille: Margin
    available_disk_bytes: Bytes


def parse_inputs(raw):
    """Every input is required; a missing one is never replaced by an assumed value."""
    raw = require_mapping(raw)
    if any(name not in raw for name in INPUT_FIELDS):
        raise GovernanceError("input_missing")
    if not is_schema_one(raw["schema_version"]):
        raise GovernanceError("record_malformed")
    try:
        return CapacityInputs.model_validate(raw)
    except ValueError:
        raise GovernanceError("record_malformed") from None


def model(inputs):
    staged = _bounded(inputs.dump_bytes + inputs.archive_bytes)
    restored = _bounded(_ceil_div(inputs.dump_bytes * inputs.restore_ratio_per_mille, 1000))
    working = _bounded(_ceil_div(restored * inputs.restore_working_per_mille, 1000))
    subtotal = _bounded(staged + inputs.manifest_bytes + restored + working)
    margin = _bounded(_ceil_div(subtotal * inputs.margin_per_mille, 1000))
    required = _bounded(subtotal + margin)
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


Token = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$"), AfterValidator(not_key_like)
]
Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$"), AfterValidator(not_key_like)]
Count = Annotated[int, Field(ge=0, le=2**32)]
Millis = Annotated[int, Field(ge=0, le=2**40)]
MountOption = Literal["rw", "ro", "noatime", "relatime", "nodev", "nosuid", "noexec", "sync"]


class _Host(Closed):
    profile_ref: str
    cores: Annotated[int, Field(ge=1, le=65536)]
    ram_bytes: PositiveBytes
    swap_bytes: Bytes
    kernel: Token
    os: Token
    python: Token

    @field_validator("profile_ref")
    @classmethod
    def _ref(cls, value):
        if not is_ref(value):
            raise ValueError("ref")
        return value


class _Storage(Closed):
    device_type: Literal["nvme", "ssd", "hdd", "virtual", "tmpfs", "other", "unknown"]
    fs_type: Literal["ext4", "xfs", "btrfs", "tmpfs", "overlayfs", "other"]
    mount_options: Annotated[list[MountOption], Field(max_length=8)]
    free_before: Bytes
    free_after: Bytes


class _Dataset(Closed):
    size_bytes: PositiveBytes
    generator: str
    seed: str
    sparse: bool
    entries: Count

    @field_validator("generator", "seed")
    @classmethod
    def _ref(cls, value):
        if not is_ref(value):
            raise ValueError("ref")
        return value


class _Measurements(Closed):
    wall_ms: Millis
    peak_rss_bytes: Bytes
    throughput_bytes_s: Bytes


class EvidenceLogEntry(Closed):
    run_id: str
    date_utc: str
    git_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    env_class: Literal["disposable-nonprod"]
    host: _Host
    storage: _Storage
    dataset: _Dataset
    cache_state: Literal["cold", "warm", "unknown"]
    command_shape: Literal["generate", "verify"]
    tool_output_ref: str
    tool_exit_status: Annotated[int, Field(ge=0, le=2)]
    tool_reason_codes: Annotated[list[Code], Field(max_length=8)]
    measurements: _Measurements
    anomalies: Annotated[list[Code], Field(max_length=16)]
    operator: str
    reviewer: str
    disposition: Literal["informational"]

    @field_validator("run_id", "tool_output_ref", "operator", "reviewer")
    @classmethod
    def _ref(cls, value):
        if not is_ref(value):
            raise ValueError("ref")
        return value

    @field_validator("date_utc")
    @classmethod
    def _timestamp(cls, value):
        if not valid_timestamp(value):
            raise ValueError("timestamp")
        return value


def parse_evidence_entry(raw):
    """Validate one evidence-log entry. It records an observation; it validates nothing."""
    raw = require_mapping(raw)
    if raw.get("env_class") not in (None, "disposable-nonprod"):
        raise GovernanceError("evidence_environment_rejected")
    # Over the complete nested input, before anything is accepted: archive object names and bare
    # 32-hex document identifiers must not pass through any field (spec 9.4). Git commit SHAs
    # (40 hex) and the fixed-format fields are unaffected.
    reject_object_identifiers(raw)
    try:
        EvidenceLogEntry.model_validate(raw)
    except ValueError:
        raise GovernanceError("record_malformed") from None
    return {"valid": True, "classification": "informational", "statement": STATEMENT}
