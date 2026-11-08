"""Synthetic SQL plus separately copied file-archive restore; no payload output."""

import sys
from uuid import NAMESPACE_URL, uuid5

from app import document_archive, document_archiving, documents
from app.config import settings
from app.db import SessionLocal
from app.models import DocumentArchiveBinding, DocumentRecord, User
from sqlalchemy import select

assert settings.env == "test" and settings.postgres_user == "postgres"
assert settings.postgres_db in {"butler_test", "butler_test_restore"}
assert settings.document_archive_directory is not None
phase = sys.argv[1]
assert phase in {"seed", "check"}
identifier = uuid5(NAMESPACE_URL, "butler-synthetic-document-restore-active")
if phase == "seed":
    # No original copy before this binding and its audit commit.
    with SessionLocal.begin() as db:
        row = db.get(DocumentRecord, identifier)
        owner = db.get(User, row.owner_id)
        assert row.state == "active" and row.revision == 3
        with document_archiving.root() as archive:
            db.add(
                DocumentArchiveBinding(
                    document_id=row.id,
                    root_id=archive.root_id,
                    created_at=row.updated_at,
                )
            )
        documents.audit(db, owner, row, "archive_bound")
    with SessionLocal.begin() as db:
        row = db.scalar(
            select(DocumentRecord)
            .where(DocumentRecord.id == identifier)
            .with_for_update()
        )
        owner = db.get(User, row.owner_id)
        assert (
            document_archiving.operation(db, owner, row, "archive_write").payload[
                "state"
            ]
            == "verified"
        )
else:
    with SessionLocal.begin() as db:
        row = db.scalar(
            select(DocumentRecord)
            .where(DocumentRecord.id == identifier)
            .with_for_update()
        )
        owner = db.get(User, row.owner_id)
        binding = db.get(DocumentArchiveBinding, row.id)
        assert binding is not None
        result = document_archiving.operation(db, owner, row, "archive_status").payload
        assert result["state"] == "verified" and result["verified_versions"] == 3
        with document_archive.opened(
            settings.document_archive_directory, binding.root_id
        ) as archive:
            expected = [
                b"\xef\xbb\xbfSynthetic restore source\r\nOriginal version\n"
            ] * 2 + [b"Synthetic replacement original\n"]
            assert [archive.read(row.id, i) for i in range(1, 4)] == expected
    # An unrelated root cannot replace the identity restored from SQL.
    try:
        with document_archive.opened(
            settings.document_archive_directory,
            uuid5(NAMESPACE_URL, "synthetic-wrong-root"),
        ):
            raise AssertionError("Wrong root was accepted")
    except document_archive.ArchiveError:
        pass
print("Synthetic document archive " + phase + " verified; original bytes not displayed")
