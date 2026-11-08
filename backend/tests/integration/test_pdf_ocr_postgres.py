"""OCR metadata uses the existing restricted source/version/recovery seals."""

import pytest
from sqlalchemy import text
from test_documents import call
from test_pdf_ingestion import pdf_upload
from test_pdf_ocr import ocr_call, ocr_lifecycle, receipt
from work_migration_helpers import assert_downgrade_refused

from app import pdf_ingestion

pytestmark = pytest.mark.integration


def test_ocr_restricted_lifecycle(scenario, monkeypatch):
    client, h, _, _, _ = scenario
    monkeypatch.setattr(pdf_ingestion, "exchange", receipt)
    ocr_lifecycle(client, h)


def test_ocr_provenance_blocks_downgrade_and_three_page_receipts(scenario, monkeypatch):
    client, h, _, admin, _ = scenario
    monkeypatch.setattr(pdf_ingestion, "exchange", receipt)
    row = ocr_call(client, h, pdf_upload(client, h).json()).json()
    assert row["extraction"]["engine"] == "poppler-tesseract-v1"
    with admin() as db:
        assert (
            db.scalar(
                text(
                    "SELECT public.butler_pdf_extraction_valid(jsonb_build_object('engine','poppler-tesseract-v1','version','25.03.0','status','no_text','pages',3,'page_spans','[]'::jsonb,'empty_pages','[]'::jsonb),'')"
                )
            )
            is False
        )
    assert_downgrade_refused("0024_pdf_ingestion", "0025_pdf_ocr", "OCR provenance evidence exists")
    assert call(client, h, row, "forget").status_code == 200
