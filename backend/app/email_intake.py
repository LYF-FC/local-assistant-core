"""Atomic offline intake with private original-email provenance; no mailbox integration."""

import base64
import hashlib
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator
from sqlalchemy import func, select

from app import documents, email_mime, identity
from app.manual_tasks import Scoped, authority, stamp
from app.models import DocumentRecord, EmailEnvelope

MAX_RETAINED = 4 * 1024 * 1024


class Import(Scoped):
    title: str = Field(min_length=1, max_length=160)
    _safe_title = field_validator("title")(documents.Metadata.nonblank.__func__)
    message_base64: str = Field(min_length=4, max_length=349528)


class Read(Scoped):
    expected_document_revision: int = Field(strict=True, ge=1)


class Export(Read):
    acknowledge_copy_limits: Literal[True]
    _explicit = field_validator("acknowledge_copy_limits", mode="before")(
        documents.Original.explicit.__func__
    )


def audit(db, user, source, operation):
    identity.audit(
        db,
        "email_intake." + operation,
        "success",
        user=user,
        scope=source.scope_key,
        entity_type="document",
        entity=str(source.id),
        metadata={"document_revision": source.revision},
    )


def receipt(source, row):
    return {
        "schema_version": 1,
        "document_id": str(source.id),
        "scope": source.scope_key,
        "current_document_revision": source.revision,
        "state": row.state,
        "source_revision": 1,
        "message_sha256": row.message_sha256,
        "message_size": row.message_size,
        "attachment_sha256": row.attachment_sha256,
        "attachment_filename": row.attachment_filename,
        "attachment_is_current": source.state == "active"
        and source.sha256 == row.attachment_sha256,
        "created_at": stamp(row.created_at),
        "forgotten_at": stamp(row.forgotten_at) if row.forgotten_at else None,
        "notice": "Original offline email only, not authenticated sender identity. Replacement does not rewrite intake provenance. No mailbox or filing effect.",
    }


def ingest(db, token, csrf, body):
    current = authority(
        db, token, csrf, body.scope, exclusive_user=True, event_prefix="email_intake"
    )
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    try:
        raw = email_mime.decode(body.message_base64)
    except ValueError:
        return identity.denied(db, 422, "email_intake.invalid_message", user=user)
    checksum = hashlib.sha256(raw).hexdigest()
    previous = db.scalar(
        select(EmailEnvelope).where(
            EmailEnvelope.owner_id == user.id,
            EmailEnvelope.scope_key == body.scope,
            EmailEnvelope.message_sha256 == checksum,
        )
    )
    if previous:
        source = db.scalar(
            select(DocumentRecord)
            .where(DocumentRecord.id == previous.document_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if identity.resolve(db, token, refresh_session=True) is None:
            return identity.denied(db, 401, "email_intake.session_denied", user=user)
        audit(db, user, source, "replayed")
        if previous.state == "forgotten":
            return identity.Result(
                410, {"schema_version": 1, "status": "forgotten", "document_id": str(source.id)}
            )
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "status": "replayed",
                "document": documents.presented(source, user),
                "provenance": receipt(source, previous),
            },
        )
    used = db.scalar(
        select(func.coalesce(func.sum(func.length(EmailEnvelope.original_message)), 0)).where(
            EmailEnvelope.owner_id == user.id
        )
    )
    if used + len(raw) > MAX_RETAINED:
        return identity.denied(db, 409, "email_intake.quota", user=user)
    try:
        name, encoded = email_mime.attachment(raw)
        upload = documents.Upload(
            scope=body.scope,
            title=body.title,
            source_reference="Offline email attachment",
            filename=name,
            original_base64=encoded,
            ingest_key=uuid4(),
        )
    except ValueError:
        return identity.denied(db, 422, "email_intake.unsupported_message", user=user)
    created = documents.create(db, token, csrf, upload)
    if created.status != 201:
        return created
    source = db.get(DocumentRecord, UUID(created.payload["id"]))
    row = EmailEnvelope(
        document_id=source.id,
        owner_id=user.id,
        scope_key=body.scope,
        state="active",
        message_sha256=checksum,
        message_size=len(raw),
        attachment_sha256=source.sha256,
        attachment_filename=name,
        original_message=raw,
        created_at=source.created_at,
    )
    db.add(row)
    db.flush()
    audit(db, user, source, "imported")
    return identity.Result(
        201,
        {
            "schema_version": 1,
            "status": "imported",
            "document": created.payload,
            "provenance": receipt(source, row),
        },
    )


def operate(db, token, csrf, identifier, body, export=False):
    current = authority(db, token, csrf, body.scope, event_prefix="email_intake")
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    source = db.scalar(
        select(DocumentRecord)
        .where(DocumentRecord.id == identifier, *documents.visible(user, body.scope))
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "email_intake.session_denied", user=user)
    if source is None:
        return identity.denied(db, 404, "email_intake.not_found", user=user)
    if source.owner_id != user.id:
        return identity.denied(db, 403, "email_intake.owner_denied", user=user)
    row = db.scalar(
        select(EmailEnvelope)
        .where(EmailEnvelope.document_id == source.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if row is None:
        return identity.denied(db, 404, "email_intake.not_found", user=user)
    if source.state == "forgotten" or row.state == "forgotten":
        return identity.denied(db, 410, "email_intake.forgotten", user=user)
    if source.revision != body.expected_document_revision:
        return identity.denied(db, 409, "email_intake.source_changed", user=user)
    result = receipt(source, row)
    if export:
        result.update(
            managed_copy=False, original_base64=base64.b64encode(row.original_message).decode()
        )
    audit(db, user, source, "exported" if export else "read")
    return identity.Result(200, result)


def forget_for_document(db, user, source):
    row = db.scalar(
        select(EmailEnvelope)
        .where(EmailEnvelope.document_id == source.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or row.state == "forgotten":
        return
    row.state = "forgotten"
    row.original_message = None
    row.attachment_filename = None
    row.attachment_sha256 = None
    row.forgotten_at = identity.now_utc()
    db.flush()
    audit(db, user, source, "forgotten")
