"""Synthetic exact-original/history/tombstone sentinel for actual logical restore."""

import hashlib
import sys
from uuid import NAMESPACE_URL, UUID, uuid5

from app import documents, identity
from app.config import settings
from app.db import SessionLocal
from app.models import DocumentRecord, DocumentVersion, User
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

assert settings.env == "test" and settings.postgres_db in {
    "butler_test",
    "butler_test_restore",
}
assert settings.postgres_user == "postgres"
phase = sys.argv[1]
assert phase in {"seed", "check"}
original = b"\xef\xbb\xbfSynthetic restore source\r\nOriginal version\n"
replacement = b"Synthetic replacement original\n"
with SessionLocal.begin() as db:
    owner = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
    assert owner and owner.slug == "synthetic-queue-restore"
    for name in ["active", "forgotten"]:
        identifier = uuid5(NAMESPACE_URL, "butler-synthetic-document-restore-" + name)
        if phase == "seed":
            now = identity.now_utc()
            row = DocumentRecord(
                id=identifier,
                owner_id=owner.id,
                scope_key="household_shared",
                state="active",
                revision=1,
                title="Synthetic restore document",
                filename="synthetic.md",
                source_reference="Synthetic restore reference",
                content_text=original.decode(),
                sha256=hashlib.sha256(original).hexdigest(),
                byte_size=len(original),
                reviewed=False,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            documents.snapshot(db, owner, row, "uploaded", original)
            documents.audit(db, owner, row, "uploaded")
            db.flush()
            row.revision = 2
            row.reviewed = True
            row.updated_at = identity.now_utc()
            db.flush()
            documents.snapshot(db, owner, row, "corrected", original)
            documents.audit(db, owner, row, "corrected", 1)
            db.flush()
            row.revision = 3
            row.reviewed = False
            row.content_text = replacement.decode()
            row.sha256 = hashlib.sha256(replacement).hexdigest()
            row.byte_size = len(replacement)
            row.updated_at = identity.now_utc()
            db.flush()
            documents.snapshot(db, owner, row, "replaced", replacement)
            documents.audit(db, owner, row, "replaced", 2)
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
                ]:
                    setattr(row, key, None)
                db.flush()
                db.execute(
                    update(DocumentVersion)
                    .where(DocumentVersion.document_id == identifier)
                    .values(snapshot=None, original_bytes=None)
                )
                documents.snapshot(db, owner, row, "forgotten", None)
                documents.audit(db, owner, row, "forgotten", 3)
        else:
            row = db.get(DocumentRecord, identifier)
            versions = list(
                db.scalars(
                    select(DocumentVersion)
                    .where(DocumentVersion.document_id == identifier)
                    .order_by(DocumentVersion.revision)
                )
            )
            assert row.owner_id == owner.id and row.scope_key == "household_shared"
            if name == "active":
                assert (
                    row.revision == 3
                    and not row.reviewed
                    and row.content_text == replacement.decode()
                    and row.sha256 == hashlib.sha256(replacement).hexdigest()
                )
                assert [v.operation for v in versions] == [
                    "uploaded",
                    "corrected",
                    "replaced",
                ]
                assert all(
                    v.original_bytes == expected
                    and v.snapshot["sha256"] == hashlib.sha256(expected).hexdigest()
                    for v, expected in zip(
                        versions, [original, original, replacement], strict=True
                    )
                )
                assert (
                    not versions[0].snapshot["reviewed"]
                    and versions[1].snapshot["reviewed"]
                )
            else:
                assert (
                    row.state == "forgotten"
                    and row.revision == 4
                    and row.content_text is None
                    and row.sha256 is None
                    and row.title is None
                )
                assert len(versions) == 4 and all(
                    v.original_bytes is None and v.snapshot is None for v in versions
                )
            for statement in [
                "DELETE FROM document_records WHERE id=:id",
                "DELETE FROM document_versions WHERE document_id=:id",
                "UPDATE document_versions SET snapshot='{}',original_bytes=convert_to('forged','UTF8') WHERE document_id=:id",
            ]:
                try:
                    with db.begin_nested():
                        db.execute(text(statement), {"id": identifier})
                except DBAPIError:
                    pass
                else:
                    raise AssertionError("Restored document seal missing")
print(
    "Synthetic document restore " + phase + " verified; no original payload displayed"
)
