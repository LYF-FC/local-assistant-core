"""``generate``: build, authenticate and publish a manifest for a synthetic set (spec 074 7.1)."""

import os
import re
import time
import uuid
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from platform import python_version

from app.recovery_set.format import (
    DEFAULT_LIMITS,
    KIND_MARKER,
    PENDING_PREFIX,
    SAFE_VERSION_RE,
    TOOL_VERSION,
    CodedError,
    Limits,
    canonical,
    manifest_hash,
    parse_json,
    parse_manifest,
    valid_uuid,
)
from app.recovery_set.fsset import open_set
from app.recovery_set.key import check_fingerprint, load_key
from app.recovery_set.publish import (
    STALE_NOTE,
    InjectedFaults,
    publish_manifest,
    stale_temporary_note,
)
from app.recovery_set.result import Result
from app.recovery_set.verify import verifier_chain

PACKAGES = ("fastapi", "sqlalchemy", "psycopg", "pydantic")
_SAFE = re.compile(SAFE_VERSION_RE)
__all__ = ["PENDING_PREFIX", "InjectedFaults", "generate"]


def _safe(value):
    return value if isinstance(value, str) and _SAFE.fullmatch(value) else None


def _installed(package):
    try:
        return _safe(version(package))
    except PackageNotFoundError:
        return None


def application_record():
    return {
        "api_version": _installed("butler-backend") or "unknown",
        "python_version": _safe(python_version()) or "unknown",
        "packages": {name: _installed(name) for name in PACKAGES},
    }


def _read_root_id(data):
    try:
        marker = parse_json(data, "archive_marker_mismatch", "archive_marker_mismatch")
    except CodedError as error:
        raise CodedError("archive_marker_mismatch") from error
    if (
        not isinstance(marker, dict)
        or set(marker) != {"schema_version", "root_id"}
        or type(marker["schema_version"]) is not int
        or marker["schema_version"] != 1
        or not isinstance(marker["root_id"], str)
        or not valid_uuid(marker["root_id"])
    ):
        raise CodedError("archive_marker_mismatch")
    return marker["root_id"]


def _read_and_hash(trust, limits, result, faults):
    """Read the set twice around hashing (spec 3.7). Returns (members, archive, totals)."""
    expect_present = trust["expect_archive"] == "present"
    with open_set(trust["set"], limits) as handle:
        first = handle.scan(archive_declared=None)
        if first.archive_dir != expect_present:
            result.expectations = "expectations_not_met"
            raise CodedError("archive_expectation_mismatch")
        if first.violations:
            raise CodedError(first.violations[0])
        found = first.sorted_found()
        kinds = [item.kind for item in found]
        if first.archive_dir and (kinds.count(KIND_MARKER) != 1 or "archive_lock" not in kinds):
            raise CodedError("set_member_missing")
        if "database.dump" not in first.found:
            raise CodedError("set_member_missing")
        members, root_id = [], None
        for item in found:
            digest, data = handle.hash_member(item, keep=item.kind == KIND_MARKER)
            if item.kind == KIND_MARKER:
                root_id = _read_root_id(data)
            members.append(
                {"path": item.path, "kind": item.kind, "size": item.size, "sha256": digest}
            )
        if faults is not None:
            faults.fire("between_passes")
        second = handle.scan(archive_declared=None)
        if second.violations or second.archive_signature() != first.archive_signature():
            raise CodedError("archive_changed_during_generation")
        if second.dump_signature() != first.dump_signature():
            raise CodedError("set_changed_during_read")
    count = sum(1 for item in found if item.kind == "archive_object")
    archive = (
        {"present": True, "root_id": root_id, "object_count": count}
        if root_id
        else {"present": False}
    )
    return members, archive, (len(found), sum(item.size for item in found))


def generate(
    trust,
    *,
    limits: Limits = DEFAULT_LIMITS,
    chain=None,
    faults: InjectedFaults | None = None,
    set_id=None,
    created_at=None,
):
    """``set_id``, ``created_at``, ``chain`` and ``faults`` are test-only function parameters."""
    started = time.monotonic()
    result = Result("generate", publication="not_published")
    try:
        result.notes = stale_temporary_note(os.path.dirname(os.path.abspath(trust["output"])))
        _generate(trust, limits, chain, result, faults, set_id, created_at)
    except CodedError as error:
        result.reason(error.code)
    except Exception:  # noqa: BLE001 - exception boundary: only a closed code leaves
        result.reason("internal_error")
    result.elapsed_ms = int((time.monotonic() - started) * 1000)
    return result


def _generate(trust, limits, chain, result, faults, set_id, created_at):
    try:
        key = load_key(trust["key"], limits)
        check_fingerprint(key, trust["key_fingerprint"])
        if key.installation_id != trust["installation_id"]:
            raise CodedError("key_installation_mismatch")
    except CodedError:
        result.authenticity = "authenticity_invalid"
        raise
    result.authenticity = "authenticity_valid"
    result.extras["key_id"] = key.key_id
    result.extras["key_fingerprint"] = key.fingerprint()
    revisions = tuple(verifier_chain() if chain is None else chain)
    head = trust["schema_head"]
    if head not in revisions:
        result.expectations = "expectations_not_met"
        raise CodedError("schema_unknown_to_verifier")
    chain_ids = list(revisions[: revisions.index(head) + 1])
    try:
        members, archive, totals = _read_and_hash(trust, limits, result, faults)
    except CodedError:
        if result.expectations != "expectations_not_met":
            result.integrity = "integrity_invalid"
        raise
    result.integrity = "integrity_valid"
    result.expectations = "expectations_met"
    result.extras["member_count"], result.extras["member_bytes"] = totals
    body = {
        "set_id": set_id or str(uuid.uuid4()),
        "created_at": created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": {"tool_version": TOOL_VERSION},
        "installation": {"installation_id": trust["installation_id"]},
        "schema": {"head": head, "revisions": chain_ids},
        "application": application_record(),
        "model": (
            {"declared": True, "tag": trust["model_tag"], "digest": trust["model_digest"]}
            if trust.get("model_tag")
            else {"declared": False}
        ),
        "work_references": {
            "suppression_manifest_sha256": trust.get("work_suppression_manifest_sha256"),
            "source_checkpoint_sha256": trust.get("work_source_checkpoint_sha256"),
        },
        "archive": archive,
        "members": members,
    }
    payload = {"key_id": key.key_id, "key_fingerprint": key.fingerprint(), "body": body}
    envelope = {
        "schema_version": 1,
        "purpose": "butler.recovery-set.v1",
        "payload": payload,
        "algorithm": "HMAC-SHA256",
        "mac": key.mac(payload),
    }
    data = canonical(envelope)
    parse_manifest(data, limits)  # the generator never publishes what its own parser rejects
    result.extras["manifest_hash"] = manifest_hash(payload)
    report = {}
    try:
        result.publication = publish_manifest(trust["output"], data, faults, report)
    except CodedError:
        result.publication = "not_published"
        raise
    finally:
        if report.get("temporary_remaining") and STALE_NOTE not in result.notes:
            result.notes = sorted([*result.notes, STALE_NOTE])
    if result.publication == "published_durability_uncertain":
        result.reason("publication_durability_uncertain")
