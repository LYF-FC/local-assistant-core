"""Closed models, strict JSON loading and a bounded read-only file loader."""

import json
import os
import re
import stat
from datetime import datetime

from pydantic import BaseModel, ConfigDict

HEX64 = re.compile(r"[a-f0-9]{64}")
UUID = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
SCHEMA_HEAD = re.compile(r"[A-Za-z0-9_]{1,64}")
# Archive object names (spec 3.3) and bare document identifiers must never appear in governance
# or deletion-evidence records (spec 9.4): they would re-disclose what was forgotten.
OBJECT_NAME = re.compile(r"[a-f0-9]{32}-v[1-9][0-9]{0,8}\.original")
BARE_32HEX = re.compile(r"[a-f0-9]{32}")
# Long hexadecimal runs are indistinguishable from key material, so opaque references, tokens and
# identifiers may not contain one anywhere (prefix, suffix or middle). Explicit exceptions, each
# validated by its own fixed-format pattern and never claimed to be distinguishable from key
# material: manifest hashes (64 hex, hash_record), Git commit SHAs (40 hex, capacity) and the
# fixed-format UUID fields.
KEY_LIKE = re.compile(r"[0-9A-Fa-f]{32,}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})")
MAX_INPUT_BYTES = 1024 * 1024

CODES = frozenset(
    {
        "json_malformed",
        "record_malformed",
        "input_missing",
        "input_unreadable",
        "independence_claim_rejected",
        "ledger_sequence_invalid",
        "ledger_supersession_invalid",
        "witness_not_distinct",
        "approver_without_defined_process",
        "comparison_inconsistent",
        "comparison_not_key_holder",
        "policy_class_missing",
        "policy_class_unknown",
        "policy_period_invalid",
        "inventory_invalid",
        "object_identifier_rejected",
        "evidence_environment_rejected",
        "role_register_invalid",
        "key_event_invalid",
        "input_out_of_range",
    }
)


class GovernanceError(Exception):
    """An error carrying only a closed code; never a path, value or message."""

    def __init__(self, code):
        if code not in CODES:
            raise ValueError("unknown governance code")
        super().__init__(code)
        self.code = code


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _no_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise GovernanceError("json_malformed")
        seen[key] = value
    return seen


def _reject_constant(_name):
    raise GovernanceError("json_malformed")


def loads_strict(text):
    """Parse JSON rejecting duplicate keys and NaN/Infinity at every depth."""
    try:
        return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)
    except GovernanceError:
        raise
    except ValueError:
        raise GovernanceError("json_malformed") from None


def read_json_file(path, limit=MAX_INPUT_BYTES):
    """Read one regular file, read-only, no symlink following, bounded; never writes."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise GovernanceError("input_unreadable") from None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise GovernanceError("input_unreadable")
        data = os.read(descriptor, limit + 1)
    except OSError:
        raise GovernanceError("input_unreadable") from None
    finally:
        os.close(descriptor)
    if len(data) > limit:
        raise GovernanceError("input_unreadable")
    try:
        return loads_strict(data.decode("utf-8"))
    except UnicodeDecodeError:
        raise GovernanceError("json_malformed") from None


def is_key_like(value):
    """True if the string contains a run of 32 or more hexadecimal characters anywhere."""
    return isinstance(value, str) and KEY_LIKE.search(value) is not None


def not_key_like(value):
    """Validator for token-like fields that are not exceptions: reject key-like substrings."""
    if is_key_like(value):
        raise ValueError("key-like")
    return value


def is_ref(value):
    """An opaque, non-secret reference: closed character set, bounded, and not key-like."""
    return isinstance(value, str) and REF.fullmatch(value) is not None and not is_key_like(value)


def is_schema_one(value):
    """True only for the integer 1 (a Boolean ``True`` compares equal to 1 and is rejected)."""
    return type(value) is int and value == 1


def valid_timestamp(value):
    """A complete, timezone-aware ISO 8601 timestamp (date, time and offset or Z)."""
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def scan_strings(value):
    """Yield every string value (and key) in a parsed JSON structure."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from scan_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from scan_strings(item)


def reject_object_identifiers(value):
    for text in scan_strings(value):
        if OBJECT_NAME.search(text) or BARE_32HEX.fullmatch(text):
            raise GovernanceError("object_identifier_rejected")


def require_mapping(raw, code="record_malformed"):
    if not isinstance(raw, dict):
        raise GovernanceError(code)
    return raw
