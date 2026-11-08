"""Transactional archive obligations and scoped API behavior using synthetic records."""

import base64
from uuid import UUID

from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_documents import ORIGINAL, call, upload

from app import document_archive as storage
from app import document_archiving
from app.config import settings
from app.manage import set_scope
from app.models import AuditEvent, DocumentArchiveBinding, DocumentRecord, User


def archive_call(client, headers, row, copy=False):
    return client.post(
        f"/api/v1/documents/{row['id']}/archive" + ("" if copy else "/status"),
        headers=headers,
        json={"scope": row["scope"], "expected_revision": row["revision"]},
    )


def lifecycle(client, h, root):
    row = upload(client, h).json()
    assert archive_call(client, h, row).json()["state"] == "unarchived"
    status = archive_call(client, h, row, True)
    assert status.status_code == 200, status.text
    assert status.json()["state"] == "verified"
    assert archive_call(client, h, row, True).json()["verified_versions"] == 1
    with storage.opened(root) as archive:
        assert archive.read(UUID(row["id"]), 1) == ORIGINAL
    row = call(client, h, row, "correct").json()
    assert archive_call(client, h, row).json()["state"] == "partial"
    assert archive_call(client, h, row, True).json()["verified_versions"] == 2
    row = call(
        client,
        h,
        row,
        "replace",
        filename="new.md",
        original_base64=base64.b64encode(b"Synthetic new").decode(),
    ).json()
    assert not row["reviewed"]
    assert archive_call(client, h, row).json()["verified_versions"] == 2
    assert archive_call(client, h, row, True).json()["verified_versions"] == 3
    assert call(client, h, row, "forget").status_code == 200
    with storage.opened(root) as archive:
        assert len(archive.entries()) == 2
    return row


def test_complete_managed_lifecycle(auth_client, configured_archive):
    lifecycle(auth_client, signin(auth_client), configured_archive)


def test_disabled_does_not_block_unbound_forgetting(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "document_archive_directory", None)
    h = signin(auth_client)
    row = upload(auth_client, h).json()
    assert archive_call(auth_client, h, row).json()["state"] == "disabled"
    assert archive_call(auth_client, h, row, True).status_code == 503
    assert call(auth_client, h, row, "forget").status_code == 200


def test_binding_survives_failed_copy_and_configuration_removal(
    auth_client, auth_store, configured_archive, monkeypatch
):
    h = signin(auth_client)
    row = upload(auth_client, h).json()
    put = storage.Archive.put

    def fail(*args):
        raise storage.ArchiveError("Synthetic disk outage")

    monkeypatch.setattr(storage.Archive, "put", fail)
    assert archive_call(auth_client, h, row, True).status_code == 503
    with auth_store() as db:
        assert db.get(DocumentArchiveBinding, UUID(row["id"])) is not None
    monkeypatch.setattr(storage.Archive, "put", put)
    assert archive_call(auth_client, h, row, True).status_code == 200
    monkeypatch.setattr(settings, "document_archive_directory", None)
    assert call(auth_client, h, row, "forget").status_code == 503
    with auth_store() as db:
        assert db.get(DocumentRecord, UUID(row["id"])).state == "active"
    monkeypatch.setattr(settings, "document_archive_directory", configured_archive)
    assert call(auth_client, h, row, "forget").status_code == 200


def test_wrong_root_cannot_rebind_or_forget(auth_client, configured_archive, tmp_path, monkeypatch):
    h = signin(auth_client)
    row = upload(auth_client, h).json()
    assert archive_call(auth_client, h, row, True).status_code == 200
    wrong = tmp_path / "wrong"
    wrong.mkdir(mode=0o700)
    storage.initialize(wrong)
    monkeypatch.setattr(settings, "document_archive_directory", wrong)
    for copy in [False, True]:
        assert archive_call(auth_client, h, row, copy).status_code == 503
    assert call(auth_client, h, row, "forget").status_code == 503
    with storage.opened(wrong) as archive:
        assert len(archive.entries()) == 2


def test_binding_audit_failure_never_copies(auth_client, auth_store, configured_archive):
    h = signin(auth_client)
    row = upload(auth_client, h).json()

    def fail(mapper, conn, target):
        if target.event_type == "documents.archive_bound":
            raise SQLAlchemyError("Synthetic audit outage")

    event.listen(AuditEvent, "before_insert", fail)
    try:
        assert archive_call(auth_client, h, row, True).status_code == 503
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    with auth_store() as db:
        assert db.get(DocumentArchiveBinding, UUID(row["id"])) is None
    with storage.opened(configured_archive) as archive:
        assert len(archive.entries()) == 2


def test_archive_audit_failure_leaves_bound_retryable_copies(
    auth_client, auth_store, configured_archive
):
    h = signin(auth_client)
    row = upload(auth_client, h).json()

    def fail(mapper, conn, target):
        if target.event_type == "documents.archive_written":
            raise SQLAlchemyError("Synthetic audit outage")

    event.listen(AuditEvent, "before_insert", fail)
    try:
        assert archive_call(auth_client, h, row, True).status_code == 503
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    with auth_store() as db:
        assert db.get(DocumentArchiveBinding, UUID(row["id"])) is not None
    assert archive_call(auth_client, h, row, True).json()["state"] == "verified"


def test_failed_forget_audit_keeps_originals_repairable(
    auth_client, auth_store, configured_archive
):
    h = signin(auth_client)
    row = upload(auth_client, h).json()
    assert archive_call(auth_client, h, row, True).status_code == 200

    def fail(mapper, conn, target):
        if target.event_type == "documents.forgotten":
            raise SQLAlchemyError("Synthetic audit outage")

    event.listen(AuditEvent, "before_insert", fail)
    try:
        assert call(auth_client, h, row, "forget").status_code == 503
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    assert call(auth_client, h, row, "original").status_code == 200
    assert archive_call(auth_client, h, row).json()["state"] == "partial"
    assert archive_call(auth_client, h, row, True).json()["state"] == "verified"
    assert call(auth_client, h, row, "forget").status_code == 200


def test_shared_viewer_scope_revocation_and_csrf_never_touch_archive(
    auth_client, auth_store, configured_archive, monkeypatch
):
    h = signin(auth_client)
    row = upload(auth_client, h).json()
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "bob")), "household_shared", True)
    other = signin(auth_client, "bob")
    for copy in [False, True]:
        assert archive_call(auth_client, other, row, copy).status_code == 403
    assert archive_call(auth_client, {}, row).status_code == 403
    h = signin(auth_client)
    stale = dict(row, revision=2)
    assert archive_call(auth_client, h, stale, True).status_code == 409
    # A committed binding is not authority after grant revocation.
    assert archive_call(auth_client, h, row, True).status_code == 200
    with auth_store.begin() as db:
        set_scope(
            db, db.scalar(select(User).where(User.slug == "alice")), "household_shared", False
        )
    for copy in [False, True]:
        assert archive_call(auth_client, h, row, copy).status_code == 403


def test_reauthorization_between_committed_binding_and_content(
    auth_client, configured_archive, monkeypatch
):
    h = signin(auth_client)
    row = upload(auth_client, h).json()
    from app import documents, identity

    real = documents.operate

    def stop(db, token, csrf, identifier, body, op):
        if op == "archive_write":
            return identity.denied(db, 401, "documents.session_denied")
        return real(db, token, csrf, identifier, body, op)

    monkeypatch.setattr(documents, "operate", stop)
    assert archive_call(auth_client, h, row, True).status_code == 401
    with storage.opened(configured_archive) as archive:
        assert len(archive.entries()) == 2


def test_purge_failure_preserves_record_for_retry(auth_client, configured_archive, monkeypatch):
    h = signin(auth_client)
    row = upload(auth_client, h).json()
    assert archive_call(auth_client, h, row, True).status_code == 200
    real = document_archiving.purge

    def fail(*args):
        raise storage.ArchiveError("Synthetic unlink failure")

    monkeypatch.setattr(document_archiving, "purge", fail)
    assert call(auth_client, h, row, "forget").status_code == 503
    assert call(auth_client, h, row, "read").json()["state"] == "active"
    monkeypatch.setattr(document_archiving, "purge", real)
    assert call(auth_client, h, row, "forget").status_code == 200
