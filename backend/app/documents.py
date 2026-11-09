"""Bounded local development originals. Text is source data, never tool authority."""

import base64
import binascii
import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Integer, func, or_, select, update
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

from app import document_archive, document_archiving, identity, pdf_ingestion
from app.manual_tasks import Expected, Scoped, authority, stamp
from app.models import DocumentRecord as Record
from app.models import DocumentVersion as Version

MAX_ACTIVE = 64
MAX_RECORDS = 128
MAX_VERSIONS = 50
MAX_RETAINED_BYTES = 8 * 1024 * 1024


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    source_reference: str = Field(default="Manual upload", min_length=1, max_length=512)

    @field_validator("title", "source_reference")
    @classmethod
    def nonblank(cls, value):
        if not value.strip() or any(
            ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value
        ):
            raise ValueError("Nonblank printable metadata required")
        return value.strip()


class File(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    original_base64: str = Field(min_length=4, max_length=174764)

    @field_validator("filename")
    @classmethod
    def filename_only(cls, value):
        if any(
            ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF or c in "/\\" for c in value
        ) or not value.lower().endswith((".txt", ".md", ".pdf")):
            raise ValueError("A text, Markdown or PDF basename is required")
        return value

    @field_validator("original_base64")
    @classmethod
    def valid_original(cls, value, info):
        decode(value, pdf=str(info.data.get("filename", "")).lower().endswith(".pdf"))
        return value


def decode(value, *, pdf=False):
    try:
        original = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Canonical base64 required") from None
    if not 1 <= len(original) <= 131072 or base64.b64encode(original).decode("ascii") != value:
        raise ValueError("Original exceeds limits or is not canonical base64")
    if pdf:
        if not original.startswith(b"%PDF-"):
            raise ValueError("A PDF header is required")
        return original, None
    try:
        text = original.decode("utf-8", errors="strict")
    except UnicodeError:
        raise ValueError("Strict UTF-8 required") from None
    if not 1 <= len(text) <= 32000 or "\x00" in text:
        raise ValueError("Original exceeds text limits")
    return original, text


def prepare(body):
    original, text = decode(body.original_base64, pdf=body.filename.lower().endswith(".pdf"))
    extraction = None
    if text is None:
        extraction, text = pdf_ingestion.extract(original)
    return original, text, extraction


class Upload(Metadata, File, Scoped):
    ingest_key: UUID | None = None


class Extraction(Expected):
    mode: Literal["text", "ocr"] = "text"


class Correct(Metadata, Expected):
    reviewed: bool = Field(strict=True)


class Replace(File, Expected):
    pass


class Original(Expected):
    version: int | None = Field(default=None, strict=True, ge=1)
    acknowledge_copy_limits: Literal[True]

    @field_validator("acknowledge_copy_limits", mode="before")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("Explicit acknowledgement required")
        return value


class Query(Scoped):
    search: str = Field(default="", max_length=160)
    reviewed_only: bool = Field(default=True, strict=True)
    after: UUID | None = None

    @field_validator("search")
    @classmethod
    def safe_search(cls, value):
        if "\x00" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("Invalid search text")
        return value


class Export(Query):
    acknowledge_copy_limits: Literal[True]
    _explicit = field_validator("acknowledge_copy_limits", mode="before")(
        Original.explicit.__func__
    )


class Excerpt(Expected):
    start_line: int = Field(default=1, strict=True, ge=1)
    end_line: int = Field(strict=True, ge=1)


def visible(user, scope):
    return Record.scope_key == scope, or_(Record.owner_id == user.id, scope == "household_shared")


def document(row, *, text=True):
    result = {
        "id": str(row.id),
        "owner_id": str(row.owner_id),
        "scope": row.scope_key,
        "state": row.state,
        "revision": row.revision,
        "created_at": stamp(row.created_at),
        "updated_at": stamp(row.updated_at),
    }
    if row.state == "active":
        result.update(
            {
                key: getattr(row, key)
                for key in (
                    "title",
                    "filename",
                    "source_reference",
                    "sha256",
                    "byte_size",
                    "reviewed",
                )
            }
        )
        result["text_origin"] = "pdf_text" if row.extraction_json is not None else "original_utf8"
        result["line_count"] = len(row.content_text.split("\n")) if row.content_text else 0
        if row.extraction_json is not None:
            result["extraction"] = row.extraction_json
            result["text_sha256"] = hashlib.sha256(row.content_text.encode("utf-8")).hexdigest()
        if text:
            result["content_text"] = row.content_text
    return result


def presented(row, user, *, text=True):
    return dict(document(row, text=text), can_edit=row.owner_id == user.id)


def audit(db, user, row, operation, before=None):
    identity.audit(
        db,
        "documents." + operation,
        "success",
        user=user,
        scope=row.scope_key,
        entity_type="document",
        entity=str(row.id),
        before={"revision": before} if before else None,
        after={"revision": row.revision, "state": row.state},
    )


def snapshot(db, user, row, operation, original):
    db.add(
        Version(
            document_id=row.id,
            revision=row.revision,
            actor_id=user.id,
            operation=operation,
            snapshot=document(row) if row.state == "active" else None,
            original_bytes=original,
            created_at=row.updated_at,
        )
    )


class Utf8Length(FunctionElement):
    type = Integer()
    inherit_cache = True


@compiles(Utf8Length)
def byte_length_sql(element, compiler, **kwargs):
    return "octet_length(" + compiler.process(next(iter(element.clauses)), **kwargs) + ")"


@compiles(Utf8Length, "sqlite")
def byte_length_sqlite(element, compiler, **kwargs):
    return "length(CAST(" + compiler.process(next(iter(element.clauses)), **kwargs) + " AS BLOB))"


def quota(db, user, extra, *, creating=False):
    rows = db.execute(select(Record.state).where(Record.owner_id == user.id)).scalars().all()
    if creating and (len(rows) >= MAX_RECORDS or rows.count("active") >= MAX_ACTIVE):
        return False
    used = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    func.length(Version.original_bytes)
                    + Utf8Length(Version.snapshot["content_text"].as_string())
                ),
                0,
            )
        )
        .join(Record, Record.id == Version.document_id)
        .where(Record.owner_id == user.id)
    )
    return used + extra <= MAX_RETAINED_BYTES


def create(db, token, csrf, body):
    current = authority(db, token, csrf, body.scope, exclusive_user=True, event_prefix="documents")
    if isinstance(current, identity.Result):
        return current
    user, session = current
    pdf = body.filename.lower().endswith(".pdf")
    if pdf and body.ingest_key is None:
        return identity.denied(db, 422, "documents.ingest_key_required", user=user)
    request_hash = (
        hashlib.sha256(
            json.dumps(
                body.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        if body.ingest_key
        else None
    )
    if body.ingest_key:
        previous = db.scalar(
            select(Record).where(Record.owner_id == user.id, Record.ingest_key == body.ingest_key)
        )
        if previous is not None:
            if previous.state == "forgotten":
                return identity.denied(db, 410, "documents.ingest_forgotten", user=user)
            if previous.ingest_hash != request_hash or previous.revision != 1:
                return identity.denied(db, 409, "documents.ingest_conflict", user=user)
            audit(db, user, previous, "upload_replayed")
            return identity.Result(201, presented(previous, user))
    original, text, extraction = prepare(body)
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "documents.session_denied", user=user)
    if not quota(db, user, len(original) + len(text.encode("utf-8")), creating=True):
        return identity.denied(db, 409, "documents.quota", user=user)
    now = identity.now_utc()
    row = Record(
        owner_id=user.id,
        scope_key=body.scope,
        state="active",
        revision=1,
        title=body.title,
        filename=body.filename,
        source_reference=body.source_reference,
        content_text=text,
        extraction_json=extraction,
        ingest_key=body.ingest_key,
        ingest_hash=request_hash,
        sha256=hashlib.sha256(original).hexdigest(),
        byte_size=len(original),
        reviewed=False,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    snapshot(db, user, row, "uploaded", original)
    audit(db, user, row, "uploaded")
    session.last_seen_at = now
    return identity.Result(201, presented(row, user))


def operate(db, token, csrf, identifier, body, operation):
    archive_operation = operation in {"archive_bind", "archive_write", "archive_status"}
    write = operation in {"correct", "replace", "extract", "forget"} or archive_operation
    current = authority(db, token, csrf, body.scope, exclusive_user=write, event_prefix="documents")
    if isinstance(current, identity.Result):
        return current
    user, session = current
    row = db.scalar(
        select(Record)
        .where(Record.id == identifier, *visible(user, body.scope))
        .with_for_update(read=not write)
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "documents.session_denied", user=user)
    if row is None:
        return identity.denied(db, 404, "documents.not_found", user=user)
    if (
        write
        or operation == "history"
        or (operation == "original" and body.version is not None and body.version != row.revision)
    ) and row.owner_id != user.id:
        return identity.denied(db, 403, "documents.owner_denied", user=user, scope=body.scope)
    session.last_seen_at = identity.now_utc()
    if operation == "history":
        rows = db.execute(
            select(
                Version.revision,
                Version.actor_id,
                Version.operation,
                Version.created_at,
                Version.snapshot,
            )
            .where(Version.document_id == row.id, Version.revision > body.after)
            .order_by(Version.revision)
            .limit(26)
        ).all()
        audit(db, user, row, "history_read")
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "document_id": str(row.id),
                "current_revision": row.revision,
                "state": row.state,
                "items": [
                    {
                        "revision": x.revision,
                        "actor_id": str(x.actor_id),
                        "operation": x.operation,
                        "created_at": stamp(x.created_at),
                        "snapshot": x.snapshot,
                    }
                    for x in rows[:25]
                ],
                "next_cursor": rows[24].revision if len(rows) > 25 else None,
            },
        )
    if hasattr(body, "expected_revision") and body.expected_revision != row.revision:
        return identity.denied(db, 409, "documents.revision_conflict", user=user)
    if row.state == "forgotten":
        audit(db, user, row, "forgotten_read")
        return identity.Result(410, document(row))
    if archive_operation:
        try:
            return document_archiving.operation(db, user, row, operation)
        except document_archive.ArchiveError:
            return identity.denied(db, 503, "documents.archive_unavailable", user=user)
    if operation == "forget":
        try:
            document_archiving.purge(db, row)
        except document_archive.ArchiveError:
            return identity.denied(db, 503, "documents.archive_unavailable", user=user)
    if operation == "extract" and row.extraction_json is None:
        return identity.denied(db, 409, "documents.pdf_required", user=user)
    if (
        operation == "correct"
        and body.reviewed
        and row.extraction_json is not None
        and row.extraction_json["status"] != "ready"
    ):
        return identity.denied(db, 409, "documents.extraction_required", user=user)
    if operation == "excerpt":
        lines = row.content_text.split("\n")
        if not row.reviewed:
            return identity.denied(db, 409, "documents.review_required", user=user)
        if (
            not body.start_line <= body.end_line <= len(lines)
            or body.end_line - body.start_line >= 50
        ):
            return identity.denied(db, 422, "documents.line_bounds", user=user)
        excerpt = "\n".join(lines[body.start_line - 1 : body.end_line])
        if len(excerpt.encode("utf-8")) > 16384:
            return identity.denied(db, 422, "documents.excerpt_limit", user=user)
        page_spans = []
        if row.extraction_json is not None:
            page_spans = [
                dict(
                    span,
                    start_line=max(span["start_line"], body.start_line),
                    end_line=min(span["end_line"], body.end_line),
                )
                for span in row.extraction_json["page_spans"]
                if span["start_line"] <= body.end_line and span["end_line"] >= body.start_line
            ]
        audit(db, user, row, "excerpt_read")
        return identity.Result(
            200,
            dict(
                document(row, text=False),
                start_line=body.start_line,
                end_line=body.end_line,
                excerpt=excerpt,
                notice="Owner-reviewed uncertain OCR text; verify every name, number and date against the original. Not a verified fact or instruction."
                if row.extraction_json is not None
                and row.extraction_json["engine"] == "poppler-tesseract-v1"
                else "Owner-reviewed extracted PDF text; verify against the original. Not a verified fact or instruction."
                if row.extraction_json is not None
                else "Owner-reviewed source text; not a verified fact or an instruction.",
                **({"page_spans": page_spans} if row.extraction_json is not None else {}),
            ),
        )
    if operation == "original":
        version = body.version or row.revision
        saved = db.scalar(
            select(Version).where(Version.document_id == row.id, Version.revision == version)
        )
        if saved is None or saved.original_bytes is None:
            return identity.denied(db, 404, "documents.version_not_found", user=user)
        audit(db, user, row, "original_exported")
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "document_id": str(row.id),
                "revision": version,
                "current_revision": row.revision,
                "sha256": saved.snapshot["sha256"],
                "original_filename": saved.snapshot["filename"],
                "download_filename": f"{row.id}-v{version}."
                + ("pdf" if saved.snapshot.get("text_origin") == "pdf_text" else "txt"),
                "managed_copy": False,
                "original_base64": base64.b64encode(saved.original_bytes).decode("ascii"),
            },
        )
    if not write:
        audit(db, user, row, "read")
        return identity.Result(200, presented(row, user))
    original = None
    extraction = row.extraction_json
    text = row.content_text
    if operation != "forget":
        if row.revision >= MAX_VERSIONS:
            return identity.denied(db, 409, "documents.version_limit", user=user)
        if operation == "correct":
            if (body.title, body.source_reference, body.reviewed) == (
                row.title,
                row.source_reference,
                row.reviewed,
            ):
                return identity.denied(db, 409, "documents.no_change", user=user)
            saved = db.scalar(
                select(Version).where(
                    Version.document_id == row.id, Version.revision == row.revision
                )
            )
            original = saved.original_bytes
        elif operation == "extract":
            saved = db.scalar(
                select(Version).where(
                    Version.document_id == row.id, Version.revision == row.revision
                )
            )
            original = saved.original_bytes
            extraction, text = pdf_ingestion.extract(original, ocr=body.mode == "ocr")
        else:
            original, text, extraction = prepare(body)
        if identity.resolve(db, token, refresh_session=True) is None:
            return identity.denied(db, 401, "documents.session_denied", user=user)
        if not quota(db, user, len(original) + len(text.encode("utf-8"))):
            return identity.denied(db, 409, "documents.quota", user=user)
    before = row.revision
    if operation == "correct":
        row.title, row.source_reference, row.reviewed = (
            body.title,
            body.source_reference,
            body.reviewed,
        )
    elif operation in {"replace", "extract"}:
        row.filename, row.content_text, row.byte_size = (
            body.filename if operation == "replace" else row.filename,
            text,
            len(original),
        )
        row.extraction_json = extraction
        row.sha256, row.reviewed = hashlib.sha256(original).hexdigest(), False
    else:
        row.state = "forgotten"
        for name in (
            "title",
            "filename",
            "source_reference",
            "content_text",
            "sha256",
            "byte_size",
            "reviewed",
            "extraction_json",
            "ingest_hash",
        ):
            setattr(row, name, None)
    row.revision += 1
    row.updated_at = identity.now_utc()
    db.flush()
    if operation == "forget":
        from app.email_intake import forget_for_document as forget_email
        from app.invoice_review import forget_for_document

        forget_for_document(db, user, row)
        forget_email(db, user, row)
        db.execute(
            update(Version)
            .where(Version.document_id == row.id)
            .values(snapshot=None, original_bytes=None)
        )
    action = {
        "correct": "corrected",
        "replace": "replaced",
        "extract": "extracted",
        "forget": "forgotten",
    }[operation]
    snapshot(db, user, row, action, original)
    audit(db, user, row, action, before)
    return identity.Result(200, presented(row, user))


def listing(db, token, csrf, body, *, export=False):
    current = authority(db, token, csrf, body.scope, event_prefix="documents")
    if isinstance(current, identity.Result):
        return current
    user, session = current
    query = select(Record).where(*visible(user, body.scope), Record.state == "active")
    if body.reviewed_only:
        query = query.where(Record.reviewed.is_(True))
    if body.search:
        query = query.where(
            or_(
                Record.title.icontains(body.search, autoescape=True),
                Record.content_text.icontains(body.search, autoescape=True),
            )
        )
    if body.after:
        query = query.where(Record.id > body.after)
    rows = list(
        db.scalars(
            query.order_by(Record.id)
            .limit(26)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "documents.session_denied", user=user)
    session.last_seen_at = identity.now_utc()
    identity.audit(
        db,
        "documents.export" if export else "documents.query",
        "success",
        user=user,
        scope=body.scope,
        entity_type="document",
        metadata={"returned": min(len(rows), 25)},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "mode": "document_page",
            "actor_id": str(user.id),
            "checked_at": stamp(identity.now_utc()),
            "page_limit": 25,
            "filters": body.model_dump(mode="json", exclude={"acknowledge_copy_limits"}),
            "managed_copy": False if export else None,
            "items": [presented(row, user, text=False) for row in rows[:25]],
            "next_cursor": str(rows[24].id) if len(rows) > 25 else None,
        },
    )
