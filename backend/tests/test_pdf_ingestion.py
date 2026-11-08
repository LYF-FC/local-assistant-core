import base64
import hashlib
from uuid import UUID, uuid4

import pytest
from pdf_fixtures import pdf
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_documents import call, upload

from app import documents, identity, pdf_ingestion
from app.models import AuditEvent, DocumentRecord, DocumentVersion


def result(original, *, text="Synthetic page one\nSynthetic page two", status="ready"):
    ready = status == "ready"
    return {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "engine": "poppler-text-v1",
        "version": "25.03.0",
        "status": status,
        "pages": 2 if ready else 1 if status == "no_text" else 0,
        "page_spans": [
            {"page": 1, "start_line": 1, "end_line": 1},
            {"page": 2, "start_line": 2, "end_line": 2},
        ]
        if ready
        else [],
        "empty_pages": [],
        "text": text if ready else "",
    }


def pdf_upload(client, h, original=None, **changes):
    data = pdf() if original is None else original
    return upload(
        client,
        h,
        filename="synthetic.pdf",
        original_base64=base64.b64encode(data).decode(),
        ingest_key=str(uuid4()),
        **changes,
    )


def extract_call(client, h, row):
    return client.post(
        f"/api/v1/documents/{row['id']}/extract",
        headers=h,
        json={"scope": row["scope"], "expected_revision": row["revision"]},
    )


def pdf_lifecycle(client, h):
    raw = pdf(("Synthetic first", "Synthetic second"))
    row = pdf_upload(client, h, raw).json()
    assert (
        row["text_origin"] == "pdf_text"
        and row["extraction"]["status"] == "ready"
        and not row["reviewed"]
    )
    assert row["sha256"] == hashlib.sha256(raw).hexdigest()
    assert row["text_sha256"] == hashlib.sha256(row["content_text"].encode()).hexdigest()
    assert call(client, h, row, "excerpt", end_line=1).status_code == 409
    row = call(client, h, row, "correct").json()
    excerpt = call(client, h, row, "excerpt", start_line=2, end_line=2).json()
    assert excerpt["page_spans"] == [{"page": 2, "start_line": 2, "end_line": 2}]
    original = call(client, h, row, "original").json()
    assert (
        original["download_filename"].endswith(".pdf")
        and base64.b64decode(original["original_base64"]) == raw
    )
    row = extract_call(client, h, row).json()
    assert row["revision"] == 3 and not row["reviewed"]
    assert call(client, h, row, "history").json()["items"][-1]["operation"] == "extracted"
    assert call(client, h, row, "forget").status_code == 200
    return row


def test_pdf_lifecycle(auth_client, monkeypatch):
    monkeypatch.setattr(pdf_ingestion, "exchange", result)
    pdf_lifecycle(auth_client, signin(auth_client))


@pytest.mark.parametrize("status", ["no_text", "encrypted", "invalid", "resource_limit"])
def test_failed_extraction_retains_original_and_refuses_review(auth_client, monkeypatch, status):
    monkeypatch.setattr(pdf_ingestion, "exchange", lambda raw: result(raw, status=status))
    h = signin(auth_client)
    raw = pdf()
    response = pdf_upload(auth_client, h, raw)
    assert response.status_code == 201, response.text
    row = response.json()
    assert (
        row["extraction"]["status"] == status
        and row["line_count"] == 0
        and row["content_text"] == ""
    )
    assert call(auth_client, h, row, "correct").status_code == 409
    assert call(auth_client, h, row, "original").status_code == 200
    monkeypatch.setattr(pdf_ingestion, "exchange", result)
    retried = extract_call(auth_client, h, row)
    assert retried.status_code == 200 and retried.json()["extraction"]["status"] == "ready"
    assert not retried.json()["reviewed"]


def test_unconfigured_worker_stores_retryable_original(auth_client, monkeypatch):
    monkeypatch.setattr(pdf_ingestion, "exchange", lambda raw: None)
    h = signin(auth_client)
    row = pdf_upload(auth_client, h).json()
    assert row["extraction"]["status"] == "unavailable"
    assert call(auth_client, h, row, "original").status_code == 200


def test_upload_key_is_owner_payload_bound_and_terminal(auth_client, auth_store, monkeypatch):
    calls = []

    def parse(raw):
        calls.append(raw)
        return result(raw)

    monkeypatch.setattr(pdf_ingestion, "exchange", parse)
    h = signin(auth_client)
    key = str(uuid4())
    raw = pdf()

    def send(**changes):
        return upload(
            auth_client,
            h,
            filename="synthetic.pdf",
            original_base64=base64.b64encode(raw).decode(),
            ingest_key=key,
            **changes,
        )

    first = send()
    second = send()
    assert (
        first.status_code == second.status_code == 201
        and first.json()["id"] == second.json()["id"]
        and len(calls) == 1
    )
    assert send(title="Different request").status_code == 409
    row = first.json()
    assert call(auth_client, h, row, "forget").status_code == 200
    assert send().status_code == 410
    with auth_store() as db:
        saved = db.get(DocumentRecord, UUID(row["id"]))
        assert (
            saved.ingest_hash is None
            and saved.extraction_json is None
            and saved.ingest_key == UUID(key)
        )
        assert all(
            v.snapshot is None and v.original_bytes is None
            for v in db.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == saved.id)
            )
        )


def test_authority_precedes_parsing_and_expiry_invalidates_prepared_result(
    auth_client, monkeypatch
):
    h = signin(auth_client)
    calls = []

    def parsed(raw):
        calls.append(raw)
        return result(raw)

    monkeypatch.setattr(pdf_ingestion, "exchange", parsed)
    assert pdf_upload(auth_client, {}).status_code == 403 and not calls
    assert (
        pdf_upload(auth_client, {**h, "Origin": "https://other.invalid"}).status_code == 403
        and not calls
    )
    real = identity.resolve

    def expiry(raw):
        monkeypatch.setattr(identity, "resolve", lambda *a, **kw: None)
        return result(raw)

    monkeypatch.setattr(pdf_ingestion, "exchange", expiry)
    assert pdf_upload(auth_client, h).status_code == 401
    monkeypatch.setattr(identity, "resolve", real)


def test_pdf_byte_quota_counts_actual_derived_utf8(auth_client, monkeypatch):
    raw = pdf()
    text = "😀" * 100

    def parse(data):
        out = result(data, text=text)
        out["pages"] = 1
        out["page_spans"] = [{"page": 1, "start_line": 1, "end_line": 1}]
        return out

    monkeypatch.setattr(pdf_ingestion, "exchange", parse)
    monkeypatch.setattr(documents, "MAX_RETAINED_BYTES", len(raw) + 400)
    h = signin(auth_client)
    row = pdf_upload(auth_client, h, raw).json()
    assert "id" in row
    assert pdf_upload(auth_client, h, raw).status_code == 409
    assert call(auth_client, h, row, "correct").status_code == 409
    assert call(auth_client, h, row, "forget").status_code == 200
    assert pdf_upload(auth_client, h, raw).status_code == 201


@pytest.mark.parametrize(
    "change",
    [
        {"source_sha256": "0" * 64},
        {"schema_version": True},
        {"pages": True},
        {"text": "x\x00"},
        {"text": "x" * 32001},
        {"page_spans": [{"page": 1, "start_line": 2, "end_line": 3}]},
        {"empty_pages": [2, 1]},
        {"engine": "remote"},
        {"version": "unknown"},
        {"status": "ready", "pages": 0},
    ],
)
def test_untrusted_worker_receipt_fails_closed(change):
    raw = pdf()
    response = result(raw)
    response.update(change)
    info, text = pdf_ingestion.validated(response, raw)
    assert info["status"] == "unavailable" and text == ""


def test_audit_failure_rolls_back_pdf_source_and_key(auth_client, auth_store, monkeypatch):
    monkeypatch.setattr(pdf_ingestion, "exchange", result)
    h = signin(auth_client)

    def fail(*args):
        raise SQLAlchemyError("Synthetic audit outage")

    event.listen(AuditEvent, "before_insert", fail)
    try:
        assert pdf_upload(auth_client, h).status_code == 503
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    with auth_store() as db:
        assert db.scalar(select(DocumentRecord.id)) is None
