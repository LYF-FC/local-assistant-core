"""Explicit OCR remains uncertain, scoped and bound to the requested engine."""

import pytest
from test_approvals import signin
from test_documents import call
from test_pdf_ingestion import pdf_upload, result

from app import pdf_ingestion


def receipt(raw, *, ocr=False):
    value = result(raw)
    if ocr:
        value["engine"] = "poppler-tesseract-v1"
    return value


def ocr_call(client, headers, row, **changes):
    return client.post(
        f"/api/v1/documents/{row['id']}/extract",
        headers=headers,
        json={
            "scope": row["scope"],
            "expected_revision": row["revision"],
            "mode": "ocr",
            **changes,
        },
    )


def ocr_lifecycle(client, h):
    row = pdf_upload(client, h).json()
    raw_hash = row["sha256"]
    row = call(client, h, row, "correct").json()
    response = ocr_call(client, h, row)
    assert response.status_code == 200, response.text
    row = response.json()
    assert not row["reviewed"] and row["revision"] == 3 and row["sha256"] == raw_hash
    assert row["extraction"]["engine"] == "poppler-tesseract-v1"
    assert call(client, h, row, "excerpt", end_line=1).status_code == 409
    row = call(client, h, row, "correct").json()
    excerpt = call(client, h, row, "excerpt", end_line=1).json()
    assert "uncertain OCR" in excerpt["notice"]
    assert excerpt["page_spans"] == [{"page": 1, "start_line": 1, "end_line": 1}]
    assert call(client, h, row, "original").json()["sha256"] == raw_hash
    history = call(client, h, row, "history").json()["items"]
    assert history[0]["snapshot"]["extraction"]["engine"] == "poppler-text-v1"
    assert history[-1]["snapshot"]["extraction"]["engine"] == "poppler-tesseract-v1"
    assert call(client, h, row, "forget").status_code == 200


def test_explicit_ocr_version_review_citations_original_and_forget(auth_client, monkeypatch):
    monkeypatch.setattr(pdf_ingestion, "exchange", receipt)
    ocr_lifecycle(auth_client, signin(auth_client))


@pytest.mark.parametrize("wrong_engine", [True, False])
def test_ocr_receipt_wrong_mode_or_page_limit_fails_closed(auth_client, monkeypatch, wrong_engine):
    def malformed(raw, *, ocr=False):
        value = receipt(raw, ocr=ocr)
        if ocr:
            if wrong_engine:
                value["engine"] = "poppler-text-v1"
            else:
                value["pages"] = 3
        return value

    monkeypatch.setattr(pdf_ingestion, "exchange", malformed)
    h = signin(auth_client)
    row = pdf_upload(auth_client, h).json()
    row = ocr_call(auth_client, h, row).json()
    assert row["extraction"]["status"] == "unavailable"
    assert row["extraction"]["engine"] == "poppler-tesseract-v1"
    assert not row["reviewed"] and row["content_text"] == ""
    assert call(auth_client, h, row, "correct").status_code == 409


def test_ocr_requires_valid_mode_revision_and_current_authority(auth_client, monkeypatch):
    monkeypatch.setattr(pdf_ingestion, "exchange", receipt)
    h = signin(auth_client)
    row = pdf_upload(auth_client, h).json()

    def must_not_parse(*args, **kwargs):
        raise AssertionError("Unauthorized or stale OCR reached parser")

    monkeypatch.setattr(pdf_ingestion, "exchange", must_not_parse)
    assert ocr_call(auth_client, h, row, mode="arbitrary-command").status_code == 422
    assert ocr_call(auth_client, h, row, expected_revision=2).status_code == 409
    assert ocr_call(auth_client, {}, row).status_code == 403
