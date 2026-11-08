"""Actual PDF source/derived seals and restricted runtime behavior."""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_documents import call
from test_pdf_ingestion import pdf_lifecycle, pdf_upload, result

from app import pdf_ingestion

pytestmark = pytest.mark.integration


def test_pdf_runtime_lifecycle_and_byte_provenance(scenario, monkeypatch):
    client, h, _, _, _ = scenario
    monkeypatch.setattr(pdf_ingestion, "exchange", result)
    pdf_lifecycle(client, h)


def test_unavailable_source_is_retained_and_cannot_be_raw_reviewed(scenario):
    client, h, _, admin, _ = scenario
    row = pdf_upload(client, h).json()
    assert row["extraction"]["status"] == "unavailable"
    with admin.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text("UPDATE document_records SET reviewed=true,revision=revision+1 WHERE id=:id"),
            {"id": UUID(row["id"])},
        )
    assert call(client, h, row, "forget").status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        "ingest_key=gen_random_uuid(),revision=revision+1",
        "ingest_hash=repeat('0',64),revision=revision+1",
        "filename='forged.txt',revision=revision+1",
        "extraction_json=jsonb_set(extraction_json,'{engine}','null'),revision=revision+1",
        "extraction_json=jsonb_set(extraction_json,'{page_spans,0,start_line}','2'),reviewed=false,revision=revision+1",
    ],
)
def test_pdf_record_metadata_and_idempotency_are_sealed(scenario, monkeypatch, change):
    client, h, _, admin, _ = scenario
    monkeypatch.setattr(pdf_ingestion, "exchange", result)
    row = pdf_upload(client, h).json()
    with admin.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(f"UPDATE document_records SET {change} WHERE id=:id"), {"id": UUID(row["id"])}
        )
    assert call(client, h, row, "forget").status_code == 200


def test_raw_derived_snapshot_and_original_are_bound(scenario, monkeypatch):
    client, h, _, admin, _ = scenario
    monkeypatch.setattr(pdf_ingestion, "exchange", result)
    row = pdf_upload(client, h).json()
    with admin.begin() as db:
        db.execute(
            text(
                "UPDATE document_records SET title='Synthetic second',revision=revision+1 WHERE id=:id"
            ),
            {"id": UUID(row["id"])},
        )
    current = call(client, h, row, "read").json()
    snapshot = {key: value for key, value in current.items() if key != "can_edit"}
    import json

    from sqlalchemy import select

    from app.models import DocumentVersion

    with admin() as db:
        raw = db.scalar(
            select(DocumentVersion.original_bytes).where(
                DocumentVersion.document_id == UUID(row["id"]), DocumentVersion.revision == 1
            )
        )
    for forge_hash in [True, False]:
        changed = dict(snapshot)
        if forge_hash:
            changed["text_sha256"] = "0" * 64
        with admin.begin() as db, pytest.raises(DBAPIError):
            db.execute(
                text("""INSERT INTO document_versions(id,document_id,revision,actor_id,operation,snapshot,original_bytes,created_at)
            VALUES(gen_random_uuid(),:id,2,:actor,'corrected',CAST(:snapshot AS jsonb),:original,:created)"""),
                {
                    "id": UUID(row["id"]),
                    "actor": UUID(row["owner_id"]),
                    "snapshot": json.dumps(changed),
                    "original": raw if forge_hash else b"%PDF-forged",
                    "created": current["updated_at"],
                },
            )
    current = call(client, h, row, "read").json()
    assert call(client, h, current, "forget").status_code == 200


def test_downgrade_refuses_retained_pdf_provenance(scenario):
    import subprocess
    from pathlib import Path

    client, h, _, _, _ = scenario
    row = pdf_upload(client, h).json()
    attempt = subprocess.run(
        ["alembic", "downgrade", "0023_document_archive"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert attempt.returncode != 0
    assert "PDF provenance evidence exists" in attempt.stderr
    assert call(client, h, row, "read").status_code == 200
    assert call(client, h, row, "forget").status_code == 200


def test_downgrade_preserves_forgotten_extraction_operation(scenario, monkeypatch):
    from work_migration_helpers import assert_downgrade_refused

    client, h, _, _, _ = scenario
    monkeypatch.setattr(pdf_ingestion, "exchange", result)
    row = pdf_upload(client, h).json()
    response = call(client, h, row, "extract", expected_revision=row["revision"])
    assert response.status_code == 200
    row = response.json()
    assert call(client, h, row, "forget").status_code == 200
    assert_downgrade_refused(
        "0023_document_archive", "0024_pdf_ingestion", "PDF provenance evidence exists"
    )


def test_raw_reextraction_cannot_retain_review(scenario, monkeypatch):
    from sqlalchemy import select

    from app import documents, identity
    from app.models import DocumentRecord, DocumentVersion, User

    client, h, _, admin, _ = scenario
    monkeypatch.setattr(pdf_ingestion, "exchange", result)
    row = pdf_upload(client, h).json()
    row = call(client, h, row, "correct").json()
    assert row["reviewed"] is True
    with admin.begin() as db, pytest.raises(DBAPIError):
        record = db.get(DocumentRecord, UUID(row["id"]))
        original = db.scalar(
            select(DocumentVersion.original_bytes).where(
                DocumentVersion.document_id == record.id,
                DocumentVersion.revision == record.revision,
            )
        )
        record.revision += 1
        record.updated_at = identity.now_utc()
        db.flush()
        documents.snapshot(db, db.get(User, record.owner_id), record, "extracted", original)
        db.flush()
    assert call(client, h, row, "forget").status_code == 200
