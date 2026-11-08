"""Strict local parser IPC and provenance validation. No native parsing in the API."""

import hashlib
import json
import os
import re
import socket
import stat
import struct
import sys

from app.config import settings
from app.document_archive import ArchiveError, open_root

STATES = {"ready", "no_text", "encrypted", "invalid", "resource_limit", "unavailable"}
MAX_ORIGINAL = 131072
MAX_RESPONSE = 262144


def unavailable(*, ocr=False):
    return {
        "engine": "poppler-tesseract-v1" if ocr else "poppler-text-v1",
        "version": "unavailable",
        "status": "unavailable",
        "pages": 0,
        "page_spans": [],
        "empty_pages": [],
    }, ""


def receive(stream, size):
    output = bytearray()
    while len(output) < size:
        chunk = stream.recv(size - len(output))
        if not chunk:
            raise ValueError("Incomplete parser response")
        output.extend(chunk)
    return bytes(output)


def exchange(original, *, ocr=False):
    if sys.platform != "linux" or settings.pdf_socket_directory is None:
        return None
    directory = None
    try:
        directory = open_root(settings.pdf_socket_directory)
        info = os.stat("worker.sock", dir_fd=directory, follow_symlinks=False)
        if (
            not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            return None
        # Descriptor-relative directory resolution avoids following a replaced parent path.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(20)
            stream.connect(f"/proc/self/fd/{directory}/worker.sock")
            payload = (b"OCR1" if ocr else b"") + original
            stream.sendall(struct.pack("!I", len(payload)) + payload)
            size = struct.unpack("!I", receive(stream, 4))[0]
            if not 1 <= size <= MAX_RESPONSE:
                return None
            return json.loads(receive(stream, size))
    except (ArchiveError, OSError, ValueError, TypeError):
        return None
    finally:
        if directory is not None:
            os.close(directory)


def validated(result, original, *, ocr=False):
    keys = {
        "schema_version",
        "source_sha256",
        "engine",
        "version",
        "status",
        "pages",
        "page_spans",
        "empty_pages",
        "text",
    }
    if (
        not isinstance(result, dict)
        or set(result) != keys
        or type(result["schema_version"]) is not int
        or result["schema_version"] != 1
    ):
        return unavailable(ocr=ocr)
    if (
        result["source_sha256"] != hashlib.sha256(original).hexdigest()
        or result["engine"] != ("poppler-tesseract-v1" if ocr else "poppler-text-v1")
        or not isinstance(result["version"], str)
        or not re.fullmatch(r"[0-9.]{1,15}(?:\+[a-f0-9]{64})?", result["version"])
    ):
        return unavailable(ocr=ocr)
    status, pages, text = result["status"], result["pages"], result["text"]
    if (
        not isinstance(status, str)
        or status not in STATES - {"unavailable"}
        or type(pages) is not int
        or not 0 <= pages <= (2 if ocr else 12)
        or not isinstance(text, str)
        or len(text) > 32000
        or "\x00" in text
        or any(0xD800 <= ord(c) <= 0xDFFF for c in text)
    ):
        return unavailable(ocr=ocr)
    spans, empty = result["page_spans"], result["empty_pages"]
    if (
        not isinstance(spans, list)
        or not isinstance(empty, list)
        or len(spans) > 12
        or len(empty) > 12
    ):
        return unavailable(ocr=ocr)
    if status != "ready":
        if (
            text
            or spans
            or empty
            or (status == "no_text" and not pages)
            or (status not in {"no_text"} and pages)
        ):
            return unavailable(ocr=ocr)
    else:
        if not text.strip() or not pages or len(spans) != pages:
            return unavailable(ocr=ocr)
        expected = 1
        for page, span in enumerate(spans, 1):
            if (
                not isinstance(span, dict)
                or set(span) != {"page", "start_line", "end_line"}
                or any(type(v) is not int for v in span.values())
                or span["page"] != page
                or span["start_line"] != expected
                or span["end_line"] < expected
            ):
                return unavailable(ocr=ocr)
            expected = span["end_line"] + 1
        if (
            expected != len(text.split("\n")) + 1
            or any(type(v) is not int or not 1 <= v <= pages for v in empty)
            or sorted(set(empty)) != empty
        ):
            return unavailable(ocr=ocr)
    return {
        key: result[key]
        for key in ("engine", "version", "status", "pages", "page_spans", "empty_pages")
    }, text


def extract(original, *, ocr=False):
    if (
        not isinstance(original, bytes)
        or not 1 <= len(original) <= MAX_ORIGINAL
        or not original.startswith(b"%PDF-")
    ):
        raise ValueError("A bounded PDF original is required")
    result = exchange(original, ocr=True) if ocr else exchange(original)
    return unavailable(ocr=ocr) if result is None else validated(result, original, ocr=ocr)
