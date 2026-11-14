"""``verify``: stage order, four-field state model and freshness precedence (spec 074 2.5, 7.2).

Read-only and offline: no database, no network, no write inside the set.
"""

import hmac
import re
import time
from pathlib import Path

from app.recovery_set.format import (
    DEFAULT_LIMITS,
    KIND_DUMP,
    KIND_MARKER,
    CodedError,
    Limits,
    dump_model,
    manifest_hash,
    members_digest,
    parse_json,
    parse_manifest,
)
from app.recovery_set.fsset import open_set, read_protected_file
from app.recovery_set.key import check_fingerprint, load_key, verify_mac
from app.recovery_set.result import Result

_REVISION = re.compile(r"[0-9a-zA-Z_]{1,64}")


def verifier_chain():
    """Ordered oldest-to-newest revision ids from this code's own migration scripts, offline."""
    from alembic.script import ScriptDirectory

    directory = Path(__file__).resolve().parents[2] / "alembic"
    revisions = [item.revision for item in ScriptDirectory(str(directory)).walk_revisions()]
    return tuple(reversed(revisions))


def check_expectations(body, trust, chain):
    """Spec 7.2 item 4. Returns the ordered list of reason codes; empty means met."""
    reasons = []
    declared = body.installation.installation_id
    if not hmac.compare_digest(declared.encode(), trust["installation_id"].encode()):
        reasons.append("installation_mismatch")
    schema = body.schema_
    if schema.head != trust["schema_head"]:
        reasons.append("schema_head_mismatch")
    revisions = list(schema.revisions)
    if revisions[-1] != schema.head or len(set(revisions)) != len(revisions):
        reasons.append("schema_chain_inconsistent")
    elif any(item not in chain for item in revisions):
        reasons.append("schema_unknown_to_verifier")
    elif tuple(revisions) != tuple(chain[: len(revisions)]):
        reasons.append("schema_chain_inconsistent")
    if trust["expect_archive"] != ("present" if body.archive.present else "absent"):
        reasons.append("archive_expectation_mismatch")
    return reasons


def check_set(set_path, body, limits, state):
    """Stage 5. Returns (first_reason | None, scan found, dump_sha). Never hashes before checks."""
    with open_set(set_path, limits) as handle:
        scan = handle.scan(archive_declared=body.archive.present)
        handle.compare(scan, body.members, body.archive.present)
        state["member_count"] = len(scan.found)
        state["member_bytes"] = sum(item.size for item in scan.found.values())
        if scan.violations:
            return scan.violations[0], None
        declared = {m.path: m for m in body.members}
        dump_sha = None
        for item in scan.sorted_found():
            member = declared[item.path]
            digest, data = handle.hash_member(item, keep=item.kind == KIND_MARKER)
            if digest != member.sha256:
                return "set_member_hash_mismatch", None
            if item.kind == KIND_DUMP:
                dump_sha = digest
            if item.kind == KIND_MARKER and not _marker_matches(data, body.archive):
                return "archive_marker_mismatch", None
        return None, dump_sha


def _marker_matches(data, archive):
    try:
        marker = parse_json(data, "archive_marker_mismatch", "archive_marker_mismatch")
    except CodedError:
        return False
    return (
        isinstance(marker, dict)
        and set(marker) == {"schema_version", "root_id"}
        and type(marker["schema_version"]) is int
        and marker["schema_version"] == 1
        and archive.present
        and marker["root_id"] == archive.root_id
    )


def verify(trust, *, limits: Limits = DEFAULT_LIMITS, chain=None):
    """``trust`` holds only externally supplied inputs (spec 5.1). Returns ``Result``."""
    started = time.monotonic()
    result = Result("verify")
    try:
        _verify(trust, limits, chain, result)
    except CodedError as error:
        result.reason(error.code)
    except Exception:  # noqa: BLE001 - exception boundary: only a closed code leaves
        result.reason("internal_error")
    result.elapsed_ms = int((time.monotonic() - started) * 1000)
    return result


def _verify(trust, limits, chain, result):
    # Stage 2: manifest file read and structure.
    try:
        data = read_protected_file(
            trust["manifest"],
            max_bytes=limits.manifest_bytes,
            unsafe_code="manifest_file_unsafe",
            too_large_code="manifest_too_large",
            any_group_other_bit=False,
            require_owner=False,
        )
        envelope, payload_value = parse_manifest(data, limits)
    except CodedError as error:
        result.integrity = "integrity_invalid"
        result.reason(error.code)
        _freshness_required(trust, result)
        return
    body = envelope.payload.body
    # Stage 3: key file and authenticity.
    try:
        key = load_key(trust["key"], limits)
        check_fingerprint(key, trust["key_fingerprint"])
        result.extras["key_id"] = key.key_id
        result.extras["key_fingerprint"] = key.fingerprint()
        verify_mac(key, envelope, payload_value)
    except CodedError as error:
        result.authenticity = "authenticity_invalid"
        result.reason(error.code)
        _freshness_required(trust, result)
        return
    result.authenticity = "authenticity_valid"
    computed_hash = manifest_hash(payload_value)
    result.extras["manifest_hash"] = computed_hash
    # Stage 4: expectations.
    codes = check_expectations(body, trust, verifier_chain() if chain is None else chain)
    result.expectations = "expectations_not_met" if codes else "expectations_met"
    for code in codes:
        result.reason(code)
    # Stage 5: set integrity (runs when authenticity is valid, even if expectations failed).
    state, dump_sha = {}, None
    try:
        failure, dump_sha = check_set(trust["set"], body, limits, state)
    except CodedError as error:
        failure = error.code
    result.extras.update(state)
    if failure is None:
        result.integrity = "integrity_valid"
    else:
        result.integrity = "integrity_invalid"
        result.reason(failure)
    # Stage 6: freshness, only when parsed and authentic.
    expected = trust.get("expected_manifest_hash")
    if expected is not None:
        if hmac.compare_digest(expected.encode(), computed_hash.encode()):
            result.freshness = "freshness_match"
        else:
            result.freshness = "freshness_mismatch"
            result.reason("freshness_expected_hash_mismatch")
    _freshness_required(trust, result)
    if (
        result.integrity == "integrity_valid"
        and result.authenticity == "authenticity_valid"
        and result.expectations == "expectations_met"
    ):
        result.extras["verified_references"] = {
            "set_id": body.set_id,
            "manifest_hash": computed_hash,
            "dump_sha256": dump_sha,
            "members_digest": members_digest(body.members),
        }


def _freshness_required(trust, result):
    if trust.get("require_freshness") and result.freshness != "freshness_match":
        result.reason("freshness_required_not_established")


__all__ = ["dump_model", "verifier_chain", "verify"]
