"""Logical invoice filing proposals only. No filesystem, executor or network access."""

import re
import unicodedata

POLICY = "invoice-filing-v1"
RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def slug(value, limit):
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    result = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:limit].rstrip("-")
    if not result or result in RESERVED:
        raise ValueError("Manual logical destination required")
    return result


def extension(source):
    return "pdf" if source.filename.lower().endswith(".pdf") else "txt"


def validate(folder, filename, suffix):
    parts = folder.split("/")
    if not 2 <= len(parts) <= 3 or parts[0] != "invoices":
        raise ValueError("Invalid logical folder")
    if any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", p) or p in RESERVED for p in parts):
        raise ValueError("Invalid logical folder")
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,159}", filename)
        or ".." in filename
        or not filename.endswith("." + suffix)
        or filename.split(".")[0] in RESERVED
        or len(folder + "/" + filename) > 384
    ):
        raise ValueError("Invalid logical filename")
    return folder + "/" + filename


def propose(source, row, folder=None, filename=None):
    if (folder is None) != (filename is None):
        raise ValueError("Provide folder and filename together")
    manual = folder is not None
    if not manual:
        choices = row.data["decisions"]
        if any(
            choices[f]["state"] != "confirmed" for f in ("issuer", "invoice_number", "issued_on")
        ):
            raise ValueError("Manual logical destination required")
        issuer = slug(choices["issuer"]["value"], 48)
        number = slug(choices["invoice_number"]["value"], 32)
        date = choices["issued_on"]["value"]
        folder = f"invoices/{date[:4]}/{issuer}"
        filename = f"{date}_{issuer}_{number}_{source.id}.{extension(source)}"
    path = validate(folder, filename, extension(source))
    return {
        "schema_version": 1,
        "policy": POLICY,
        "state": "proposed",
        "source_revision": source.revision,
        "source_sha256": source.sha256,
        "based_on_review_revision": row.revision,
        "manual": manual,
        "folder": folder,
        "filename": filename,
        "relative_path": path,
        "execution_authorized": False,
        "approved_revision": None,
    }
