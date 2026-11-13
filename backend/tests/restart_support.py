"""Process-level crash harness: real worker subprocesses and persistent synthetic effect ledgers.

The workers under test (`filing_worker.process`, `notification_worker.process`) run unchanged in
a separate operating-system process. Their only synthetic collaborator, the destination or the
delivery channel, is replaced here by a directory-backed ledger that survives process death. The
parent kills a worker with SIGKILL at a controlled point; a distinct process then recovers from
the same PostgreSQL rows and the same ledger directory.

Coordination is explicit: the child announces the crash point on stdout and blocks reading stdin,
and the parent either kills it (a genuine crash) or writes a release line (a stalled worker that
later resumes). No sleeps are used for synchronisation.

Publishing an object is atomic and exclusive (`os.link` of a fully written temporary file), so
the operating system, not Python state, enforces "never overwrite" across concurrent processes.
"""

import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from app import filing
from app import notifications as notes

BACKEND = Path(__file__).resolve().parents[1]
CHILD = Path(__file__).resolve().with_name("restart_worker.py")
TIMEOUT = 90


class Ledger:
    """Durable effect store and append-only call log shared by every worker process."""

    def __init__(self, root):
        self.root = Path(root)
        for name in ("objects", "tmp"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def log(self, name, line):
        fd = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (line + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)

    def lines(self, name):
        path = self.root / name
        return path.read_text().splitlines() if path.exists() else []

    def publish(self, name, payload):
        """Create the object exclusively; return False if it already exists. Never overwrites."""
        tmp = self.root / "tmp" / f"{os.getpid()}-{threading.get_ident()}-{name}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, json.dumps(payload, sort_keys=True).encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(tmp, self.root / "objects" / name)
            return True
        except FileExistsError:
            return False
        finally:
            tmp.unlink()

    def read(self, name):
        path = self.root / "objects" / name
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return None

    def objects(self):
        return [json.loads(p.read_text()) for p in sorted((self.root / "objects").iterdir())]

    # Test-controlled switch observed by every process: lookups become inconclusive.
    @property
    def lookup_blocked(self):
        return (self.root / "lookup_unavailable").exists()

    def block_lookup(self):
        (self.root / "lookup_unavailable").write_text("1")

    def unblock_lookup(self):
        (self.root / "lookup_unavailable").unlink(missing_ok=True)

    # Evidence readers (never used by the code under test).
    def calls(self):
        return self.lines("calls.log")

    def effects(self):
        return self.lines("effects.log")

    def lookups(self):
        return self.lines("lookups.log")


def no_hook(point):
    return None


class FileDestination(filing.SyntheticDestination):
    """Persistent synthetic filing destination: keyed, never overwrites, answers lookup by key."""

    def __init__(self, root, hook=no_hook):
        super().__init__()
        self.ledger = Ledger(root)
        self.hook = hook

    @staticmethod
    def name(path):
        return hashlib.sha256(path.encode()).hexdigest()[:40]

    def put(self, key, path, sha256, size):
        path = filing.canonical_path(path)
        name = self.name(path)
        self.ledger.log("calls.log", f"{key} {path}")
        owner = self.ledger.read(name)
        if owner is None:
            self.hook("before_effect")
            payload = {"key": key, "path": path, "sha256": sha256, "size": size}
            if self.ledger.publish(name, payload):
                self.ledger.log("effects.log", f"{key} {path}")
                self.hook("after_effect")
                return filing.Outcome.ACCEPTED
            owner = self.ledger.read(name)
        return filing.Outcome.ACCEPTED if owner["key"] == key else filing.Outcome.COLLISION

    def lookup(self, key):
        self.ledger.log("lookups.log", key)
        if self.ledger.lookup_blocked:
            return filing.Lookup.UNAVAILABLE
        found = any(item["key"] == key for item in self.ledger.objects())
        return filing.Lookup.FILED if found else filing.Lookup.ABSENT


class FileChannel(notes.SyntheticChannel):
    """Persistent synthetic delivery channel: idempotent on the delivery key."""

    def __init__(self, root, hook=no_hook):
        super().__init__()
        self.ledger = Ledger(root)
        self.hook = hook

    def send(self, key, recipient):
        self.ledger.log("calls.log", f"{key} {recipient}")
        if self.ledger.read(key) is not None:
            return notes.Outcome.ACCEPTED
        self.hook("before_effect")
        if self.ledger.publish(key, {"key": key, "recipient": recipient}):
            self.ledger.log("effects.log", f"{key} {recipient}")
            self.hook("after_effect")
        return notes.Outcome.ACCEPTED

    def lookup(self, key):
        self.ledger.log("lookups.log", key)
        if self.ledger.lookup_blocked:
            return notes.Lookup.UNAVAILABLE
        return notes.Lookup.DELIVERED if self.ledger.read(key) else notes.Lookup.ABSENT


class Worker:
    """One real worker process handling exactly one filing or notification row."""

    def __init__(self, kind, db_url, ledger, target, crash_at=None):
        self.kind, self.crash_at = kind, crash_at
        self.args = {
            "kind": kind,
            "db_url": db_url,
            "ledger": str(ledger.root),
            "target": str(target),
            "crash_at": crash_at,
        }
        self.proc = None
        self.reached = None
        self.stderr = ""

    def start(self):
        env = dict(os.environ, PYTHONPATH=str(BACKEND), PYTHONUNBUFFERED="1")
        self.proc = subprocess.Popen(
            [sys.executable, str(CHILD), json.dumps(self.args)],
            cwd=BACKEND,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.pid = self.proc.pid
        return self

    def _guard(self):
        timer = threading.Timer(TIMEOUT, self.proc.kill)
        timer.start()
        return timer

    def wait_reached(self):
        """Block until the child reports its crash point (or exits); no polling or sleeping."""
        timer = self._guard()
        seen = []
        try:
            for line in self.proc.stdout:
                if line.startswith("REACHED "):
                    self.reached = line.split()[1]
                    return self.reached
                seen.append(line.strip())
        finally:
            timer.cancel()
        raise AssertionError(
            f"worker exited before its crash point: stdout={seen} {self.collect()}"
        )

    def kill(self):
        """Genuine operating-system termination: SIGKILL, no cleanup handlers, no flush."""
        assert self.proc.poll() is None, "worker already exited"
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait()
        self.stderr = self.proc.stderr.read()
        assert self.proc.returncode == -signal.SIGKILL, self.proc.returncode
        return self.proc.returncode

    def release(self):
        self.proc.stdin.write("go\n")
        self.proc.stdin.flush()

    def finish(self):
        """Wait for normal completion and return the worker's outcome string."""
        timer = self._guard()
        try:
            out, err = self.proc.communicate()
        finally:
            timer.cancel()
        self.stderr = err
        assert self.proc.returncode == 0, f"worker failed ({self.proc.returncode}): {err}"
        results = [
            line.split(maxsplit=1)[1] for line in out.splitlines() if line.startswith("RESULT ")
        ]
        assert len(results) == 1, out + err
        return results[0].strip()

    def collect(self):
        if self.proc.poll() is None:
            self.proc.kill()
        out, err = self.proc.communicate()
        return {"returncode": self.proc.returncode, "stdout": out, "stderr": err}

    def stop(self):
        """Test cleanup: never leave a worker running, even after a failed assertion."""
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.communicate()


def run_to_completion(kind, db_url, ledger, target):
    """Start a fresh worker process with no crash point and wait for its outcome."""
    return Worker(kind, db_url, ledger, target).start().finish()
