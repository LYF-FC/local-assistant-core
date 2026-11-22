"""Opt-in durable *synthetic* filing destination for the local MVP-01 rehearsal (spec 076).

This is not a filing adapter and not a filesystem or NAS integration. It records one metadata
entry per filing (filing key, canonical logical path, original SHA-256 and byte size) in a private,
explicitly marked ledger directory so that the effect survives the worker process, its database
transaction and a container restart. The original invoice bytes are never copied.

Durability model, with its limits:

* Each entry is written to a temporary file, fsynced and published with ``os.link``. The link is
  the arbiter: it fails if the path entry already exists, so the operating system, not process
  memory, enforces "never overwrite" across concurrent workers. The parent directory is fsynced.
* ``lookup`` answers by filing key from the ledger alone, so a worker restarted after an effect
  and before its outcome was recorded finds the effect and does not repeat it.
* The ledger lives on a Docker named volume of the local rehearsal. A host reboot or container
  restart preserves it; deleting the volume (the explicit rehearsal reset) removes it. It is not a
  backup, not replicated and not evidence about any real destination.

Guards: development/test environment only, an absolute directory that is not a symbolic link and
carries the exact synthetic marker. The marker is written only by the explicit ``init`` command into
an empty directory. Controls for owner-visible failure scenarios are plain files in ``control/``
and only exist inside a marked ledger.
"""

import argparse
import hashlib
import json
import os
import stat
import sys
import threading
from pathlib import Path

from app import filing
from app.config import settings

MARKER = ".butler-synthetic-filing-ledger-v1"
MARKER_TEXT = "butler synthetic filing ledger v1; metadata only; not a real destination\n"
SCHEMA = 1
MAX_ENTRIES = 5000
CONTROLS = {
    "lookup-unavailable": "persistent",  # every lookup is inconclusive until cleared
    "timeout-after-effect": "once",  # next put applies the effect, then reports a timeout
    "timeout-before-effect": "once",  # next put reports a timeout without any effect
}


class LedgerError(RuntimeError):
    """Fixed, non-sensitive refusal; never carries a path, key or file content."""


def no_hook(point):
    return None


def directory(configured=None):
    root = configured if configured is not None else settings.filing_synthetic_ledger_directory
    if root is None:
        raise LedgerError("A synthetic filing ledger directory is required")
    return Path(root)


def guard_environment():
    if settings.env not in {"development", "test"}:
        raise LedgerError("The synthetic filing ledger exists only in development or test")


def verify(root):
    """Return the validated ledger directory or raise a fixed refusal."""
    guard_environment()
    root = Path(root)
    if not root.is_absolute():
        raise LedgerError("The synthetic filing ledger must be an absolute directory")
    try:
        info = root.lstat()
    except OSError as error:
        raise LedgerError("The synthetic filing ledger is unavailable") from error
    if not stat.S_ISDIR(info.st_mode):
        raise LedgerError("The synthetic filing ledger must be a directory, not a link")
    marker = root / MARKER
    try:
        marker_info = marker.lstat()
        valid = stat.S_ISREG(marker_info.st_mode) and marker.read_text() == MARKER_TEXT
    except OSError:
        valid = False
    if not valid:
        raise LedgerError("The directory is not a marked synthetic filing ledger")
    return root


def initialize(root):
    """Mark an empty directory as the synthetic ledger; idempotent only for an already marked one."""
    guard_environment()
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise LedgerError("An existing absolute directory is required")
    entries = {item.name for item in root.iterdir()}
    marker = root / MARKER
    if MARKER in entries:
        verify(root)
    elif entries:
        raise LedgerError("Only an empty directory can become a synthetic filing ledger")
    else:
        write_private(marker, MARKER_TEXT.encode())
    for name in ("objects", "tmp", "control"):
        (root / name).mkdir(mode=0o700, exist_ok=True)
    sync_directory(root)
    return root


def write_private(path, payload):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class DurableSyntheticDestination(filing.SyntheticDestination):
    """Keyed, never-overwriting synthetic destination whose entries survive restarts."""

    def __init__(self, root=None, hook=no_hook):
        super().__init__()
        self.root = verify(directory(root))
        self.hook = hook

    # ------------------------------------------------------------------ ledger primitives
    def append(self, name, line):
        fd = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (line + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)

    def lines(self, name):
        path = self.root / name
        return path.read_text().splitlines() if path.exists() else []

    @staticmethod
    def name(path):
        return hashlib.sha256(path.encode()).hexdigest()[:40]

    def entry(self, name):
        try:
            value = json.loads((self.root / "objects" / name).read_text())
        except FileNotFoundError:
            return None
        if (
            not isinstance(value, dict)
            or value.get("schema") != SCHEMA
            or set(value) != {"schema", "key", "path", "sha256", "size"}
        ):
            raise LedgerError("A ledger entry is unreadable")
        return value

    def entries(self):
        names = sorted(item.name for item in (self.root / "objects").iterdir())
        if len(names) > MAX_ENTRIES:
            raise LedgerError("The synthetic ledger exceeds its bounded size")
        return [self.entry(name) for name in names]

    def publish(self, name, payload):
        """Create the entry exclusively and durably; False means it already exists."""
        tmp = self.root / "tmp" / f"{os.getpid()}-{threading.get_ident()}-{name}"
        write_private(tmp, json.dumps(payload, sort_keys=True).encode())
        try:
            os.link(tmp, self.root / "objects" / name)
        except FileExistsError:
            return False
        finally:
            tmp.unlink()
        sync_directory(self.root / "objects")
        return True

    # ------------------------------------------------------------------ controls
    def control(self, name):
        return (self.root / "control" / name).exists()

    def consume(self, name):
        """Take a one-shot control exactly once, even with competing workers."""
        try:
            (self.root / "control" / name).unlink()
        except FileNotFoundError:
            return False
        return True

    # ------------------------------------------------------------------ destination contract
    def put(self, key, path, sha256, size):
        path = filing.canonical_path(path)
        name = self.name(path)
        self.append("calls.log", key)
        owner = self.entry(name)
        if owner is not None:
            return filing.Outcome.ACCEPTED if owner["key"] == key else filing.Outcome.COLLISION
        if self.consume("timeout-before-effect"):
            return filing.Outcome.TIMEOUT
        self.hook("before_effect")
        payload = {"schema": SCHEMA, "key": key, "path": path, "sha256": sha256, "size": size}
        if self.publish(name, payload):
            self.append("effects.log", key)
            self.hook("after_effect")
            if self.consume("timeout-after-effect"):
                return filing.Outcome.TIMEOUT
            return filing.Outcome.ACCEPTED
        owner = self.entry(name)
        return filing.Outcome.ACCEPTED if owner["key"] == key else filing.Outcome.COLLISION

    def lookup(self, key):
        self.append("lookups.log", key)
        if self.control("lookup-unavailable"):
            return filing.Lookup.UNAVAILABLE
        found = any(item["key"] == key for item in self.entries())
        return filing.Lookup.FILED if found else filing.Lookup.ABSENT

    # ------------------------------------------------------------------ owner-visible evidence
    def summary(self):
        """Counts and metadata only; keys are shortened and no original content ever exists here."""
        items = self.entries()
        return {
            "entries": len(items),
            "effects": len(self.lines("effects.log")),
            "calls": len(self.lines("calls.log")),
            "lookups": len(self.lines("lookups.log")),
            "controls": sorted(item.name for item in (self.root / "control").iterdir()),
            "items": [
                {
                    "key": item["key"][:12],
                    "path": item["path"],
                    "sha256": item["sha256"],
                    "size": item["size"],
                }
                for item in items
            ],
        }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Synthetic filing ledger of the local rehearsal; metadata only, no real destination"
    )
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    sub.add_parser("status")
    control = sub.add_parser("control")
    control.add_argument("name", choices=sorted(CONTROLS))
    control.add_argument("state", choices=["on", "off"])
    args = parser.parse_args(argv)
    try:
        if args.action == "init":
            initialize(directory())
            print("Synthetic filing ledger ready")
        elif args.action == "status":
            print(json.dumps(DurableSyntheticDestination().summary(), sort_keys=True))
        else:
            root = verify(directory())
            target = root / "control" / args.name
            if args.state == "on":
                target.write_text("1")
            else:
                target.unlink(missing_ok=True)
            print(f"Control {args.name} {args.state}")
    except LedgerError as error:
        print(f"Refused: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
