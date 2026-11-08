"""Synthetic PDF exact original/derivation/history/archive/tombstone restore."""

import hashlib
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend/tests"))
from app import document_archiving, documents, identity
from app.config import settings
from app.db import SessionLocal
from app.models import DocumentRecord, DocumentVersion, User
from pdf_fixtures import pdf

assert settings.env == "test" and settings.postgres_user == "postgres"
assert settings.postgres_db in {"butler_test", "butler_test_restore"}
phase = sys.argv[1]
assert phase in {"seed", "check"}
raw = pdf()
derived = "Synthetic invoice 100.00"
info = {
    "engine": "poppler-text-v1",
    "version": "25.03.0",
    "status": "ready",
    "pages": 1,
    "page_spans": [{"page": 1, "start_line": 1, "end_line": 1}],
    "empty_pages": [],
}
owner_id = UUID("22222222-2222-4222-8222-222222222222")
for name in ["active", "forgotten"]:
    identifier = uuid5(NAMESPACE_URL, "synthetic-pdf-restore-" + name)
    with SessionLocal.begin() as db:
        owner = db.get(User, owner_id)
        if phase == "seed":
            now = identity.now_utc()
            row = DocumentRecord(
                id=identifier,
                owner_id=owner.id,
                scope_key="household_shared",
                state="active",
                revision=1,
                title="Synthetic PDF restore",
                filename="synthetic.pdf",
                source_reference="Synthetic PDF original",
                content_text=derived,
                sha256=hashlib.sha256(raw).hexdigest(),
                byte_size=len(raw),
                reviewed=False,
                extraction_json=info,
                ingest_key=uuid5(NAMESPACE_URL, "synthetic-pdf-request-" + name),
                ingest_hash=hashlib.sha256(name.encode()).hexdigest(),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            documents.snapshot(db, owner, row, "uploaded", raw)
            documents.audit(db, owner, row, "uploaded")
            db.flush()
            row.reviewed = True
            row.revision = 2
            row.updated_at = identity.now_utc()
            db.flush()
            documents.snapshot(db, owner, row, "corrected", raw)
            documents.audit(db, owner, row, "corrected")
            db.flush()
            row.reviewed = False
            row.revision = 3
            row.updated_at = identity.now_utc()
            db.flush()
            documents.snapshot(db, owner, row, "extracted", raw)
            documents.audit(db, owner, row, "extracted")
            db.flush()
            if name == "forgotten":
                row.state = "forgotten"
                row.revision = 4
                row.updated_at = identity.now_utc()
                for key in [
                    "title",
                    "filename",
                    "source_reference",
                    "content_text",
                    "sha256",
                    "byte_size",
                    "reviewed",
                    "extraction_json",
                    "ingest_hash",
                ]:
                    setattr(row, key, None)
                db.flush()
                db.execute(
                    update(DocumentVersion)
                    .where(DocumentVersion.document_id == identifier)
                    .values(snapshot=None, original_bytes=None)
                )
                documents.snapshot(db, owner, row, "forgotten", None)
                documents.audit(db, owner, row, "forgotten")
        else:
            row = db.get(DocumentRecord, identifier)
            versions = list(
                db.scalars(
                    select(DocumentVersion)
                    .where(DocumentVersion.document_id == identifier)
                    .order_by(DocumentVersion.revision)
                )
            )
            if name == "active":
                assert (
                    row.state == "active"
                    and row.revision == 3
                    and not row.reviewed
                    and row.content_text == derived
                    and row.extraction_json == info
                )
                assert [v.operation for v in versions] == [
                    "uploaded",
                    "corrected",
                    "extracted",
                ]
                assert all(
                    v.original_bytes == raw
                    and v.snapshot["text_origin"] == "pdf_text"
                    and v.snapshot["sha256"] == hashlib.sha256(raw).hexdigest()
                    and v.snapshot["text_sha256"]
                    == hashlib.sha256(derived.encode()).hexdigest()
                    and v.snapshot["extraction"] == info
                    for v in versions
                )
                assert (
                    document_archiving.operation(
                        db, owner, row, "archive_status"
                    ).payload["state"]
                    == "verified"
                )
            else:
                assert (
                    row.state == "forgotten"
                    and row.extraction_json is None
                    and row.ingest_hash is None
                    and row.ingest_key is not None
                )
                assert len(versions) == 4 and all(
                    v.snapshot is None and v.original_bytes is None for v in versions
                )
            try:
                with db.begin_nested():
                    db.execute(
                        text(
                            "UPDATE document_records SET revision=revision WHERE id=:id"
                        ),
                        {"id": identifier},
                    )
            except DBAPIError:
                pass
            else:
                raise AssertionError("Restored PDF seal missing")
    if phase == "seed" and name == "active":
        with SessionLocal.begin() as db:
            row = db.get(DocumentRecord, identifier)
            owner = db.get(User, owner_id)
            document_archiving.operation(db, owner, row, "archive_bind")
        with SessionLocal.begin() as db:
            row = db.scalar(
                select(DocumentRecord)
                .where(DocumentRecord.id == identifier)
                .with_for_update()
            )
            owner = db.get(User, owner_id)
            assert (
                document_archiving.operation(db, owner, row, "archive_write").payload[
                    "state"
                ]
                == "verified"
            )
print(
    "Synthetic PDF original/derivation/history/archive/forget restore "
    + phase
    + " verified; no payloads displayed"
)
