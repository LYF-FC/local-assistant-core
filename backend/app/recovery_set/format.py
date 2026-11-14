"""Closed manifest format, canonical JSON, limits and reason codes (spec 074 sections 3.8, 4, 7.3)."""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

MAC_DOMAIN = b"butler.installation-recovery-set-mac.v1\n"
FINGERPRINT_DOMAIN = b"butler.installation-recovery-set-key-fingerprint.v1\n"
HASH_DOMAIN = b"butler.installation-recovery-set-manifest-hash.v1\n"
PURPOSE = "butler.recovery-set.v1"
KEY_PURPOSE = "installation_recovery_set"
TOOL_VERSION = "074.1"

# The reason-code vocabulary is closed (spec 7.3); an unknown code is a programming error.
REASON_CODES = frozenset(
    {
        "trust_input_missing", "trust_input_malformed", "freshness_requested_without_expected_hash",
        "paths_overlap",
        "key_file_unsafe", "key_file_malformed", "key_namespace_mismatch",
        "key_installation_mismatch", "key_fingerprint_mismatch",
        "manifest_file_unsafe", "manifest_too_large", "manifest_malformed",
        "manifest_duplicate_key", "manifest_unknown_field", "manifest_noncanonical",
        "manifest_schema_unsupported", "manifest_key_reference_mismatch",
        "manifest_authentication_failed", "manifest_path_unsafe",
        "installation_mismatch", "schema_head_mismatch", "schema_chain_inconsistent",
        "schema_unknown_to_verifier", "archive_expectation_mismatch",
        "set_member_missing", "set_member_unexpected", "set_directory_unexpected",
        "set_path_unsafe", "set_member_not_regular", "set_member_symlink",
        "set_member_hardlinked", "set_member_unsafe_mode", "set_member_size_mismatch",
        "set_member_hash_mismatch", "set_entry_limit_exceeded", "set_size_limit_exceeded",
        "set_enumeration_ambiguous", "set_changed_during_read", "archive_marker_mismatch",
        "archive_pending_objects_present", "archive_changed_during_generation",
        "freshness_expected_hash_mismatch", "freshness_required_not_established",
        "filesystem_unsupported", "output_exists", "output_unsafe", "io_error",
        "publication_durability_uncertain", "internal_error",
    }
)  # fmt: skip


class CodedError(Exception):
    """An error carrying only a closed reason code; never a path, value or message."""

    def __init__(self, code, further=0):
        if code not in REASON_CODES:
            raise ValueError("unknown reason code")
        super().__init__(code)
        self.code = code
        self.further = further


# Provisional placeholder only: this is NOT an approved or measured operational capacity
# (spec 3.8, owner decision O8). It exists so limit handling can be specified and tested; the
# real ceiling is deferred to measured resource testing and a separate owner decision.
PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES = 64 * 1024**3


@dataclass(frozen=True)
class Limits:
    """Spec 3.8. Overridable only by a function parameter (test-only injection point)."""

    archive_entries: int = 8192  # existing-code-derived (document_archive.MAX_ENTRIES)
    object_bytes: int = 131072  # existing-code-derived (document_archive.MAX_OBJECT)
    archive_payload_bytes: int = 64 * 1024 * 1024  # existing-code-derived (MAX_BYTES)
    key_file_bytes: int = 2048  # existing-code-derived (Work key file bound)
    manifest_bytes: int = 4 * 1024 * 1024  # provisional engineering limit
    buffer_bytes: int = 1024 * 1024  # provisional engineering limit
    dump_bytes: int = PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES  # unapproved placeholder
    marker_bytes: int = 256  # spec 3.4 rule 9

    @property
    def total_members(self):
        # Archive entries include marker and lock; the dump is one further member.
        return self.archive_entries + 1


DEFAULT_LIMITS = Limits()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CodedError("manifest_duplicate_key")
        result[key] = value
    return result


def _no_float(_):
    raise CodedError("manifest_malformed")


def parse_json(data, duplicate_code="manifest_duplicate_key", malformed_code="manifest_malformed"):
    """Strict JSON: no duplicate keys at any depth, no floats, no NaN/Infinity constants."""

    def pairs(items):
        try:
            return _pairs(items)
        except CodedError as error:
            raise CodedError(duplicate_code) from error

    try:
        text = data.decode("utf-8")
        return json.loads(
            text, object_pairs_hook=pairs, parse_float=_no_float, parse_constant=_no_float
        )
    except CodedError as error:
        raise CodedError(
            duplicate_code if error.code == "manifest_duplicate_key" else malformed_code
        ) from error
    except (ValueError, RecursionError) as error:
        raise CodedError(malformed_code) from error


HEX64 = r"[a-f0-9]{64}"
UUID_RE = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
REVISION_RE = r"[A-Za-z0-9_]{1,64}"
SAFE_VERSION_RE = r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}"
TIMESTAMP_RE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
OBJECT_NAME_RE = r"[a-f0-9]{32}-v[1-9][0-9]{0,8}\.original"
PENDING_PREFIX = ".pending-"
DUMP_PATH = "database.dump"
MARKER_PATH = "archive/.archive.json"
LOCK_PATH = "archive/.archive.lock"
_OBJECT_PATH = re.compile(r"archive/" + OBJECT_NAME_RE)
KIND_DUMP, KIND_MARKER, KIND_LOCK, KIND_OBJECT = (
    "dump",
    "archive_marker",
    "archive_lock",
    "archive_object",
)


def kind_of_path(path):
    """The single allowlisted spelling of a member path (spec 3.4 rules 2 and 3), or None."""
    if path == DUMP_PATH:
        return KIND_DUMP
    if path == MARKER_PATH:
        return KIND_MARKER
    if path == LOCK_PATH:
        return KIND_LOCK
    if _OBJECT_PATH.fullmatch(path):
        return KIND_OBJECT
    return None


def valid_timestamp(value):
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def valid_uuid(value):
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


class _PathUnsafe(ValueError):
    pass


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _hex(value):
    if not re.fullmatch(HEX64, value):
        raise ValueError("hex64 required")
    return value


class Member(_Closed):
    path: str
    kind: Literal["dump", "archive_marker", "archive_lock", "archive_object"]
    size: int = Field(ge=0, le=2**62)
    sha256: str

    @field_validator("path")
    @classmethod
    def _path(cls, value):
        if kind_of_path(value) is None:
            raise _PathUnsafe("unsafe member path")
        return value

    @field_validator("sha256")
    @classmethod
    def _sha(cls, value):
        return _hex(value)

    @model_validator(mode="after")
    def _kind(self):
        if kind_of_path(self.path) != self.kind:
            raise _PathUnsafe("kind does not match path")
        return self


class Generator(_Closed):
    tool_version: str

    @field_validator("tool_version")
    @classmethod
    def _v(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,31}", value):
            raise ValueError("tool version")
        return value


class Installation(_Closed):
    installation_id: str

    @field_validator("installation_id")
    @classmethod
    def _v(cls, value):
        if not valid_uuid(value):
            raise ValueError("uuid")
        return value


class Schema(_Closed):
    head: str
    revisions: list[str] = Field(min_length=1, max_length=2048)

    @field_validator("head")
    @classmethod
    def _h(cls, value):
        if not re.fullmatch(REVISION_RE, value):
            raise ValueError("revision")
        return value

    @field_validator("revisions")
    @classmethod
    def _r(cls, value):
        if any(not re.fullmatch(REVISION_RE, item) for item in value):
            raise ValueError("revision")
        return value


def _version(value):
    if value is not None and not re.fullmatch(SAFE_VERSION_RE, value):
        raise ValueError("version")
    return value


class Packages(_Closed):
    fastapi: str | None
    sqlalchemy: str | None
    psycopg: str | None
    pydantic: str | None

    @field_validator("fastapi", "sqlalchemy", "psycopg", "pydantic")
    @classmethod
    def _v(cls, value):
        return _version(value)


class Application(_Closed):
    api_version: str
    python_version: str
    packages: Packages

    @field_validator("api_version", "python_version")
    @classmethod
    def _v(cls, value):
        return _version(value)


class ModelAbsent(_Closed):
    declared: Literal[False]


class ModelDeclared(_Closed):
    declared: Literal[True]
    tag: str
    digest: str

    @field_validator("tag")
    @classmethod
    def _t(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,96}:[A-Za-z0-9_.-]{1,30}", value):
            raise ValueError("model tag")
        return value

    @field_validator("digest")
    @classmethod
    def _d(cls, value):
        return _hex(value)


class WorkReferences(_Closed):
    suppression_manifest_sha256: str | None
    source_checkpoint_sha256: str | None

    @field_validator("suppression_manifest_sha256", "source_checkpoint_sha256")
    @classmethod
    def _h(cls, value):
        return None if value is None else _hex(value)


class ArchiveAbsent(_Closed):
    present: Literal[False]


class ArchivePresent(_Closed):
    present: Literal[True]
    root_id: str
    object_count: int = Field(ge=0, le=8190)

    @field_validator("root_id")
    @classmethod
    def _r(cls, value):
        if not valid_uuid(value):
            raise ValueError("uuid")
        return value


class Body(_Closed):
    set_id: str
    created_at: str
    generator: Generator
    installation: Installation
    schema_: Schema = Field(alias="schema")
    application: Application
    model: Annotated[ModelAbsent | ModelDeclared, Field(discriminator="declared")]
    work_references: WorkReferences
    archive: Annotated[ArchiveAbsent | ArchivePresent, Field(discriminator="present")]
    members: list[Member] = Field(min_length=1, max_length=8193)

    @field_validator("set_id")
    @classmethod
    def _s(cls, value):
        if not valid_uuid(value):
            raise ValueError("uuid")
        return value

    @field_validator("created_at")
    @classmethod
    def _c(cls, value):
        if not re.fullmatch(TIMESTAMP_RE, value) or not valid_timestamp(value):
            raise ValueError("timestamp")
        return value


class Payload(_Closed):
    key_id: str
    key_fingerprint: str
    body: Body

    @field_validator("key_id")
    @classmethod
    def _k(cls, value):
        if not valid_uuid(value):
            raise ValueError("uuid")
        return value

    @field_validator("key_fingerprint")
    @classmethod
    def _f(cls, value):
        return _hex(value)


class Envelope(_Closed):
    schema_version: Literal[1]
    purpose: Literal["butler.recovery-set.v1"]
    payload: Payload
    algorithm: Literal["HMAC-SHA256"]
    mac: str

    @field_validator("mac")
    @classmethod
    def _m(cls, value):
        return _hex(value)


def dump_model(model):
    return model.model_dump(mode="json", by_alias=True)


def manifest_hash(payload_value):
    return hashlib.sha256(HASH_DOMAIN + canonical(payload_value)).hexdigest()


def members_digest(members):
    return hashlib.sha256(canonical([dump_model(m) for m in members])).hexdigest()


def _classify(error: ValidationError):
    kinds = {item["type"] for item in error.errors()}
    if "extra_forbidden" in kinds:
        return "manifest_unknown_field"
    for item in error.errors():
        if isinstance(item.get("ctx", {}).get("error"), _PathUnsafe):
            return "manifest_path_unsafe"
    return "manifest_malformed"


def parse_manifest(data, limits=DEFAULT_LIMITS):
    """Bytes -> (Envelope, parsed payload dict). Raises CodedError with a manifest_* code only."""
    if len(data) > limits.manifest_bytes:
        raise CodedError("manifest_too_large")
    value = parse_json(data)
    if not isinstance(value, dict):
        raise CodedError("manifest_malformed")
    version = value.get("schema_version")
    if type(version) is not int or version != 1 or value.get("purpose") != PURPOSE:
        raise CodedError("manifest_schema_unsupported")
    try:
        envelope = Envelope.model_validate(value)
    except ValidationError as error:
        raise CodedError(_classify(error)) from error
    body = envelope.payload.body
    paths = [m.path for m in body.members]
    if len(set(paths)) != len(paths) or len({p.casefold() for p in paths}) != len(paths):
        raise CodedError("set_enumeration_ambiguous")
    if [p.encode() for p in paths] != sorted(p.encode() for p in paths):
        raise CodedError("manifest_noncanonical")
    kinds = [m.kind for m in body.members]
    objects = kinds.count(KIND_OBJECT)
    has_archive_files = KIND_MARKER in kinds or KIND_LOCK in kinds or objects
    archive = body.archive
    if (
        kinds.count(KIND_DUMP) != 1
        or kinds.count(KIND_MARKER) != kinds.count(KIND_LOCK)
        or kinds.count(KIND_MARKER) > 1
        or bool(has_archive_files) != archive.present
        or (archive.present and (kinds.count(KIND_MARKER) != 1 or archive.object_count != objects))
        or len(body.schema_.revisions) < 1
    ):
        raise CodedError("manifest_malformed")
    if canonical(dump_model(envelope)) != data:
        raise CodedError("manifest_noncanonical")
    return envelope, value["payload"]
