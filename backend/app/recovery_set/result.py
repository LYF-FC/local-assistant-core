"""Closed result object and exit statuses (spec 074 sections 2.5 and 7.3)."""

from dataclasses import dataclass, field

from app.recovery_set.format import REASON_CODES

NOTE_VOCABULARY = ("stale_temporary_present",)
INTEGRITY = ("integrity_valid", "integrity_invalid", "integrity_not_evaluated")
AUTHENTICITY = ("authenticity_valid", "authenticity_invalid", "authenticity_not_evaluated")
EXPECTATIONS = ("expectations_met", "expectations_not_met", "expectations_not_evaluated")
FRESHNESS = ("freshness_not_evaluated", "freshness_match", "freshness_mismatch")
PUBLICATION = ("not_published", "published_durability_uncertain", "published_durable")
FRESHNESS_NOTE = "matches_supplied_expected_hash_only"

KEYS = frozenset(
    {
        "schema_version", "operation", "integrity", "authenticity", "expectations", "freshness",
        "reasons", "notes", "manifest_hash", "key_id", "key_fingerprint", "member_count",
        "member_bytes", "verified_references", "elapsed_ms", "point_in_time", "restore_performed",
        "recovery_complete", "freshness_note", "publication",
    }
)  # fmt: skip
VERIFIED_KEYS = frozenset({"set_id", "manifest_hash", "dump_sha256", "members_digest"})
USAGE_CODES = frozenset(
    {
        "trust_input_missing", "trust_input_malformed", "freshness_requested_without_expected_hash",
        "paths_overlap",
    }
)  # fmt: skip


@dataclass
class Result:
    operation: str
    integrity: str = "integrity_not_evaluated"
    authenticity: str = "authenticity_not_evaluated"
    expectations: str = "expectations_not_evaluated"
    freshness: str = "freshness_not_evaluated"
    reasons: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    extras: dict = field(default_factory=dict)
    publication: str | None = None
    elapsed_ms: int = 0

    def reason(self, code):
        if code not in REASON_CODES:
            raise ValueError("unknown reason code")
        if code not in self.reasons:
            self.reasons.append(code)

    def freshness_note(self):
        return FRESHNESS_NOTE if self.freshness == "freshness_match" else None

    def exit_status(self):
        if any(code in USAGE_CODES for code in self.reasons):
            return 2
        if self.operation == "generate":
            return 0 if self.publication == "published_durable" and not self.reasons else 1
        ok = (
            self.integrity == "integrity_valid"
            and self.authenticity == "authenticity_valid"
            and self.expectations == "expectations_met"
            and self.freshness != "freshness_mismatch"
            and not self.reasons
        )
        return 0 if ok else 1

    def to_dict(self):
        notes = sorted(set(self.notes))
        if any(note not in NOTE_VOCABULARY for note in notes):
            raise ValueError("note outside the closed vocabulary")
        value = {
            "schema_version": 1,
            "operation": self.operation,
            "integrity": self.integrity,
            "authenticity": self.authenticity,
            "expectations": self.expectations,
            "freshness": self.freshness,
            "reasons": list(self.reasons),
            "notes": notes,
            "elapsed_ms": self.elapsed_ms,
            "point_in_time": True,
            "restore_performed": False,
            "recovery_complete": False,
        }
        value.update(self.extras)
        note = self.freshness_note()
        if note is not None:
            value["freshness_note"] = note
        if self.publication is not None:
            value["publication"] = self.publication
        if self.operation == "generate":
            value.pop("verified_references", None)
        if set(value) - KEYS:
            raise ValueError("key outside the closed output set")
        return value
