"""Synthetic invoice/source/derived-history sentinel for isolated logical recovery."""

import hashlib
import sys
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select

from app import documents, identity, invoice_fields, invoice_filing, invoice_review
from app.config import settings
from app.db import SessionLocal
from app.models import DocumentRecord, InvoiceReview, InvoiceRevision, User

assert settings.env == "test" and settings.postgres_db in {"butler_test", "butler_test_restore"}
assert (
    settings.postgres_user == "postgres"
)  # Deliberately fixed PostgreSQL/restore harness, not Compose/browser.
phase = sys.argv[1]
assert phase in {"seed", "check"}
content = "Issuer: Synthetic Restore Vendor\nInvoice number: R-001\nTotal: 99.00\nCurrency: EUR"
with SessionLocal.begin() as db:
    owner = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
    assert owner
    for name in ("reviewed", "forgotten"):
        identifier = uuid5(NAMESPACE_URL, "butler-synthetic-invoice-restore-" + name)
        if phase == "seed":
            now = identity.now_utc()
            original = content.encode()
            doc = DocumentRecord(
                id=identifier,
                owner_id=owner.id,
                scope_key="household_shared",
                state="active",
                revision=1,
                title="Synthetic restore invoice",
                filename="synthetic.txt",
                source_reference="Synthetic fixture",
                content_text=content,
                sha256=hashlib.sha256(original).hexdigest(),
                byte_size=len(original),
                reviewed=False,
                created_at=now,
                updated_at=now,
            )
            db.add(doc)
            db.flush()
            documents.snapshot(db, owner, doc, "uploaded", original)
            db.flush()
            doc.reviewed = True
            doc.revision = 2
            doc.updated_at = identity.now_utc()
            db.flush()
            documents.snapshot(db, owner, doc, "corrected", original)
            db.flush()
            row = InvoiceReview(
                document_id=doc.id,
                owner_id=owner.id,
                scope_key=doc.scope_key,
                state="draft",
                revision=1,
                source_revision=doc.revision,
                data=invoice_fields.prepare(doc),
                created_at=identity.now_utc(),
                updated_at=identity.now_utc(),
            )
            row.updated_at = row.created_at
            db.add(row)
            invoice_review.remember(db, owner, row)
            db.flush()
            choices = {
                f: {"state": "unknown", "value": None, "note": "Unknown in synthetic fixture"}
                for f in invoice_fields.FIELDS
            }
            choices["issuer"] = {
                "state": "confirmed",
                "value": "Synthetic Restore Vendor",
                "line": 1,
            }
            choices["invoice_number"] = {"state": "confirmed", "value": "R-001", "line": 2}
            row.state = "reviewed"
            row.revision = 2
            row.updated_at = identity.now_utc()
            row.data = {
                **row.data,
                "decisions": invoice_fields.review(doc, invoice_fields.Decisions(**choices)),
            }
            row.issuer_key, row.number_key = "synthetic restore vendor", "r-001"
            invoice_review.remember(db, owner, row)
            db.flush()
            row.data = {
                **row.data,
                "filing_plan": invoice_filing.propose(
                    doc, row, "invoices/manual", "synthetic-restore.txt"
                ),
            }
            row.revision += 1
            row.updated_at = identity.now_utc()
            invoice_review.remember(db, owner, row)
            db.flush()
            row.data = {
                **row.data,
                "filing_plan": {
                    **row.data["filing_plan"],
                    "state": "approved",
                    "approved_revision": 4,
                },
            }
            row.revision += 1
            row.updated_at = identity.now_utc()
            invoice_review.remember(db, owner, row)
            db.flush()
            if name == "forgotten":
                invoice_review.forget_for_document(db, owner, doc)
        else:
            row = db.get(InvoiceReview, identifier)
            doc = db.get(DocumentRecord, identifier)
            history = list(
                db.scalars(
                    select(InvoiceRevision)
                    .where(InvoiceRevision.document_id == identifier)
                    .order_by(InvoiceRevision.revision)
                )
            )
            assert row.owner_id == doc.owner_id == owner.id and row.source_revision == doc.revision
            if name == "reviewed":
                assert (
                    row.state == "reviewed"
                    and row.issuer_key == "synthetic restore vendor"
                    and len(history) == 4
                )
                assert (
                    row.data["source"]["sha256"] == doc.sha256
                    and row.data["decisions"]["total"]["value"] is None
                )
                assert row.data["candidates"]["total"][0]["value"] == "99.00"
                plan = row.data["filing_plan"]
                assert plan["state"] == "approved" and plan["execution_authorized"] is False
                assert (
                    plan["source_sha256"] == doc.sha256 and plan["source_revision"] == doc.revision
                )
                assert history[3].snapshot["data"]["filing_plan"] == plan
                assert history[2].snapshot["data"]["filing_plan"]["state"] == "proposed"
            else:
                assert (
                    row.state == "forgotten"
                    and row.data is None
                    and row.issuer_key is None
                    and row.number_key is None
                )
                assert all(r.snapshot is None for r in history) and len(history) == 5
                assert doc.state == "active" and doc.content_text == content
print(
    "Synthetic invoice source/decision/non-executable filing plan/history and forgotten-derived recovery verified"
)
