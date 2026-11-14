"""Descriptor-relative closed-set enumeration, invariants and streaming hashing.

Spec 074 sections 3.3, 3.4, 3.6, 3.7 and 3.8. Everything here is read-only: the tool never
writes inside the set, never follows a symlink, never changes a mode and never hashes before the
type, mode, link, entry-count and size checks of a member have passed.
"""

import errno
import hashlib
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass, field

from app.recovery_set.format import (
    KIND_DUMP,
    KIND_LOCK,
    KIND_MARKER,
    KIND_OBJECT,
    LOCK_PATH,
    MARKER_PATH,
    OBJECT_NAME_RE,
    PENDING_PREFIX,
    CodedError,
    Limits,
)

GROUP_OTHER_READ_WRITE = 0o066
GROUP_OTHER_ANY = 0o077
_OBJECT_NAME = re.compile(OBJECT_NAME_RE)
_FLAGS_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def read_protected_file(
    path, *, max_bytes, unsafe_code, too_large_code, any_group_other_bit, require_owner
):
    """Bounded read of a single-link regular file with no group or other bits (spec 3.6)."""
    mask = GROUP_OTHER_ANY if any_group_other_bit else GROUP_OTHER_READ_WRITE
    try:
        descriptor = os.open(path, _FLAGS_READ)
    except OSError as error:
        raise CodedError(unsafe_code) from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (require_owner and before.st_uid != os.geteuid())
            or before.st_mode & mask
            or not before.st_mode & stat.S_IRUSR
        ):
            raise CodedError(unsafe_code)
        if before.st_size > max_bytes:
            raise CodedError(too_large_code)
        chunks, remaining = [], max_bytes + 1
        while remaining:
            block = os.read(descriptor, min(remaining, 65536))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(data) > max_bytes:
            raise CodedError(too_large_code)
        if (before.st_size, before.st_ino, before.st_mtime_ns) != (
            after.st_size,
            after.st_ino,
            after.st_mtime_ns,
        ) or len(data) != before.st_size:
            raise CodedError(unsafe_code)
        return data
    except OSError as error:
        raise CodedError(unsafe_code) from error
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class Found:
    path: str
    kind: str
    size: int
    ino: int
    dev: int
    mtime_ns: int

    def signature(self):
        return (self.path, self.size, self.ino, self.dev, self.mtime_ns)


@dataclass
class Scan:
    found: dict = field(default_factory=dict)  # path -> Found (allowlisted, invariants held)
    flagged: set = field(default_factory=set)  # allowlisted paths present but violating
    violations: list = field(default_factory=list)  # reason codes in the fixed detection order
    pending: bool = False
    archive_dir: bool = False
    complete: bool = True  # False when the entry limit stopped the listing

    def add(self, code):
        self.violations.append(code)

    def sorted_found(self):
        return sorted(self.found.values(), key=lambda item: item.path.encode())

    def archive_signature(self):
        return (
            self.archive_dir,
            self.pending,
            tuple(item.signature() for item in self.sorted_found() if item.kind != KIND_DUMP),
        )

    def dump_signature(self):
        dump = self.found.get("database.dump")
        return None if dump is None else dump.signature()


def _name_key(name):
    return os.fsencode(name)


def _member_violation(info, *, directory=False):
    if stat.S_ISLNK(info.st_mode):
        return "set_member_symlink"
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            return "set_member_not_regular"
    else:
        if not stat.S_ISREG(info.st_mode):
            return "set_member_not_regular"
        if info.st_nlink != 1:
            return "set_member_hardlinked"
    if info.st_mode & GROUP_OTHER_READ_WRITE:
        return "set_member_unsafe_mode"
    return None


def _path_info(name, dir_fd):
    """Metadata by ``fstat`` on an ``O_PATH`` descriptor: no follow, no device open."""
    descriptor = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
    try:
        return os.fstat(descriptor)
    finally:
        os.close(descriptor)


def _unexpected_code(name, dir_fd):
    try:
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except OSError:
        return "set_member_unexpected"
    return "set_directory_unexpected" if stat.S_ISDIR(info.st_mode) else "set_member_unexpected"


def _open_directory(name, dir_fd=None):
    """Open a directory without following a symlink; classify only failures (code choice)."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        return os.open(name, flags, dir_fd=dir_fd)
    except OSError as error:
        if error.errno == errno.ENOENT:
            raise CodedError("set_member_missing") from error
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            try:
                info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            except OSError as inner:
                raise CodedError("io_error") from inner
            raise CodedError(
                "set_member_symlink" if stat.S_ISLNK(info.st_mode) else "set_member_not_regular"
            ) from error
        raise CodedError("io_error") from error


class OpenSet:
    def __init__(self, set_fd, limits):
        self.set_fd, self.archive_fd, self.limits = set_fd, None, limits

    def close(self):
        for descriptor in (self.archive_fd, self.set_fd):
            if descriptor is not None:
                os.close(descriptor)
        self.archive_fd = None

    def _list(self, descriptor, cap):
        names = []
        try:
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    names.append(entry.name)
                    if len(names) > cap:
                        break
        except OSError as error:
            raise CodedError("io_error") from error
        return sorted(names, key=_name_key)

    def scan(self, archive_declared=None):
        """Enumerate once. ``archive_declared`` None means generate (descend if present)."""
        scan, limits = Scan(), self.limits
        info = os.fstat(self.set_fd)
        if info.st_mode & GROUP_OTHER_READ_WRITE:
            scan.add("set_member_unsafe_mode")
        names = self._list(self.set_fd, limits.total_members + 1)
        if len(names) > limits.total_members + 1:  # pragma: no cover - guarded by the cap
            scan.add("set_entry_limit_exceeded")
        if len({name.casefold() for name in names}) != len(names):
            scan.add("set_enumeration_ambiguous")
        archive_present = False
        for name in names:
            if name == "database.dump":
                self._member(scan, name, "database.dump", KIND_DUMP, self.set_fd)
            elif name == "archive":
                archive_present = True
            else:
                scan.add(_unexpected_code(name, self.set_fd))
        scan.archive_dir = archive_present
        if archive_present:
            if archive_declared is False:
                scan.add("set_directory_unexpected")
            else:
                self._scan_archive(scan)
        return scan

    def _member(self, scan, name, path, kind, dir_fd):
        try:
            info = _path_info(name, dir_fd)
        except OSError as error:
            raise CodedError("io_error") from error
        violation = _member_violation(info)
        limit = {
            KIND_DUMP: self.limits.dump_bytes,
            KIND_MARKER: self.limits.marker_bytes,
            KIND_LOCK: self.limits.object_bytes,
            KIND_OBJECT: self.limits.object_bytes,
        }[kind]
        if violation is None and info.st_size > limit:
            violation = (
                "archive_marker_mismatch" if kind == KIND_MARKER else "set_size_limit_exceeded"
            )
        if violation is not None:
            scan.add(violation)
            scan.flagged.add(path)
            return
        scan.found[path] = Found(
            path, kind, info.st_size, info.st_ino, info.st_dev, info.st_mtime_ns
        )

    def _scan_archive(self, scan):
        limits = self.limits
        try:
            self.archive_fd = _open_directory("archive", self.set_fd)
        except CodedError as error:
            scan.add(error.code)
            return
        info = os.fstat(self.archive_fd)
        if info.st_mode & GROUP_OTHER_READ_WRITE:
            scan.add("set_member_unsafe_mode")
        names = self._list(self.archive_fd, limits.archive_entries)
        if len(names) > limits.archive_entries:
            scan.add("set_entry_limit_exceeded")
            scan.complete = False
            return
        if any(name.startswith(PENDING_PREFIX) for name in names):
            scan.pending = True
            scan.add("archive_pending_objects_present")
        if len({name.casefold() for name in names}) != len(names):
            scan.add("set_enumeration_ambiguous")
        payload = 0
        for name in names:
            if name.startswith(PENDING_PREFIX):
                continue
            if name == ".archive.json":
                self._member(scan, name, MARKER_PATH, KIND_MARKER, self.archive_fd)
            elif name == ".archive.lock":
                self._member(scan, name, LOCK_PATH, KIND_LOCK, self.archive_fd)
            elif _OBJECT_NAME.fullmatch(name):
                path = f"archive/{name}"
                self._member(scan, name, path, KIND_OBJECT, self.archive_fd)
                if path in scan.found:
                    payload += scan.found[path].size
            else:
                scan.add(_unexpected_code(name, self.archive_fd))
        if payload > limits.archive_payload_bytes:
            scan.add("set_size_limit_exceeded")

    def compare(self, scan, members, archive_present):
        """Closed-world comparison with the manifest member list (spec 3.4 rule 6)."""
        if not scan.complete:
            return
        declared = {m.path: m for m in members}
        for path in sorted(declared, key=lambda item: item.encode()):
            if path not in scan.found and path not in scan.flagged:
                scan.add("set_member_missing")
        for item in scan.sorted_found():
            if item.path not in declared:
                scan.add("set_member_unexpected")
        for item in scan.sorted_found():
            member = declared.get(item.path)
            if member is not None and member.size != item.size:
                scan.add("set_member_size_mismatch")

    def hash_member(self, found: Found, keep=False):
        """Open once, ``fstat``, stream with a fixed buffer, ``fstat`` again (spec 3.4 rule 8)."""
        directory = self.set_fd if found.kind == KIND_DUMP else self.archive_fd
        name = found.path.split("/")[-1]
        try:
            descriptor = os.open(name, _FLAGS_READ, dir_fd=directory)
        except OSError as error:
            raise CodedError("set_changed_during_read") from error
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_mode & GROUP_OTHER_READ_WRITE
                or (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns)
                != (found.ino, found.dev, found.size, found.mtime_ns)
            ):
                raise CodedError("set_changed_during_read")
            digest, total, chunks, limit = hashlib.sha256(), 0, [], found.size + 1
            while True:
                block = os.read(descriptor, min(self.limits.buffer_bytes, limit - total))
                if not block:
                    break
                total += len(block)
                if total > found.size:
                    raise CodedError("set_changed_during_read")
                digest.update(block)
                if keep:
                    chunks.append(block)
            after = os.fstat(descriptor)
            if total != found.size or (after.st_ino, after.st_size, after.st_mtime_ns) != (
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ):
                raise CodedError("set_changed_during_read")
            return digest.hexdigest(), (b"".join(chunks) if keep else None)
        except OSError as error:
            raise CodedError("io_error") from error
        finally:
            os.close(descriptor)


@contextmanager
def open_set(path, limits: Limits):
    descriptor = _open_directory(path)
    handle = OpenSet(descriptor, limits)
    try:
        yield handle
    finally:
        handle.close()
