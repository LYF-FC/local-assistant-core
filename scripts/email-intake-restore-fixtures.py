"""Synthetic offline-mail fidelity/tombstones for the fixed isolated PG restore harness."""

import hashlib
import sys
from email import policy
from email.message import EmailMessage
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, update

from app import documents, email_intake, email_mime, identity
from app.config import settings
from app.db import SessionLocal
from app.models import DocumentRecord, DocumentVersion, EmailEnvelope, User

assert settings.env == "test" and settings.postgres_db in {"butler_test", "butler_test_restore"}
assert (
    settings.postgres_user == "postgres"
)  # Fixed native/restore harness; not a portable Compose fixture.
phase = sys.argv[1]
assert phase in {"seed", "check"}
content = b"Issuer: Synthetic Restore Mail\nInvoice number: E-058\nTotal: 19.00\nCurrency: EUR"
with SessionLocal.begin() as db:
    owner = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
    assert owner
    for name in ("active", "forgotten"):
        identifier = uuid5(NAMESPACE_URL, "butler-synthetic-email-restore-" + name)
        mail = EmailMessage(policy=policy.SMTP)
        mail["From"] = "synthetic@example.invalid"
        mail["Subject"] = "Synthetic restore " + name
        mail.set_content("Synthetic original envelope")
        mail.add_attachment(content, maintype="text", subtype="plain", filename="synthetic.txt")
        mail.set_boundary("synthetic-restore-email-058")
        raw = mail.as_bytes()
        if phase == "seed":
            now = identity.now_utc()
            doc = DocumentRecord(
                id=identifier,
                owner_id=owner.id,
                scope_key="household_shared",
                state="active",
                revision=1,
                title="Synthetic email restore",
                filename="synthetic.txt",
                source_reference="Offline email attachment",
                content_text=content.decode(),
                sha256=hashlib.sha256(content).hexdigest(),
                byte_size=len(content),
                reviewed=False,
                created_at=now,
                updated_at=now,
            )
            db.add(doc)
            db.flush()
            documents.snapshot(db, owner, doc, "uploaded", content)
            db.flush()
            assert email_mime.attachment(raw)[0] == "synthetic.txt"
            envelope = EmailEnvelope(
                document_id=identifier,
                owner_id=owner.id,
                scope_key=doc.scope_key,
                state="active",
                message_sha256=hashlib.sha256(raw).hexdigest(),
                message_size=len(raw),
                attachment_sha256=doc.sha256,
                attachment_filename=doc.filename,
                original_message=raw,
                created_at=now,
            )
            db.add(envelope)
            db.flush()
            if name == "forgotten":
                doc.state = "forgotten"
                doc.revision = 2
                doc.updated_at = identity.now_utc()
                for key in (
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
                    setattr(doc, key, None)
                db.flush()
                email_intake.forget_for_document(db, owner, doc)
                db.execute(
                    update(DocumentVersion)
                    .where(DocumentVersion.document_id == identifier)
                    .values(snapshot=None, original_bytes=None)
                )
                documents.snapshot(db, owner, doc, "forgotten", None)
        else:
            row = db.get(EmailEnvelope, identifier)
            doc = db.get(DocumentRecord, identifier)
            assert (
                row.owner_id == doc.owner_id == owner.id
                and row.message_sha256 == hashlib.sha256(raw).hexdigest()
                and row.message_size == len(raw)
            )
            versions = list(
                db.scalars(
                    select(DocumentVersion)
                    .where(DocumentVersion.document_id == identifier)
                    .order_by(DocumentVersion.revision)
                )
            )
            if name == "active":
                assert (
                    row.original_message == raw
                    and row.attachment_sha256 == doc.sha256
                    and row.attachment_filename == doc.filename
                )
                assert (
                    len(versions) == 1
                    and versions[0].original_bytes == content
                    and row.forgotten_at is None
                )
            else:
                assert (
                    row.state == doc.state == "forgotten"
                    and row.original_message is None
                    and row.attachment_filename is None
                    and row.attachment_sha256 is None
                    and row.forgotten_at is not None
                )
                assert all(v.snapshot is None and v.original_bytes is None for v in versions)
print(
    "Synthetic original-email fidelity/source provenance and replay tombstone/scrubbing recovery verified"
)
