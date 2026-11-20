"""Bounded synthetic dump staging; no executor, activation, archive or operational API.

The final handoff is an immutable <=16 MiB snapshot, read *after* Spec 074 verifies
the private staged copy, then compared with its authenticated dump digest. A
consumer must use these bytes directly, never reopen a staged/source pathname.
The caller's environment declaration is a scope prerequisite, not proof that
arbitrary input data or a consumer is safe. Non-Work reconciliation is absent:
every result remains quarantined and never establishes restore eligibility.
"""

import hashlib
import os
import re
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from app.recovery_set.cli import parse_trust
from app.recovery_set.format import REASON_CODES, CodedError, Limits, valid_uuid
from app.recovery_set.fsset import open_directory_nofollow, open_set, read_protected_file
from app.recovery_set.result import VERIFIED_KEYS, Result
from app.recovery_set.verify import verify

MAX_DUMP_BYTES = 16 * 1024 * 1024
_HEX = re.compile(r"[a-f0-9]{64}")
_HEAD = re.compile(r"[A-Za-z0-9_]{1,64}")
_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_WRITE_NEW = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
_CODES = frozenset(
    {
        "staging_scope_required",
        "staging_trust_invalid",
        "staging_archive_unsupported",
        "staging_source_rejected",
        "staging_verification_failed",
        "staging_bytes_changed",
        "staging_io_error",
        "staging_cleanup_failed",
    }
)


class StagingError(Exception):
    """Only closed codes leave expected staging failures; never input bytes or paths."""

    def __init__(self, code, verification_reasons=()):
        if code not in _CODES or any(item not in REASON_CODES for item in verification_reasons):
            raise ValueError("unknown staging code")
        super().__init__(code)
        self.code = code
        self.verification_reasons = tuple(verification_reasons)


@dataclass(frozen=True)
class StagingExpectations:
    installation_id: str
    schema_head: str
    key_path: Path = field(repr=False)
    key_fingerprint: str = field(repr=False)
    expected_manifest_hash: str = field(repr=False)
    environment: str = "disposable-synthetic"


@dataclass(frozen=True)
class ConsumedDump:
    """Consumer return is opaque: it cannot promote this wrapper out of quarantine."""

    consumer_result: object = field(repr=False)
    dump_sha256: str
    installation_id: str
    schema_head: str

    @property
    def quarantined(self):
        return True

    @property
    def restore_eligible(self):
        return False


@dataclass(frozen=True)
class VerifiedDump:
    """Internal test-slice artifact. Holding it never authorizes operational restore."""

    dump_bytes: bytes = field(repr=False)
    dump_sha256: str
    manifest_hash: str
    installation_id: str
    schema_head: str

    @property
    def quarantined(self):
        return True

    @property
    def restore_eligible(self):
        return False

    def consume(self, consumer):
        """Supply the same immutable snapshot and check its binding before/after use.

        A trusted synthetic consumer supplies it directly to stdin, for example.
        Its return/exception does not prove restored contents or activation safety;
        the separate read-only database-binding inspection must follow success.
        """
        if type(self.dump_bytes) is not bytes or len(self.dump_bytes) > MAX_DUMP_BYTES:
            raise StagingError("staging_bytes_changed")
        if hashlib.sha256(self.dump_bytes).hexdigest() != self.dump_sha256:
            raise StagingError("staging_bytes_changed")
        result = consumer(self.dump_bytes)
        if hashlib.sha256(self.dump_bytes).hexdigest() != self.dump_sha256:
            raise StagingError("staging_bytes_changed")
        return ConsumedDump(result, self.dump_sha256, self.installation_id, self.schema_head)


def _path(value):
    if not isinstance(value, (str, Path)):
        raise StagingError("staging_trust_invalid")
    value = os.fspath(value)
    if not value or "\x00" in value:
        raise StagingError("staging_trust_invalid")
    return value


def _trust(source_set, manifest_path, scratch_parent, expectations):
    if not isinstance(expectations, StagingExpectations):
        raise StagingError("staging_trust_invalid")
    if expectations.environment != "disposable-synthetic":
        raise StagingError("staging_scope_required")
    values = (
        expectations.installation_id,
        expectations.schema_head,
        expectations.key_fingerprint,
        expectations.expected_manifest_hash,
    )
    if (
        any(not isinstance(value, str) for value in values)
        or not valid_uuid(values[0])
        or not _HEAD.fullmatch(values[1])
        or not _HEX.fullmatch(values[2])
        or not _HEX.fullmatch(values[3])
    ):
        raise StagingError("staging_trust_invalid")
    source, manifest, parent = map(_path, (source_set, manifest_path, scratch_parent))
    key = _path(expectations.key_path)
    for spell in (os.path.abspath, os.path.realpath):
        source_path, parent_path = spell(source), spell(parent)
        if os.path.commonpath((source_path, parent_path)) == source_path:
            raise StagingError("staging_trust_invalid")
    _, trust = parse_trust(
        [
            "verify",
            "--set",
            source,
            "--manifest",
            manifest,
            "--recovery-key",
            key,
            "--expected-key-fingerprint",
            values[2],
            "--expected-installation-id",
            values[0],
            "--expected-schema-head",
            values[1],
            "--expected-manifest-hash",
            values[3],
            "--require-freshness",
            "--expect-archive",
            "absent",
        ]
    )
    return trust, parent


def _verified_references(verification, expectations):
    if (
        not isinstance(verification, Result)
        or not isinstance(verification.reasons, list)
        or any(
            not isinstance(code, str) or code not in REASON_CODES for code in verification.reasons
        )
        or not isinstance(verification.extras, dict)
    ):
        raise StagingError("staging_verification_failed")
    if (
        verification.exit_status() != 0
        or verification.operation != "verify"
        or verification.integrity != "integrity_valid"
        or verification.authenticity != "authenticity_valid"
        or verification.expectations != "expectations_met"
        or verification.freshness != "freshness_match"
    ):
        raise StagingError("staging_verification_failed", verification.reasons)
    references = verification.extras.get("verified_references")
    if (
        not isinstance(references, dict)
        or set(references) != VERIFIED_KEYS
        or not isinstance(references.get("set_id"), str)
        or not valid_uuid(references["set_id"])
        or any(
            not isinstance(references.get(name), str) or not _HEX.fullmatch(references[name])
            for name in ("manifest_hash", "dump_sha256", "members_digest")
        )
        or references["manifest_hash"] != expectations.expected_manifest_hash
        or verification.extras.get("manifest_hash") != expectations.expected_manifest_hash
        or type(verification.extras.get("member_count")) is not int
        or verification.extras["member_count"] != 1
        or type(verification.extras.get("member_bytes")) is not int
        or not 0 <= verification.extras["member_bytes"] <= MAX_DUMP_BYTES
    ):
        raise StagingError("staging_verification_failed")
    return references


def _source_dump(path, limits):
    with open_set(path, limits) as handle:
        first = handle.scan(archive_declared=None)
        if first.archive_dir:
            raise StagingError("staging_archive_unsupported")
        if first.violations or set(first.found) != {"database.dump"}:
            raise StagingError("staging_source_rejected", first.violations[:1])
        _, data = handle.hash_member(first.found["database.dump"], keep=True)
        second = handle.scan(archive_declared=None)
        if (
            second.violations
            or second.archive_dir
            or set(second.found) != {"database.dump"}
            or first.dump_signature() != second.dump_signature()
        ):
            raise StagingError("staging_source_rejected")
        return data


def _write(directory, name, data):
    descriptor = os.open(name, _WRITE_NEW, 0o600, dir_fd=directory)
    try:
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("staging write made no progress")
            remaining = remaining[written:]
    finally:
        os.close(descriptor)


@contextmanager
def _stage(parent):
    parent_fd = open_directory_nofollow(parent)
    root_fd = set_fd = None
    root_created = set_created = False
    name = f"spec075-{uuid.uuid4().hex}"
    try:
        info = os.fstat(parent_fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise StagingError("staging_source_rejected")
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        root_created = True
        root_fd = os.open(name, _DIRECTORY, dir_fd=parent_fd)
        os.mkdir("set", 0o700, dir_fd=root_fd)
        set_created = True
        set_fd = os.open("set", _DIRECTORY, dir_fd=root_fd)
        yield Path(os.path.abspath(parent)) / name, root_fd, set_fd
    finally:
        failed = False

        def remove(function, entry, directory):
            nonlocal failed
            try:
                function(entry, dir_fd=directory)
            except FileNotFoundError:
                pass
            except OSError:
                failed = True

        if set_fd is not None:
            remove(os.unlink, "database.dump", set_fd)
            os.close(set_fd)
        if root_fd is not None:
            if set_created:
                remove(os.rmdir, "set", root_fd)
            remove(os.unlink, "manifest.json", root_fd)
            os.close(root_fd)
        if root_created:
            remove(os.rmdir, name, parent_fd)
        os.close(parent_fd)
        if failed:
            raise StagingError("staging_cleanup_failed")


def stage_synthetic_dump(source_set, manifest_path, scratch_parent, expectations):
    """Copy/verify/snapshot one small dump, then discard the private disk stage.

    No archive, key generation, database action or consumer invocation occurs here.
    Expected failures use closed codes. Unexpected programming errors are not
    disguised as ordinary verification failures.
    """
    try:
        trust, parent = _trust(source_set, manifest_path, scratch_parent, expectations)
        limits = Limits(dump_bytes=MAX_DUMP_BYTES)
        dump = _source_dump(trust["set"], limits)
        manifest = read_protected_file(
            trust["manifest"],
            max_bytes=limits.manifest_bytes,
            unsafe_code="manifest_file_unsafe",
            too_large_code="manifest_too_large",
            any_group_other_bit=False,
            require_owner=False,
        )
        with _stage(parent) as (root, root_fd, set_fd):
            _write(set_fd, "database.dump", dump)
            _write(root_fd, "manifest.json", manifest)
            del dump
            staged = {**trust, "set": str(root / "set"), "manifest": str(root / "manifest.json")}
            verification = verify(staged, limits=limits)
            references = _verified_references(verification, expectations)
            snapshot = read_protected_file(
                root / "set" / "database.dump",
                max_bytes=MAX_DUMP_BYTES,
                unsafe_code="set_changed_during_read",
                too_large_code="set_size_limit_exceeded",
                any_group_other_bit=True,
                require_owner=True,
            )
            digest = hashlib.sha256(snapshot).hexdigest()
            if (
                digest != references["dump_sha256"]
                or len(snapshot) != verification.extras["member_bytes"]
            ):
                raise StagingError("staging_bytes_changed")
            result = VerifiedDump(
                snapshot,
                digest,
                references["manifest_hash"],
                expectations.installation_id,
                expectations.schema_head,
            )
        return result
    except CodedError as error:
        raise StagingError("staging_source_rejected", (error.code,)) from None
    except OSError:
        raise StagingError("staging_io_error") from None
