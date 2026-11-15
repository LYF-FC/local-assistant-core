"""Custody role-register and key-event record validation (spec 074 Phase C, C1 and C5).

Records and interfaces only. Nothing here generates, stores, reads, provisions or rotates a key,
names a person, or activates a custody arrangement. Roles that the owner has not assigned stay
``null`` (undecided). The primary and recovery custodians are both verification-key holders and
can each forge a valid HMAC; the operator holds the key only temporarily, during an authorized
session. Procedural separation is reported as such: it is never cryptographic separation, and no
output claims non-repudiation or independent verification.
"""

from datetime import date
from typing import Literal, Protocol

from pydantic import field_validator

from app.recovery_governance.common import (
    DATE,
    HEX64,
    REF,
    UUID,
    Closed,
    GovernanceError,
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


def parse_role_register(raw):
    """Validate a role register and report; assignments may be ``null`` (undecided)."""
    raw = require_mapping(raw, "role_register_invalid")
    if set(raw) != {"schema_version", "assignments", "degraded_arrangement_acceptance_ref"}:
        raise GovernanceError("role_register_invalid")
    if raw["schema_version"] != 1:
        raise GovernanceError("role_register_invalid")
    assignments = require_mapping(raw["assignments"], "role_register_invalid")
    if set(assignments) != set(ROLES):
        raise GovernanceError("role_register_invalid")
    for value in assignments.values():
        if value is not None and not (isinstance(value, str) and REF.fullmatch(value)):
            raise GovernanceError("role_register_invalid")
    acceptance = raw["degraded_arrangement_acceptance_ref"]
    if acceptance is not None and not (isinstance(acceptance, str) and REF.fullmatch(acceptance)):
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
    elif acceptance is not None:
        status = "degraded_accepted_by_owner_reference"
    else:
        status = "degraded_not_accepted"
    holders = sorted(
        {assignments[role] for role in KEY_HOLDER_ROLES if assignments[role] is not None}
    )
    return {
        "status": status,
        "undecided_roles": undecided,
        "conflicts": conflicts,
        "key_holders_at_rest": holders,
        "operator_key_access": "temporary_during_authorized_session_only",
        "note": SEPARATION_NOTE,
    }


def key_holders(register_raw):
    """Actors who hold the verification key at rest (both custodians), for ledger checks."""
    report = parse_role_register(register_raw)
    return set(report["key_holders_at_rest"])


class KeyEventRecord(Closed):
    """Metadata-only audit record. There is no field that can carry key material."""

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
    key_fingerprint: str
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

    @field_validator("key_fingerprint")
    @classmethod
    def _fingerprint(cls, value):
        if not HEX64.fullmatch(value):
            raise ValueError("fingerprint")
        return value

    @field_validator("occurred_on")
    @classmethod
    def _date(cls, value):
        if not DATE.fullmatch(value):
            raise ValueError("date")
        date.fromisoformat(value)
        return value

    @field_validator("actor_ref", "ceremony_ref")
    @classmethod
    def _ref(cls, value):
        if value is not None and not REF.fullmatch(value):
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
