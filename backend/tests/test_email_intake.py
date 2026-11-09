import base64
import hashlib
from email import policy
from email.message import EmailMessage
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_documents import call as document_call
from test_invoice_filing import approved
from test_invoice_review import TEXT, confirm

from app import email_intake, email_mime
from app.manage import set_scope
from app.models import AuditEvent, DocumentRecord, EmailEnvelope, InvoiceReview, User


def message(
    content=None,
    filename="synthetic-invoice.txt",
    *,
    subject="Synthetic offline invoice",
    copies=1,
):
    if content is None:
        content = TEXT.encode()
    mail = EmailMessage(policy=policy.SMTP)
    mail["From"] = "sender@example.invalid"
    mail["To"] = "recipient@example.invalid"
    mail["Subject"] = subject
    mail["Message-ID"] = "<synthetic-058@example.invalid>"
    mail.set_content("Synthetic forwarded original. Untrusted instructions are inert.")
    for _ in range(copies):
        mail.add_attachment(
            content,
            maintype="application" if filename.endswith(".pdf") else "text",
            subtype="pdf" if filename.endswith(".pdf") else "plain",
            filename=filename,
        )
    mail.set_boundary("synthetic-boundary-058")
    return mail.as_bytes()


def ingest(client, h, raw=None, scope="household_shared", title="Synthetic email invoice"):
    return client.post(
        "/api/v1/email-intake",
        headers=h,
        json={
            "scope": scope,
            "title": title,
            "message_base64": base64.b64encode(raw if raw is not None else message()).decode(),
        },
    )


def mail_call(client, h, doc, op="read", **extra):
    return client.post(
        f"/api/v1/email-intake/{doc['id']}/{op}",
        headers=h,
        json={"scope": doc["scope"], "expected_document_revision": doc["revision"], **extra},
    )


def test_raw_and_attachment_fidelity_review_plan_export_and_aggregate_forget(
    auth_client, auth_store
):
    h = signin(auth_client)
    raw = message()
    r = ingest(auth_client, h, raw)
    assert r.status_code == 201, r.json()
    doc = r.json()["document"]
    meta = r.json()["provenance"]
    assert not doc["reviewed"] and doc["source_reference"] == "Offline email attachment"
    assert (
        meta["message_sha256"] == hashlib.sha256(raw).hexdigest() and meta["source_revision"] == 1
    )
    data = mail_call(auth_client, h, doc, "export", acknowledge_copy_limits=True).json()
    assert base64.b64decode(data["original_base64"]) == raw and data["managed_copy"] is False
    assert mail_call(auth_client, h, doc, "export", acknowledge_copy_limits=1).status_code == 422
    doc = document_call(auth_client, h, doc, "correct", reviewed=True).json()
    reviewed = approved(auth_client, h, doc, confirm(auth_client, h, doc))
    replay = ingest(auth_client, h, raw, title="Do not rename on replay")
    assert (
        replay.status_code == 200
        and replay.json()["status"] == "replayed"
        and replay.json()["document"] == doc
    )
    assert replay.json()["provenance"]["current_document_revision"] == doc["revision"]
    assert document_call(auth_client, h, doc, "forget").status_code == 200
    with auth_store() as db:
        row = db.get(EmailEnvelope, UUID(doc["id"]))
        assert (
            row.state == "forgotten"
            and row.original_message is None
            and row.attachment_filename is None
            and row.attachment_sha256 is None
        )
        assert db.get(InvoiceReview, UUID(doc["id"])).data is None
        assert row.message_sha256 == hashlib.sha256(raw).hexdigest()
    assert ingest(auth_client, h, raw).status_code == 410
    assert reviewed["review"]["data"]["filing_plan"]["execution_authorized"] is False


def test_distinct_forward_bytes_and_source_replacement_keep_initial_email(auth_client):
    h = signin(auth_client)
    raw = message()
    doc = ingest(auth_client, h, raw).json()["document"]
    other = ingest(auth_client, h, message(subject="Synthetic other forwarding envelope")).json()[
        "document"
    ]
    assert other["id"] != doc["id"] and other["sha256"] == doc["sha256"]
    doc2 = document_call(
        auth_client,
        h,
        doc,
        "replace",
        filename="changed.txt",
        original_base64=base64.b64encode(b"Synthetic replacement").decode(),
    ).json()
    assert mail_call(auth_client, h, doc).status_code == 409
    data = mail_call(auth_client, h, doc2, "export", acknowledge_copy_limits=True).json()
    assert (
        data["attachment_is_current"] is False and base64.b64decode(data["original_base64"]) == raw
    )
    assert ingest(auth_client, h, raw).json()["document"]["id"] == doc["id"]


@pytest.mark.parametrize(
    "kind",
    [
        "multiple",
        "missing",
        "nested",
        "html",
        "encoding",
        "path",
        "type",
        "duplicate",
        "boundary",
        "line",
        "lines",
        "parts",
        "size",
        "base64",
        "empty",
    ],
)
def test_strict_mime_subset_rejects_ambiguity(kind):
    raw = message()
    if kind == "multiple":
        raw = message(copies=2)
    if kind == "missing":
        raw = b"MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=x\r\n\r\n--x\r\nContent-Type: text/plain\r\n\r\nSynthetic body\r\n--x--\r\n"
    if kind == "nested":
        raw = raw.replace(b"Content-Type: text/plain", b"Content-Type: message/rfc822", 1)
    if kind == "html":
        raw = raw.replace(b"Content-Type: text/plain", b"Content-Type: text/html", 1)
    if kind == "encoding":
        raw = raw.replace(
            b"Content-Transfer-Encoding: base64", b"Content-Transfer-Encoding: quoted-printable"
        )
    if kind == "path":
        raw = message(filename="../synthetic.txt")
    if kind == "type":
        raw = raw.replace(b'filename="synthetic-invoice.txt"', b'filename="synthetic-invoice.pdf"')
    if kind == "duplicate":
        raw = raw.replace(b"MIME-Version: 1.0", b"MIME-Version: 1.0\r\nMIME-Version: 1.0", 1)
    if kind == "boundary":
        raw = raw.replace(b"--synthetic-boundary-058--", b"--wrong--")
    if kind == "line":
        raw += b"x" * 1025
    if kind == "lines":
        raw += b"\r\n" * 4097
    if kind == "parts":
        raw += b"\r\n--fake" * 9
    if kind == "size":
        raw = b"x" * 262145
    if kind == "base64":
        raw = raw.replace(b"SXNzdWVy", b"!XNzdWVy")
    if kind == "empty":
        raw = b""
    with pytest.raises(ValueError):
        email_mime.attachment(raw)


def test_pdf_original_reuses_worker_contract(auth_client):
    h = signin(auth_client)
    r = ingest(auth_client, h, message(b"%PDF-synthetic-unavailable", filename="synthetic.pdf"))
    assert r.status_code == 201
    assert r.json()["document"]["extraction"]["status"] == "unavailable"


def test_owner_only_provenance_scope_dedup_and_admin_private_negatives(auth_client, auth_store):
    h = signin(auth_client)
    with auth_store.begin() as db:
        for slug in ("alice", "bob"):
            u = db.scalar(select(User).where(User.slug == slug))
            set_scope(db, u, "member_b_private", True)
            set_scope(db, u, "household_shared", True)
            if slug == "bob":
                set_scope(db, u, "technical_admin", True)
    shared = ingest(auth_client, h).json()["document"]
    private = ingest(auth_client, h, scope="member_b_private").json()["document"]
    assert shared["id"] != private["id"]
    bh = signin(auth_client, "bob")
    assert mail_call(auth_client, bh, shared).status_code == 403
    assert mail_call(auth_client, bh, private).status_code == 404
    assert ingest(auth_client, bh).json()["document"]["id"] != shared["id"]
    assert ingest(auth_client, {"X-CSRF-Token": "invalid"}).status_code == 403
    h = signin(auth_client)
    with auth_store.begin() as db:
        set_scope(
            db, db.scalar(select(User).where(User.slug == "alice")), "household_shared", False
        )
    assert mail_call(auth_client, h, shared).status_code == 403


def test_quota_unsupported_and_audit_failures_are_atomic(auth_client, auth_store, monkeypatch):
    h = signin(auth_client)
    assert ingest(auth_client, h, b"Unsupported synthetic mail").status_code == 422
    monkeypatch.setattr(email_intake, "MAX_RETAINED", 1)
    assert ingest(auth_client, h).status_code == 409
    monkeypatch.setattr(email_intake, "MAX_RETAINED", 4 * 1024 * 1024)

    def fail(mapper, conn, target):
        if target.event_type == "email_intake.imported":
            raise SQLAlchemyError("Synthetic intake audit failure")

    event.listen(AuditEvent, "before_insert", fail)
    try:
        assert ingest(auth_client, h).status_code == 503
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    with auth_store() as db:
        assert (
            list(db.scalars(select(DocumentRecord))) == []
            and list(db.scalars(select(EmailEnvelope))) == []
        )
    r = ingest(auth_client, h)
    assert r.status_code == 201
    with auth_store() as db:
        logs = list(
            db.scalars(select(AuditEvent).where(AuditEvent.event_type.like("email_intake.%")))
        )
        assert all(
            "example.invalid" not in str(a.metadata_json)
            and "message_sha256" not in str(a.metadata_json)
            for a in logs
        )


@pytest.mark.parametrize(
    "value", ["!AAA", "AAAAA", "AAAA====", base64.b64encode(b"x" * 262145).decode()]
)
def test_noncanonical_or_oversized_message_base64(value):
    with pytest.raises(ValueError):
        email_mime.decode(value)


@pytest.mark.parametrize("content", [b"", b"\xff", b"x" * 32001, b"x" * 131073])
def test_attachment_reuses_original_byte_and_text_bounds(content):
    with pytest.raises(ValueError):
        email_mime.attachment(message(content))


def test_origin_session_and_invalid_upload_do_not_release_email(auth_client):
    h = signin(auth_client)
    doc = ingest(auth_client, h).json()["document"]
    assert (
        mail_call(auth_client, {**h, "Origin": "https://invalid.example"}, doc).status_code == 403
    )
    assert (
        auth_client.post(
            "/api/v1/email-intake",
            headers=h,
            json={
                "scope": "household_shared",
                "title": "Synthetic invalid upload",
                "message_base64": "!AAA",
            },
        ).status_code
        == 422
    )
    auth_client.cookies.clear()
    assert mail_call(auth_client, h, doc, "export", acknowledge_copy_limits=True).status_code == 401
