"""Custody role-register and key-event record validation (spec 074 Phase C, C1 and C5).

Records and interfaces only. Nothing here generates, stores, reads, provisions or rotates a key,
names a person, or activates a custody arrangement. Roles that the owner has not assigned stay
``null`` (undecided). The primary and recovery custodians are both verification-key holders and
can each forge a valid HMAC; the operator holds the key only temporarily, during an authorized
session. Procedural separation is reported as such: it is never cryptographic separation, and no
output claims non-repudiation or independent verification.

An owner-acceptance reference is format-checked only. Its presence proves no owner decision, and
this package has no authority record to check it against: the report says so, and a status of
"caller verified" only reflects what the caller states it verified outside this package.
"""

from datetime import date
from typing import Literal, Protocol

from pydantic import field_validator

from app.recovery_governance.common import (
    DATE,
    UUID,
    Closed,
    GovernanceError,
    is_ref,
    is_schema_one,
    require_mapping,
)

ROLES = ("primary_custodian", "recovery_custodian", "operator", "record_keeper")
KEY_HOLDER_ROLES = ("primary_custodian", "recovery_custodian")
CONFLICTS = (
    ("primary_custodian", "recovery_custodian"),
    ("record_keeper", "primary_custodian"),
    ("record_keeper", "recovery_custodian"),
)
SEPARATION_NOTE = "procedural_separation_only; every_key_holder_can_forge; not_non_repudiation"


def parse_role_register(raw, verified_decisions=None):
    """Validate a role register and report; assignments may be ``null`` (undecided).

    ``verified_decisions`` is the set of owner-decision references the caller states were verified
    against an owner-decision record outside this package (default: none).
    """
    raw = require_mapping(raw, "role_register_invalid")
    if set(raw) != {"schema_version", "assignments", "degraded_arrangement_acceptance_ref"}:
        raise GovernanceError("role_register_invalid")
    if not is_schema_one(raw["schema_version"]):
        raise GovernanceError("role_register_invalid")
    assignments = require_mapping(raw["assignments"], "role_register_invalid")
    if set(assignments) != set(ROLES):
        raise GovernanceError("role_register_invalid")
    for value in assignments.values():
        if value is not None and not is_ref(value):
            raise GovernanceError("role_register_invalid")
    acceptance = raw["degraded_arrangement_acceptance_ref"]
    if acceptance is not None and not is_ref(acceptance):
        raise GovernanceError("role_register_invalid")
    undecided = [role for role in ROLES if assignments[role] is None]
    conflicts = [
        [a, b]
        for a, b in CONFLICTS
        if assignments[a] is not None and assignments[a] == assignments[b]
    ]
    if undecided:
        status = "undecided"
    elif not conflicts:
        status = "complete_distinct"
    elif acceptance is None:
        status = "degraded_not_accepted"
    elif acceptance in frozenset(verified_decisions or ()):
        status = "degraded_owner_decision_caller_verified"
    else:
        status = "degraded_reference_unverified"
    holders = sorted(
        {assignments[role] for role in KEY_HOLDER_ROLES if assignments[role] is not None}
    )
    return {
        "status": status,
        "undecided_roles": undecided,
        "conflicts": conflicts,
        "acceptance_reference": (
            "none" if acceptance is None else "format_checked_only_authority_not_verified"
        ),
        "authority_verification": "not_performed_by_this_package",
        "key_holders_at_rest": holders,
        "operator_key_access": "temporary_during_authorized_session_only",
        "note": SEPARATION_NOTE,
    }


def key_holders(register_raw, verified_decisions=None):
    """Actors who hold the verification key at rest (both custodians), for ledger checks."""
    report = parse_role_register(register_raw, verified_decisions)
    return set(report["key_holders_at_rest"])


class KeyEventRecord(Closed):
    """Metadata-only audit record. There is no field that can carry key material.

    The key's keyed fingerprint is a 64-character hexadecimal tag, which cannot be told apart
    from key material by syntax, so it is deliberately **not** a field here: the record carries
    only an opaque reference to the keeper's fingerprint record. References may not look like
    key material (long hexadecimal strings are rejected).
    """

    event_id: str
    event: Literal[
        "generated",
        "provisioned",
        "released_for_session",
        "returned_from_session",
        "rotated",
        "retired",
        "destroyed",
        "lost_declared",
        "compromise_declared",
    ]
    key_id: str
    fingerprint_record_ref: str
    installation_id: str
    occurred_on: str
    role: Literal["primary_custodian", "recovery_custodian", "operator", "record_keeper"]
    actor_ref: str
    ceremony_ref: str | None = None

    @field_validator("event_id", "key_id", "installation_id")
    @classmethod
    def _uuid(cls, value):
        if not UUID.fullmatch(value):
            raise ValueError("uuid")
        return value

    @field_validator("occurred_on")
    @classmethod
    def _date(cls, value):
        if not DATE.fullmatch(value):
            raise ValueError("date")
        date.fromisoformat(value)
        return value

    @field_validator("fingerprint_record_ref", "actor_ref", "ceremony_ref")
    @classmethod
    def _ref(cls, value):
        if value is not None and not is_ref(value):
            raise ValueError("ref")
        return value


def validate_key_events(raw_events):
    if not isinstance(raw_events, (list, tuple)):
        raise GovernanceError("key_event_invalid")
    try:
        events = [KeyEventRecord.model_validate(item) for item in raw_events]
    except ValueError:
        raise GovernanceError("key_event_invalid") from None
    seen = set()
    previous = None
    for item in events:
        if item.event_id in seen or (previous is not None and item.occurred_on < previous):
            raise GovernanceError("key_event_invalid")
        seen.add(item.event_id)
        previous = item.occurred_on
    return {"valid": True, "events": len(events), "note": "metadata_only; no_key_material_field"}


class FutureKeyOperations(Protocol):
    """Interface for FUTURE key operations. No implementation exists and none is authorized.

    Any future implementation (a separate owner authorization, after the custody decisions)
    must emit a ``KeyEventRecord`` for every operation, so that generation, provisioning,
    release, rotation, loss and destruction are auditable without recording key material.
    """

    def record_event(self, event: KeyEventRecord) -> None: ...
