"""Archive lifecycle under current document authority and row lock."""

import hashlib

from sqlalchemy import select

from app import document_archive, identity
from app.config import settings
from app.models import DocumentArchiveBinding, DocumentVersion


def root(binding=None):
    if settings.env not in {"development", "test"} or settings.document_archive_directory is None:
        raise document_archive.ArchiveError("Correct archive configuration required")
    return document_archive.opened(
        settings.document_archive_directory, binding.root_id if binding else None
    )


def purge(db, row):
    binding = db.get(DocumentArchiveBinding, row.id)
    if binding:
        with root(binding) as archive:
            archive.purge(row.id)


def operation(db, user, row, operation):
    from app.documents import audit

    binding = db.get(DocumentArchiveBinding, row.id)
    if operation == "archive_bind":
        with root(binding) as archive:
            if binding is None:
                db.add(
                    DocumentArchiveBinding(
                        document_id=row.id, root_id=archive.root_id, created_at=identity.now_utc()
                    )
                )
                db.flush()
        audit(db, user, row, "archive_bound")
        return identity.Result(200, {"prepared": True})
    versions = list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == row.id)
            .order_by(DocumentVersion.revision)
            .limit(51)
        )
    )
    if (
        len(versions) != row.revision
        or len(versions) > 50
        or any(v.revision != i for i, v in enumerate(versions, 1))
    ):
        raise document_archive.ArchiveError("Incomplete authoritative versions")
    result = {
        "schema_version": 1,
        "document_id": str(row.id),
        "revision": row.revision,
        "state": "unarchived",
        "versions": len(versions),
        "verified_versions": 0,
        "verified_bytes": 0,
        "checked_at": identity.now_utc().isoformat(),
    }
    if binding is None:
        if settings.document_archive_directory is None:
            result["state"] = "disabled"
        elif operation == "archive_write":
            raise document_archive.ArchiveError("Committed binding required")
    else:
        with root(binding) as archive:
            archive.discard_pending(row.id)
            for version in versions:
                data = version.original_bytes
                if (
                    data is None
                    or version.snapshot is None
                    or hashlib.sha256(data).hexdigest() != version.snapshot["sha256"]
                    or len(data) != version.snapshot["byte_size"]
                ):
                    raise document_archive.ArchiveError("Original provenance mismatch")
                if operation == "archive_write":
                    archive.put(row.id, version.revision, data)
                try:
                    actual = archive.read(row.id, version.revision)
                except FileNotFoundError:
                    continue
                if actual != data:
                    raise document_archive.ArchiveError("Archive integrity mismatch")
                result["verified_versions"] += 1
                result["verified_bytes"] += len(actual)
        result["state"] = "verified" if result["verified_versions"] == len(versions) else "partial"
    audit(db, user, row, "archive_written" if operation == "archive_write" else "archive_checked")
    return identity.Result(200, result)
