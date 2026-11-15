"""Expected-manifest-hash record and ledger validation (spec 074 Phase C, C2).

Two acts are kept apart (docs/RECOVERY_HASH_GOVERNANCE.md):

* the initial witnessed recording of a hash (``HashRecordEntry``): the entry equals what the tool
  printed for that run, nothing more;
* a later comparison of a retained hash against a presented manifest (``ComparisonEvent``): with
  the current tooling that needs ``verify``, which requires the HMAC key, so it is a *key-holder
  check* and never independent verification.

The models have no field that can express independence, and any independence claim is rejected.
Persons are never named: actors are opaque references. This module reads and writes nothing and
touches no key material. It does not change the closed output of ``app.recovery_set``.
"""

from datetime import date
from typing import Literal

from pydantic import field_validator, model_validator

from app.recovery_governance.common import (
    DATE,
    HEX64,
    REF,
    SCHEMA_HEAD,
    UUID,
    Closed,
    GovernanceError,
    require_mapping,
)

FRESHNESS_STATES = ("freshness_not_evaluated", "freshness_match", "freshness_mismatch")
EVIDENCE_CLASS = "key_holder_check_not_independent"


def _pattern(value, pattern):
    if not pattern.fullmatch(value):
        raise ValueError("pattern")
    return value


def _iso_date(value):
    _pattern(value, DATE)
    date.fromisoformat(value)
    return value


class HashRecordEntry(Closed):
    entry: int
    set_id: str
    manifest_hash: str
    key_id: str
    installation_id: str
    schema_head: str
    recorded_on: str
    recorded_by: str
    witnessed_by: str
    approved_by: str | None = None
    approval_process_ref: str | None = None
    supersedes: int | None = None

    @field_validator("entry")
    @classmethod
    def _entry(cls, value):
        if value < 1:
            raise ValueError("entry")
        return value

    @field_validator("supersedes")
    @classmethod
    def _supersedes(cls, value):
        if value is not None and value < 1:
            raise ValueError("supersedes")
        return value

    @field_validator("manifest_hash")
    @classmethod
    def _hash(cls, value):
        return _pattern(value, HEX64)

    @field_validator("key_id", "installation_id")
    @classmethod
    def _uuid(cls, value):
        return _pattern(value, UUID)

    @field_validator("schema_head")
    @classmethod
    def _head(cls, value):
        return _pattern(value, SCHEMA_HEAD)

    @field_validator("recorded_on")
    @classmethod
    def _date(cls, value):
        return _iso_date(value)

    @field_validator("set_id", "recorded_by", "witnessed_by", "approved_by", "approval_process_ref")
    @classmethod
    def _ref(cls, value):
        return value if value is None else _pattern(value, REF)

    @model_validator(mode="after")
    def _roles(self):
        if self.recorded_by == self.witnessed_by:
            raise GovernanceError("witness_not_distinct")
        if self.approved_by is not None and self.approval_process_ref is None:
            raise GovernanceError("approver_without_defined_process")
        if self.approved_by is None and self.approval_process_ref is not None:
            raise ValueError("process without approver")
        if self.supersedes is not None and self.supersedes >= self.entry:
            raise ValueError("supersedes")
        return self


class ComparisonEvent(Closed):
    """A later comparison. ``basis`` can only be a key-holder check; there is no other value."""

    entry: int
    compared_on: str
    basis: Literal["key_holder_check"]
    performed_by: str
    presented_manifest_hash: str
    result: Literal["freshness_not_evaluated", "freshness_match", "freshness_mismatch"]

    @field_validator("compared_on")
    @classmethod
    def _date(cls, value):
        return _iso_date(value)

    @field_validator("performed_by")
    @classmethod
    def _ref(cls, value):
        return _pattern(value, REF)

    @field_validator("presented_manifest_hash")
    @classmethod
    def _hash(cls, value):
        return _pattern(value, HEX64)


def _reject_independence_claims(raw):
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(key, str) and "independ" in key.lower():
                raise GovernanceError("independence_claim_rejected")
            _reject_independence_claims(value)
    elif isinstance(raw, list):
        for item in raw:
            _reject_independence_claims(item)


def _parse(model, raw):
    require_mapping(raw)
    _reject_independence_claims(raw)
    try:
        return model.model_validate(raw)
    except GovernanceError:
        raise
    except ValueError:
        raise GovernanceError("record_malformed") from None


def parse_entry(raw):
    return _parse(HashRecordEntry, raw)


def parse_comparison(raw):
    return _parse(ComparisonEvent, raw)


def validate_ledger(entries_raw, comparisons_raw=(), key_holders=None):
    """Validate an append-only ledger and any later comparisons; return a closed report.

    ``key_holders`` is the set of actor references known to hold the verification key (for
    example from the role register). Comparisons cannot be validated without it, so a ledger
    with comparisons and no ``key_holders`` fails closed rather than assuming.
    """
    if not isinstance(entries_raw, (list, tuple)):
        raise GovernanceError("record_malformed")
    entries = [parse_entry(item) for item in entries_raw]
    comparisons = [parse_comparison(item) for item in comparisons_raw]
    by_number = {}
    last_for_set = {}
    previous_date = None
    for index, item in enumerate(entries, start=1):
        if item.entry != index or item.entry in by_number:
            raise GovernanceError("ledger_sequence_invalid")
        if previous_date is not None and item.recorded_on < previous_date:
            raise GovernanceError("ledger_sequence_invalid")
        previous_date = item.recorded_on
        expected = last_for_set.get(item.set_id)
        if item.supersedes != expected:
            raise GovernanceError("ledger_supersession_invalid")
        if item.supersedes is not None and by_number[item.supersedes].set_id != item.set_id:
            raise GovernanceError("ledger_supersession_invalid")
        by_number[item.entry] = item
        last_for_set[item.set_id] = item.entry
    superseded = {item.supersedes for item in entries if item.supersedes is not None}
    if comparisons and key_holders is None:
        raise GovernanceError("input_missing")
    reported = []
    for event in comparisons:
        target = by_number.get(event.entry)
        if target is None:
            raise GovernanceError("comparison_inconsistent")
        if event.performed_by not in key_holders:
            raise GovernanceError("comparison_not_key_holder")
        equal = event.presented_manifest_hash == target.manifest_hash
        if (event.result == "freshness_match" and not equal) or (
            event.result == "freshness_mismatch" and equal
        ):
            raise GovernanceError("comparison_inconsistent")
        reported.append(
            {
                "entry": event.entry,
                "result": event.result,
                "reference": "superseded" if event.entry in superseded else "latest",
                "evidence_class": EVIDENCE_CLASS,
            }
        )
    return {
        "valid": True,
        "entries": len(entries),
        "latest_entry_by_set": dict(sorted(last_for_set.items())),
        "comparisons": reported,
        "note": "recording_is_not_hmac_verification; comparisons_are_key_holder_checks",
    }
