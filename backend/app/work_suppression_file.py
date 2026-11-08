"""Bounded metadata-only trusted local manifest; digest is not authentication."""

import hashlib
import hmac
import json
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.work_lifecycle import Contract, clock

MAX_BYTES = 32768


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class Entry(Contract):
    kind: Literal["note", "party"]
    id: UUID
    forgotten_revision: int = Field(strict=True, ge=2, le=101)
    forgotten_at: datetime

    @model_validator(mode="after")
    def valid(self):
        clock(self.forgotten_at)
        if self.kind == "party" and self.forgotten_revision > 3:
            raise ValueError("Invalid terminal party revision")
        return self


class Body(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["synthetic_work_suppression_manifest"] = "synthetic_work_suppression_manifest"
    export_id: UUID
    workspace_id: UUID
    exported_by: UUID
    source_database_oid: int = Field(strict=True, ge=1)
    generated_at: datetime
    items: tuple[Entry, ...] = Field(max_length=25)

    @model_validator(mode="after")
    def valid(self):
        generated = clock(self.generated_at)
        keys = [(item.kind, str(item.id)) for item in self.items]
        if keys != sorted(set(keys)) or any(
            clock(item.forgotten_at) > generated for item in self.items
        ):
            raise ValueError("Unordered/duplicate/future terminal decisions")
        return self


def digest(body):
    return hashlib.sha256(
        b"butler.synthetic.work-suppression.v1\n" + canonical(body.model_dump(mode="json"))
    ).hexdigest()


class Manifest(Contract):
    body: Body
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def valid(self):
        if not hmac.compare_digest(self.digest, digest(self.body)):
            raise ValueError("Manifest digest mismatch")
        if len(canonical(self.model_dump(mode="json"))) > MAX_BYTES:
            raise ValueError("Manifest too large")
        return self


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def read_json_file(path, *, max_bytes=MAX_BYTES):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or before.st_mode & 0o077
            or not before.st_mode & stat.S_IRUSR
            or before.st_size > max_bytes
        ):
            raise ValueError("Protected regular owner file required")
        data = stream.read(max_bytes + 1)
        after = os.fstat(stream.fileno())
        if len(data) > max_bytes or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("Manifest changed or exceeded bound")
    try:
        value = json.loads(data, object_pairs_hook=_unique)
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid bounded manifest JSON") from error
    return value


def manifest_from_value(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"body", "digest"}
        or not isinstance(value.get("body"), dict)
        or set(value["body"]) != set(Body.model_fields)
        or type(value["body"]["schema_version"]) is not int
    ):
        raise ValueError("Explicit complete manifest header required")
    return Manifest.model_validate(value)


def write_json_file(path, value, *, max_bytes=MAX_BYTES):
    encoded = canonical(value)
    if len(encoded) > max_bytes:
        raise ValueError("Protected JSON exceeds bound")
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
    )
    created = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        parent = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    except BaseException:
        try:
            current = os.stat(path, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current and (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
            os.unlink(path)
        raise


def read_file(path):
    return manifest_from_value(read_json_file(path))


def write_file(path, manifest: Manifest):
    if not isinstance(manifest, Manifest):
        raise TypeError("Typed manifest required")
    write_json_file(path, manifest.model_dump(mode="json"))
