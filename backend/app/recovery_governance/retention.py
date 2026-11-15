"""Retention policy validation and report-only reconciliation (spec 074 Phase C, C3).

Every artifact class must carry an explicit period in the policy file: either the literal
``"undecided"`` or ``{"days": n}``. There is no default and no inferred period; a missing class
is an error. Reconciliation is report-only: it never deletes, expires, purges or restores
anything, and "period elapsed" means only that the owner must review. A verified manifest is
never permission to restore: for recovery sets and manifests the report always states that
restore eligibility is not established while DOC-X02 (older-backup forgetting reconciliation for
non-Work records) is open. Records carry opaque identifiers only, never archive object names.
"""

from datetime import date
from typing import Literal

from pydantic import field_validator

from app.recovery_governance.common import (
    DATE,
    HEX64,
    REF,
    UUID,
    Closed,
    GovernanceError,
    reject_object_identifiers,
    require_mapping,
)

ARTIFACT_CLASSES = (
    "recovery_set",
    "manifest",
    "expected_hash_record",
    "fingerprint_record",
    "key_copy",
    "key_event_record",
    "captured_tool_output",
    "temporary_artifact",
)
MAX_DAYS = 36500
BLOCKERS = ("doc_x02_open",)
RESTORE_ELIGIBILITY = "not_established_doc_x02_open"
_SET_CLASSES = ("recovery_set", "manifest")


def _iso(value):
    if not DATE.fullmatch(value):
        raise GovernanceError("inventory_invalid")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise GovernanceError("inventory_invalid") from None


def _check_date(value):
    if not DATE.fullmatch(value):
        raise ValueError("date")
    date.fromisoformat(value)
    return value


def parse_policy(raw):
    """Return {class: None | days}; None means undecided. Every class is required."""
    raw = require_mapping(raw, "policy_period_invalid")
    if set(raw) != {"schema_version", "periods"} or raw["schema_version"] != 1:
        raise GovernanceError("policy_period_invalid")
    periods = require_mapping(raw["periods"], "policy_period_invalid")
    for name in periods:
        if name not in ARTIFACT_CLASSES:
            raise GovernanceError("policy_class_unknown")
    for name in ARTIFACT_CLASSES:
        if name not in periods:
            raise GovernanceError("policy_class_missing")
    result = {}
    for name in ARTIFACT_CLASSES:
        value = periods[name]
        if value == "undecided":
            result[name] = None
        elif (
            isinstance(value, dict)
            and set(value) == {"days"}
            and isinstance(value["days"], int)
            and not isinstance(value["days"], bool)
            and 1 <= value["days"] <= MAX_DAYS
        ):
            result[name] = value["days"]
        else:
            raise GovernanceError("policy_period_invalid")
    return result


class InventoryItem(Closed):
    artifact_id: str
    artifact_class: Literal[
        "recovery_set",
        "manifest",
        "expected_hash_record",
        "fingerprint_record",
        "key_copy",
        "key_event_record",
        "captured_tool_output",
        "temporary_artifact",
    ]
    created_on: str
    state: Literal["active", "superseded", "expired", "destroyed"]
    evidence_ref: str | None = None

    @field_validator("artifact_id", "evidence_ref")
    @classmethod
    def _ref(cls, value):
        if value is not None and not REF.fullmatch(value):
            raise ValueError("ref")
        return value

    @field_validator("created_on")
    @classmethod
    def _created(cls, value):
        return _check_date(value)


class Obligation(Closed):
    obligation_ref: str
    applies_to: list
    status: Literal["open", "closed"]
    evidence_ref: str | None = None

    @field_validator("obligation_ref", "evidence_ref")
    @classmethod
    def _ref(cls, value):
        if value is not None and not REF.fullmatch(value):
            raise ValueError("ref")
        return value

    @field_validator("applies_to")
    @classmethod
    def _targets(cls, value):
        if not value or not all(isinstance(i, str) and REF.fullmatch(i) for i in value):
            raise ValueError("applies_to")
        return value


def parse_inventory(raw):
    raw = require_mapping(raw, "inventory_invalid")
    if set(raw) - {"schema_version", "items", "obligations"} or raw.get("schema_version") != 1:
        raise GovernanceError("inventory_invalid")
    if not isinstance(raw.get("items"), list) or not isinstance(raw.get("obligations", []), list):
        raise GovernanceError("inventory_invalid")
    reject_object_identifiers(raw)
    try:
        items = [InventoryItem.model_validate(i) for i in raw["items"]]
        obligations = [Obligation.model_validate(o) for o in raw.get("obligations", [])]
    except ValueError:
        raise GovernanceError("inventory_invalid") from None
    ids = [i.artifact_id for i in items]
    if len(set(ids)) != len(ids):
        raise GovernanceError("inventory_invalid")
    for obligation in obligations:
        if not set(obligation.applies_to) <= set(ids):
            raise GovernanceError("inventory_invalid")
        if obligation.status == "closed" and obligation.evidence_ref is None:
            raise GovernanceError("inventory_invalid")
    return items, obligations


def reconcile(policy, items, obligations, as_of):
    """Report-only reconciliation; takes no action on any artifact."""
    today = _iso(as_of)
    open_for = {}
    for obligation in obligations:
        if obligation.status == "open":
            for target in obligation.applies_to:
                open_for.setdefault(target, []).append(obligation.obligation_ref)
    report = []
    for item in sorted(items, key=lambda i: i.artifact_id):
        period = policy[item.artifact_class]
        if item.state in ("expired", "destroyed") and item.evidence_ref is None:
            status = "recorded_without_evidence"
        elif item.state == "destroyed":
            status = "recorded_destroyed"
        elif item.artifact_id in open_for:
            status = "forgetting_obligation_open"
        elif period is None:
            status = "undecided_period"
        elif (today - _iso(item.created_on)).days >= period:
            status = "period_elapsed_owner_review_required"
        else:
            status = "within_retention"
        entry = {"artifact_id": item.artifact_id, "class": item.artifact_class, "status": status}
        if item.artifact_class in _SET_CLASSES:
            entry["restore_eligibility"] = RESTORE_ELIGIBILITY
        report.append(entry)
    counts = {}
    for entry in report:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {
        "report": "retention_reconciliation",
        "basis": "policy_and_inventory_only",
        "actions_taken": "none",
        "blockers": list(BLOCKERS),
        "items": report,
        "summary": dict(sorted(counts.items())),
    }


class DestructionRecord(Closed):
    """Deletion evidence: set ids and hashes only, never object identifiers (spec 9.4)."""

    record_id: str
    set_id: str
    manifest_hash: str
    destroyed_on: str
    authorized_by_ref: str
    method_ref: str
    copy_inventory_ref: str

    @field_validator("record_id")
    @classmethod
    def _uuid(cls, value):
        if not UUID.fullmatch(value):
            raise ValueError("uuid")
        return value

    @field_validator("manifest_hash")
    @classmethod
    def _hash(cls, value):
        if not HEX64.fullmatch(value):
            raise ValueError("hash")
        return value

    @field_validator("destroyed_on")
    @classmethod
    def _date(cls, value):
        return _check_date(value)

    @field_validator("set_id", "authorized_by_ref", "method_ref", "copy_inventory_ref")
    @classmethod
    def _ref(cls, value):
        if not REF.fullmatch(value):
            raise ValueError("ref")
        return value


def parse_destruction_record(raw):
    raw = require_mapping(raw)
    reject_object_identifiers(raw)
    try:
        record = DestructionRecord.model_validate(raw)
    except GovernanceError:
        raise
    except ValueError:
        raise GovernanceError("record_malformed") from None
    return {
        "valid": True,
        "record_id": record.record_id,
        "note": "evidence_record_only; no_deletion_performed_or_authorized_by_validation",
    }
