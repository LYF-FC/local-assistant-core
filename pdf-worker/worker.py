"""Serial local PDF extraction. No database, network service, original files or logs."""

import ctypes
import fcntl
import hashlib
import json
import os
import re
import selectors
import signal
import socketserver
import stat
import struct

# Fixed local guard, no shell; bounded pipes and child confinement.
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

GUARD = "/usr/local/bin/pdf-guard"
ROOT = Path("/run/butler-pdf")
MAX_INPUT = 131072
MAX_TEXT = 32000
MAX_OUTPUT = 131072
MAX_RESPONSE = 262144
MAX_PAGES = 12


class BoundedFailure(Exception):
    pass


def command(mode, original=b"", output_limit=MAX_OUTPUT):
    """Bound both streams while feeding stdin; never use unbounded communicate()."""
    # Fixed absolute guard; mode is checked by the guard.
    with subprocess.Popen(  # nosec B603
        [GUARD, mode],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
        start_new_session=True,
        env={},
    ) as child:
        streams = {child.stdout: bytearray(), child.stderr: bytearray()}
        sent = 0
        deadline = time.monotonic() + 8
        with selectors.DefaultSelector() as selector:
            for stream in streams:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            if original:
                os.set_blocking(child.stdin.fileno(), False)
                selector.register(child.stdin, selectors.EVENT_WRITE)
            else:
                child.stdin.close()
            try:
                while selector.get_map():
                    if time.monotonic() >= deadline:
                        raise BoundedFailure("resource_limit")
                    for key, _ in selector.select(min(0.2, max(0, deadline - time.monotonic()))):
                        stream = key.fileobj
                        if stream is child.stdin:
                            try:
                                sent += os.write(stream.fileno(), original[sent : sent + 16384])
                            except BrokenPipeError:
                                sent = len(original)
                            if sent == len(original):
                                selector.unregister(stream)
                                stream.close()
                        else:
                            data = os.read(stream.fileno(), 16384)
                            if not data:
                                selector.unregister(stream)
                                continue
                            streams[stream].extend(data)
                            if len(streams[stream]) > (
                                output_limit if stream is child.stdout else 8192
                            ):
                                raise BoundedFailure("resource_limit")
                child.wait(timeout=max(0.01, deadline - time.monotonic()))
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise
        return (
            child.returncode,
            bytes(streams[child.stdout]),
            bytes(streams[child.stderr]),
        )


def extract(original, version):
    result = {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "engine": "poppler-text-v1",
        "version": version,
        "status": "invalid",
        "pages": 0,
        "page_spans": [],
        "empty_pages": [],
        "text": "",
    }
    if not 1 <= len(original) <= MAX_INPUT or not original.startswith(b"%PDF-"):
        return result
    try:
        code, info, error = command("info", original, 8192)
        if code != 0:
            result["status"] = (
                "encrypted"
                if b"password" in error.lower()
                else "resource_limit"
                if code < 0 or code == 125
                else "invalid"
            )
            return result
        # Reject duplicate/injected metadata headings rather than guessing a count.
        matches = re.findall(rb"^Pages:\s+([0-9]+)\s*$", info, re.MULTILINE)
        if len(matches) != 1:
            return result
        pages = int(matches[0])
        if not 1 <= pages <= MAX_PAGES:
            result["status"] = "resource_limit"
            return result
        if re.search(rb"^Encrypted:\s+yes\b", info, re.MULTILINE):
            result["status"] = "encrypted"
            return result
        code, output, _ = command("text", original)
        if code != 0:
            result["status"] = "resource_limit" if code < 0 or code == 125 else "invalid"
            return result
        text = output.decode("utf-8", errors="strict")
        if "\x00" in text:
            return result
        parts = text.split("\f")
        if parts[-1] == "":
            parts.pop()
        if len(parts) != pages:
            return result
        parts = [part.rstrip("\n") for part in parts]
        combined = "\n".join(parts)
        if len(combined) > MAX_TEXT:
            result["status"] = "resource_limit"
            return result
        result["pages"] = pages
        if not combined.strip():
            result["status"] = "no_text"
            return result
        line = 1
        spans = []
        for page, part in enumerate(parts, 1):
            lines = len(part.split("\n"))
            spans.append({"page": page, "start_line": line, "end_line": line + lines - 1})
            if not part.strip():
                result["empty_pages"].append(page)
            line += lines
        result.update(status="ready", text=combined, page_spans=spans)
        return result
    except (
        BoundedFailure,
        OSError,
        UnicodeError,
        ValueError,
        subprocess.TimeoutExpired,
    ):
        result["status"] = "resource_limit"
        return result


def receive(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise BoundedFailure("invalid_frame")
        data.extend(chunk)
    return bytes(data)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(20)
        try:
            size = struct.unpack("!I", receive(self.request, 4))[0]
            if not 1 <= size <= MAX_INPUT:
                return
            original = receive(self.request, size)
            result = extract(original, self.server.parser_version)
            payload = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
            if len(payload) <= MAX_RESPONSE:
                self.request.sendall(struct.pack("!I", len(payload)) + payload)
        except (OSError, BoundedFailure):
            return


class Server(socketserver.UnixStreamServer):
    def handle_error(self, request, client_address):
        # No tracebacks, document bytes, extracted output or request objects in logs.
        return


def main():
    if os.getuid() != 10001 or stat.S_IMODE(ROOT.stat().st_mode) != 0o700 or ROOT.is_symlink():
        raise SystemExit("Private parser directory/user required")
    if ctypes.CDLL(None).prctl(4, 0, 0, 0, 0) != 0:
        raise SystemExit("Parser parent protection unavailable")
    code, output, _ = command("probe", output_limit=1024)
    if code != 0 or output != b"confined\n":
        raise SystemExit("Parser confinement unavailable")
    code, _, version = command("version", output_limit=1024)
    matches = re.findall(rb"pdftotext version ([0-9.]+)", version)
    if code != 0 or len(matches) != 1:
        raise SystemExit("Parser version unavailable")
    os.umask(0o077)
    lock = os.open(ROOT / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    path = ROOT / "worker.sock"
    if path.exists() or path.is_symlink():
        previous = path.lstat()
        if not stat.S_ISSOCK(previous.st_mode) or previous.st_uid != os.getuid():
            raise SystemExit("Unsafe parser control entry")
        path.unlink()
    with Server(str(path), Handler) as server:
        os.chmod(path, 0o600)
        build = hashlib.sha256(
            Path("/opt/parser-packages.txt").read_bytes()
            + Path(GUARD).read_bytes()
            + Path(__file__).read_bytes()
            + sys.version.encode()
        ).hexdigest()
        server.parser_version = matches[0].decode() + "+" + build
        server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
