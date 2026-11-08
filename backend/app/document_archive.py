"""Private bounded local archive. Disk objects are copies, never application authority."""

import argparse
import fcntl
import json
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

MAX_OBJECT = 131072
MAX_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 8192
MARKER = ".archive.json"
LOCK = ".archive.lock"
OBJECT = re.compile(r"([a-f0-9]{32})-v([1-9]|[1-4][0-9]|50)\.original")
PENDING = re.compile(r"\.pending-([a-f0-9]{32})-[a-f0-9]{32}")


class ArchiveError(Exception):
    """Never include paths, source data or underlying exceptions in public output."""


def checked(fd, *, directory=False):
    info = os.fstat(fd)
    if (
        info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise ArchiveError("Unsafe archive permissions or object type")
    return info


def open_root(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or path == Path("/"):
        raise ArchiveError("An absolute private directory is required")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        checked(fd, directory=True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_file(directory, name, limit=MAX_OBJECT):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = checked(fd)
        if info.st_size > limit:
            raise ArchiveError("Archive object exceeds its limit")
        chunks, remaining = [], limit + 1
        while remaining:
            block = os.read(fd, min(remaining, 65536))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        data = b"".join(chunks)
        if len(data) > limit or len(data) != info.st_size:
            raise ArchiveError("Archive object changed or exceeded its limit")
        return data
    finally:
        os.close(fd)


def write_all(fd, data):
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise ArchiveError("Archive write incomplete")
        view = view[written:]
    os.fsync(fd)


class Archive:
    def __init__(self, fd, root_id):
        self.fd, self.root_id = fd, root_id

    def entries(self):
        result, linked = [], {}
        with os.scandir(self.fd) as entries:
            for entry in entries:
                if len(result) >= MAX_ENTRIES:
                    raise ArchiveError("Archive entry limit reached")
                name = entry.name
                if (
                    name not in {LOCK, MARKER}
                    and not OBJECT.fullmatch(name)
                    and not PENDING.fullmatch(name)
                ):
                    raise ArchiveError("Unknown archive entry")
                info = entry.stat(follow_symlinks=False)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink not in {1, 2}
                    or (info.st_nlink == 2 and name in {MARKER, LOCK})
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                ):
                    raise ArchiveError("Unsafe archive entry")
                if name not in {LOCK, MARKER} and info.st_size > MAX_OBJECT:
                    raise ArchiveError("Archive object exceeds its limit")
                result.append((name, info.st_size))
                if info.st_nlink == 2:
                    linked.setdefault((info.st_dev, info.st_ino), []).append(name)
        # A crash between link publication and temporary unlink has exactly two
        # known names for one inode, belonging to the same document. Reject every
        # other hardlink, including any link outside this private root.
        for names in linked.values():
            if len(names) != 2:
                raise ArchiveError("Unmanaged hardlink")
            pending = [PENDING.fullmatch(name) for name in names if PENDING.fullmatch(name)]
            objects = [OBJECT.fullmatch(name) for name in names if OBJECT.fullmatch(name)]
            if len(pending) != 1 or len(objects) != 1 or pending[0][1] != objects[0][1]:
                raise ArchiveError("Unmanaged hardlink")
        return result

    @staticmethod
    def key(document_id, revision):
        if (
            not isinstance(document_id, UUID)
            or type(revision) is not int
            or not 1 <= revision <= 50
        ):
            raise ArchiveError("Invalid archive identity")
        return f"{document_id.hex}-v{revision}.original"

    def read(self, document_id, revision):
        return read_file(self.fd, self.key(document_id, revision))

    def discard_pending(self, document_id):
        for name, _ in self.entries():
            match = PENDING.fullmatch(name)
            if match and match[1] == document_id.hex:
                os.unlink(name, dir_fd=self.fd)
        os.fsync(self.fd)

    def put(self, document_id, revision, data):
        if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_OBJECT:
            raise ArchiveError("Invalid archive original")
        key = self.key(document_id, revision)
        self.discard_pending(document_id)
        try:
            previous = read_file(self.fd, key)
        except FileNotFoundError:
            pass
        else:
            if previous != data:
                raise ArchiveError("Archive integrity mismatch; do not overwrite")
            return
        entries = self.entries()
        if (
            len(entries) + 2 > MAX_ENTRIES
            or sum(size for name, size in entries if name not in {MARKER, LOCK}) + len(data)
            > MAX_BYTES
        ):
            raise ArchiveError("Archive capacity reached")
        pending = f".pending-{document_id.hex}-{uuid4().hex}"
        fd = os.open(
            pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd
        )
        try:
            write_all(fd, data)
        finally:
            os.close(fd)
        # Never replace a conflicting object. All legitimate writers hold this root's lock.
        os.link(pending, key, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
        os.unlink(pending, dir_fd=self.fd)
        os.fsync(self.fd)
        if read_file(self.fd, key) != data:
            raise ArchiveError("Published original did not verify")

    def purge(self, document_id):
        if not isinstance(document_id, UUID):
            raise ArchiveError("Invalid archive identity")
        for name, _ in self.entries():
            match = OBJECT.fullmatch(name) or PENDING.fullmatch(name)
            if match and match[1] == document_id.hex:
                os.unlink(name, dir_fd=self.fd)
        os.fsync(self.fd)


@contextmanager
def opened(path, expected=None):
    directory = lock = None
    try:
        directory = open_root(path)
        # Initialization creates this file; never create files in an unprovisioned root.
        lock = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        checked(lock)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        marker = json.loads(read_file(directory, MARKER, 256))
        if (
            not isinstance(marker, dict)
            or set(marker) != {"schema_version", "root_id"}
            or not isinstance(marker["root_id"], str)
            or type(marker["schema_version"]) is not int
            or marker["schema_version"] != 1
        ):
            raise ArchiveError("Unsupported archive marker")
        root_id = UUID(marker["root_id"])
        if str(root_id) != marker["root_id"] or (expected is not None and root_id != expected):
            raise ArchiveError("Archive root identity mismatch")
        archive = Archive(directory, root_id)
        archive.entries()
        yield archive
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ArchiveError("Archive unavailable") from exc
    finally:
        if lock is not None:
            os.close(lock)
        if directory is not None:
            os.close(directory)


def initialize(path):
    """Explicit local operator action only; refuses any existing directory content."""
    directory = lock = None
    try:
        directory = open_root(path)
        with os.scandir(directory) as entries:
            if next(entries, None) is not None:
                raise ArchiveError("Initialization requires an empty private directory")
        lock = os.open(
            LOCK, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root_id = uuid4()
        fd = os.open(
            MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        try:
            write_all(fd, json.dumps({"schema_version": 1, "root_id": str(root_id)}).encode())
        finally:
            os.close(fd)
        os.fsync(directory)
        return root_id
    except OSError as exc:
        raise ArchiveError("Archive initialization unavailable") from exc
    finally:
        if lock is not None:
            os.close(lock)
        if directory is not None:
            os.close(directory)


def main():
    parser = argparse.ArgumentParser(
        description="Initialize an empty private local document archive"
    )
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        initialize(args.directory)
    except ArchiveError:
        parser.exit(
            1, "Archive not initialized; check the empty private directory and permissions.\n"
        )
    print("Private archive initialized. Configure only an isolated development/test service.")


if __name__ == "__main__":
    main()
