"""Bounded deterministic labeled invoice candidates; no model or file/network parser."""

import hashlib
import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FIELDS = ("issuer", "invoice_number", "issued_on", "due_on", "total", "currency")
LIMITS = {
    "issuer": 160,
    "invoice_number": 96,
    "issued_on": 10,
    "due_on": 10,
    "total": 16,
    "currency": 3,
}
CURRENCIES = {"EUR", "USD", "GBP", "CHF", "CAD"}
LABELS = {
    "issuer": (
        "issuer",
        "supplier",
        "vendor",
        "fournisseur",
        "émetteur",
        "emetteur",
        "proveedor",
        "emisor",
    ),
    "invoice_number": (
        "invoice number",
        "invoice no",
        "n° facture",
        "numéro facture",
        "facture n°",
        "número de factura",
        "numero de factura",
    ),
    "issued_on": ("invoice date", "date de facture", "fecha de factura"),
    "due_on": ("due date", "échéance", "echeance", "fecha de vencimiento"),
    "total": ("total", "total ttc", "montant ttc", "importe total"),
    "currency": ("currency", "devise", "moneda"),
}
BY_LABEL = {label: field for field, labels in LABELS.items() for label in labels}


def normalize(field, value):
    value = value.strip()
    if (
        not value
        or len(value) > LIMITS[field]
        or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise ValueError("Unsupported field value")
    if field in {"issued_on", "due_on"}:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("ISO date required")
    elif field == "total":
        if not re.fullmatch(r"-?(?:0|[1-9][0-9]{0,8})[.,][0-9]{2}", value):
            raise ValueError("Explicit decimal amount required")
        value = format(Decimal(value.replace(",", ".")), ".2f")
        if Decimal(value) == 0:
            value = "0.00"
    elif field == "currency":
        value = value.upper()
        if value not in CURRENCIES:
            raise ValueError("Unsupported currency")
    return value


def evidence(source, line):
    lines = source.content_text.split("\n")
    if not 1 <= line <= len(lines):
        raise ValueError("Invalid evidence line")
    quote = lines[line - 1]
    if len(quote) > 256 or len(quote.encode()) > 1024:
        raise ValueError("Evidence line too large")
    spans = source.extraction_json["page_spans"] if source.extraction_json else []
    return {
        "line": line,
        "quote": quote,
        "pages": [s["page"] for s in spans if s["start_line"] <= line <= s["end_line"]],
    }


def prepare(source):
    lines = source.content_text.split("\n")
    candidates = {field: [] for field in FIELDS}
    truncated = len(lines) > 1000
    for number, line in enumerate(lines[:1000], 1):
        if len(line) > 256 or len(line.encode()) > 1024:
            truncated = True
            continue
        label, separator, raw = line.lstrip("\ufeff").partition(":")
        if not separator:
            label, separator, raw = line.partition("=")
        field = BY_LABEL.get(label.strip().casefold())
        if not separator or not field:
            continue
        if len(candidates[field]) >= 3:
            truncated = True
            continue
        raw = raw.strip()
        try:
            value, issue = normalize(field, raw), None
        except ValueError:
            value, issue = None, "unsupported_format"
        candidates[field].append(
            {"raw": raw, "value": value, "issue": issue, "evidence": evidence(source, number)}
        )
    return {
        "extractor": "invoice-labels-v1",
        "source": {
            "revision": source.revision,
            "sha256": source.sha256,
            "text_sha256": hashlib.sha256(source.content_text.encode()).hexdigest(),
            "ocr_uncertain": bool(
                source.extraction_json
                and source.extraction_json["engine"] == "poppler-tesseract-v1"
            ),
        },
        "candidates": candidates,
        "truncated": truncated,
        "decisions": None,
    }


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["confirmed", "unknown"]
    value: str | None = Field(default=None, max_length=160)
    line: int | None = Field(default=None, strict=True, ge=1)
    note: str = Field(default="", max_length=160)

    @field_validator("value", "note")
    @classmethod
    def safe_text(cls, value):
        if value is not None and any(
            ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value
        ):
            raise ValueError("Printable field text required")
        return value


class Decisions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuer: Decision
    invoice_number: Decision
    issued_on: Decision
    due_on: Decision
    total: Decision
    currency: Decision


def review(source, decisions):
    result = {}
    for field in FIELDS:
        item = getattr(decisions, field)
        if item.state == "unknown":
            if item.value is not None or item.line is not None:
                raise ValueError("Unknown fields cannot claim values/evidence")
            result[field] = {"state": "unknown", "value": None, "note": item.note, "evidence": None}
            continue
        if item.value is None:
            raise ValueError("Confirmed value required")
        value = normalize(field, item.value)
        if item.line is None and not item.note.strip():
            raise ValueError("Manual original-check note required")
        result[field] = {
            "state": "confirmed",
            "value": value,
            "note": item.note,
            "evidence": evidence(source, item.line) if item.line else None,
        }
    issue, due = result["issued_on"]["value"], result["due_on"]["value"]
    if issue and due and due < issue:
        raise ValueError("Due date precedes invoice date")
    return result


def key(value):
    return " ".join(value.casefold().split()) if value else None
