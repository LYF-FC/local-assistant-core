"""No-replace atomic, exclusive and durable manifest publication (spec 074 section 9.1).

The final name appears through a single hard link that fails if the name exists. A replacing
``rename`` is never used and there is no fallback, copy or check-then-write sequence.
"""

import errno
import heapq
import os
import secrets
import stat
from dataclasses import dataclass, field

from app.recovery_set.format import CodedError

TEMP_PREFIX = ".recovery-set-tmp-"
STALE_SCAN_LIMIT = 64
_UNSUPPORTED = {
    errno.EPERM,
    errno.ENOTSUP,
    errno.EOPNOTSUPP,
    errno.EINVAL,
    errno.EXDEV,
    errno.ENOSYS,
}


@dataclass
class InjectedFaults:
    """Test-only injection point: a function parameter, never reachable from the CLI,
    environment or configuration. Each callback runs at a named point and may raise or kill."""

    points: dict = field(default_factory=dict)

    def fire(self, name):
        callback = self.points.get(name)
        if callback is not None:
            callback()


def _fire(faults, name):
    if faults is not None:
        faults.fire(name)


def stale_temporary_note(directory_path):
    """Informational only: does the first 64 sorted names include the tool's temp prefix?"""
    try:
        with os.scandir(directory_path) as entries:
            first = heapq.nsmallest(
                STALE_SCAN_LIMIT, (os.fsencode(entry.name) for entry in entries)
            )
    except OSError:
        return []
    prefix = TEMP_PREFIX.encode()
    return ["stale_temporary_present"] if any(name.startswith(prefix) for name in first) else []


def _write_all(descriptor, data, faults):
    view, half, fired = memoryview(data), max(1, len(data) // 2), False
    while view:
        chunk = view[:half] if not fired else view
        written = os.write(descriptor, chunk)
        if written <= 0:
            raise OSError(errno.EIO, "short write")
        view = view[written:]
        if not fired:
            fired = True
            _fire(faults, "mid_write")


def publish_manifest(output_path, data, faults=None):
    """Returns ``published_durable`` or ``published_durability_uncertain``; raises CodedError
    with ``publication: not_published`` semantics for every failure before publication."""
    directory_path, name = os.path.split(os.path.abspath(output_path))
    try:
        parent = os.open(directory_path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as error:
        raise CodedError("output_unsafe") from error
    temporary = None
    try:
        if os.fstat(parent).st_mode & 0o022:
            raise CodedError("output_unsafe")
        try:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            info = None
        if info is not None:
            raise CodedError(
                "output_exists"
                if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                else "output_unsafe"
            )
        temporary = f"{TEMP_PREFIX}{secrets.token_hex(16)}"
        try:
            _fire(faults, "before_temp_create")
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=parent,
            )
        except OSError as error:
            temporary = None
            raise CodedError("io_error") from error
        try:
            _write_all(descriptor, data, faults)
            _fire(faults, "before_flush")
            os.fsync(descriptor)
        except OSError as error:
            raise CodedError("io_error") from error
        finally:
            os.close(descriptor)
        _fire(faults, "after_flush")
        try:
            _fire(faults, "before_publish")
            os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        except FileExistsError as error:
            raise CodedError("output_exists") from error
        except OSError as error:
            if error.errno in _UNSUPPORTED:
                raise CodedError("filesystem_unsupported") from error
            raise CodedError("io_error") from error
    except BaseException as error:
        if temporary is not None and isinstance(error, CodedError):
            _remove(parent, temporary)
        raise
    # Published: from here the final name may exist. Nothing below deletes or renames it.
    try:
        _fire(faults, "after_link")
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        os.close(parent)
        return "published_durability_uncertain"
    _remove(parent, temporary)
    try:
        _fire(faults, "after_publish")
        _flush_directory(parent, faults)
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        os.close(parent)
        return "published_durability_uncertain"
    os.close(parent)
    return "published_durable"


def _remove(parent, temporary):
    try:
        os.unlink(temporary, dir_fd=parent)
    except OSError:
        pass  # a remaining temporary is a documented recoverable artifact (G3)


def _flush_directory(parent, faults):
    for attempt in range(3):
        try:
            _fire(faults, "before_dir_fsync")
            os.fsync(parent)
            return
        except InterruptedError:
            if attempt == 2:
                raise
