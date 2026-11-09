"""Small offline MIME subset. Original bytes are data; no header is authority."""

import base64
import binascii
import re
from email import policy
from email.errors import MessageDefect, MessageError
from email.parser import BytesParser

from app import documents

MAX_MESSAGE = 262144
SINGLE_HEADERS = (
    "content-type",
    "content-disposition",
    "content-transfer-encoding",
    "mime-version",
    "from",
    "subject",
    "message-id",
)


def decode(value):
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Invalid original email") from None
    if not 1 <= len(raw) <= MAX_MESSAGE or base64.b64encode(raw).decode() != value:
        raise ValueError("Invalid original email")
    return raw


def attachment(raw):
    if not 1 <= len(raw) <= MAX_MESSAGE:
        raise ValueError("Email exceeds parser bounds")
    lines = raw.splitlines()
    if (
        len(lines) > 4096
        or any(len(line) > 1024 for line in lines)
        or sum(line.lower().startswith(b"content-type:") for line in lines) > 4
        or sum(line.startswith(b"--") for line in lines) > 8
    ):
        raise ValueError("Email exceeds parser bounds")
    try:
        root = BytesParser(policy=policy.default.clone(raise_on_defect=True)).parsebytes(raw)
        if (
            root.get_content_type() != "multipart/mixed"
            or not root.is_multipart()
            or root.get("MIME-Version") != "1.0"
            or root.get("Content-Transfer-Encoding", "7bit") != "7bit"
        ):
            raise ValueError("Unsupported email structure")
        if not re.fullmatch(r"[A-Za-z0-9_=.-]{1,70}", root.get_boundary() or ""):
            raise ValueError("Unsupported boundary")
        parts = root.get_payload()
        if not 1 <= len(parts) <= 2:
            raise ValueError("Exactly one attachment required")
        for part in (root, *parts):
            if (
                part.defects
                or len(part.keys()) > 64
                or any(len(part.get_all(h, [])) > 1 for h in SINGLE_HEADERS)
            ):
                raise ValueError("Ambiguous email headers")
            if any(getattr(v, "defects", ()) for _, v in part.items()):
                raise ValueError("Defective email headers")
        found = []
        for part in parts:
            if part.is_multipart():
                raise ValueError("Nested email is unsupported")
            name = part.get_filename()
            if part.get_content_disposition() != "attachment":
                if (
                    name is not None
                    or part.get_content_disposition() not in {None, "inline"}
                    or part.get_content_type() != "text/plain"
                ):
                    raise ValueError("Unsupported email body")
                continue
            if not name or part.get("Content-Transfer-Encoding", "").lower() != "base64":
                raise ValueError("Strict attachment encoding required")
            expected_type = "application/pdf" if name.lower().endswith(".pdf") else "text/plain"
            if part.get_content_type() != expected_type:
                raise ValueError("Attachment type mismatch")
            payload = part.get_payload()
            if not isinstance(payload, str) or not re.fullmatch(r"[A-Za-z0-9+/=\r\n]+", payload):
                raise ValueError("Strict attachment encoding required")
            encoded = payload.replace("\r", "").replace("\n", "")
            file = documents.File(filename=name, original_base64=encoded)
            found.append((file.filename, file.original_base64))
        if len(found) != 1:
            raise ValueError("Exactly one attachment required")
        return found[0]
    except (ValueError, LookupError, RecursionError, TypeError, MessageDefect, MessageError) as exc:
        raise ValueError("Unsupported or ambiguous email") from exc
