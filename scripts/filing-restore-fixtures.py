"""Synthetic live filing records for isolated logical recovery.

Scope of the claim: this proves that *database records* survive a strict dump and restore: a
pending and an unknown filing with their honest sealed history, the single-use authorization
marker, the destination reservation and the guards that protect them. It does NOT prove that a
synthetic destination survives an application restart: the destination is an in-memory double
that a restarted worker recreates empty, so a lookup after a real restart would say "absent".
"""

import hashlib
import sys
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app import documents, filing, identity, invoice_fields, invoice_filing, invoice_review
from app.config import settings
from app.db import SessionLocal
from app.models import (
    DocumentRecord,
    FilingExecution,
    FilingExecutionEvent,
    InvoiceReview,
    User,
)

assert settings.env == "test" and settings.postgres_db in {"butler_test", "butler_test_restore"}
assert (
    settings.postgres_user == "postgres"
)  # Deliberately fixed PostgreSQL/restore harness, not Compose/browser.
phase = sys.argv[1]
assert phase in {"seed", "check"}
SCOPE = "household_shared"
FILES = {"pending": "synthetic-filing-pending.txt", "unknown": "synthetic-filing-unknown.txt"}


def identifier(name):
    return uuid5(NAMESPACE_URL, "butler-synthetic-filing-restore-" + name)


def seed_source(db, owner, name, number):
    """A reviewed invoice with an approved (still non-executable) plan, as the product creates it."""
    content = (
        f"Issuer: Synthetic Filing Vendor\nInvoice number: {number}\nTotal: 12.00\nCurrency: EUR"
    )
    now = identity.now_utc()
    original = content.encode()
    doc = DocumentRecord(
        id=identifier(name),
        owner_id=owner.id,
        scope_key=SCOPE,
        state="active",
        revision=1,
        title="Synthetic filing restore invoice",
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
    choices["issuer"] = {"state": "confirmed", "value": "Synthetic Filing Vendor", "line": 1}
    choices["invoice_number"] = {"state": "confirmed", "value": number, "line": 2}
    row.state = "reviewed"
    row.revision = 2
    row.updated_at = identity.now_utc()
    row.data = {
        **row.data,
        "decisions": invoice_fields.review(doc, invoice_fields.Decisions(**choices)),
    }
    row.issuer_key, row.number_key = "synthetic filing vendor", number.lower()
    invoice_review.remember(db, owner, row)
    db.flush()
    row.data = {
        **row.data,
        "filing_plan": invoice_filing.propose(doc, row, "invoices/manual", FILES[name]),
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
            "approved_revision": row.revision + 1,
        },
    }
    row.revision += 1
    row.updated_at = identity.now_utc()
    invoice_review.remember(db, owner, row)
    db.flush()
    return doc, row


def seed_filing(db, owner, doc, row, name):
    now = identity.now_utc()
    path = row.data["filing_plan"]["relative_path"]
    execution = FilingExecution(
        document_id=doc.id,
        owner_id=owner.id,
        scope_key=SCOPE,
        plan_revision=row.revision,
        source_revision=doc.revision,
        destination_key=filing.destination_key(SCOPE, path),
        destination=filing.DESTINATION,
        revision=1,
        state="pending",
        attempts=0,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(execution)
    filing.record_event(db, execution, "requested", owner)
    if name == "unknown":
        # An attempt was claimed and its outcome never reported: the honest ambiguous state.
        later = identity.now_utc()
        filing.change(
            db,
            execution,
            "attempted",
            later,
            attempts=1,
            attempt_started_at=later,
            authorization_consumed_at=later,
        )
        filing.change(
            db,
            execution,
            "unknown",
            later,
            state="unknown",
            reason="ambiguous_outcome",
            attempt_started_at=None,
            next_attempt_at=later + filing.RECONCILE_INTERVAL,
        )
    db.flush()
    return execution


def rejected(statement, **params):
    """True when the guard refuses the statement; the transaction is rolled back either way."""
    try:
        with SessionLocal.begin() as db:
            db.execute(text(statement), params)
    except DBAPIError:
        return True
    return False


with SessionLocal.begin() as db:
    owner = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
    assert owner
    if phase == "seed":
        for name, number in (("pending", "FR-001"), ("unknown", "FR-002")):
            doc, row = seed_source(db, owner, name, number)
            seed_filing(db, owner, doc, row, name)
    else:
        for name in ("pending", "unknown"):
            doc = db.get(DocumentRecord, identifier(name))
            review = db.get(InvoiceReview, identifier(name))
            execution = db.scalar(
                select(FilingExecution).where(FilingExecution.document_id == identifier(name))
            )
            events = list(
                db.scalars(
                    select(FilingExecutionEvent)
                    .where(FilingExecutionEvent.execution_id == execution.id)
                    .order_by(FilingExecutionEvent.revision)
                )
            )
            plan = review.data["filing_plan"]
            assert doc.state == "active" and review.state == "reviewed"
            assert plan["state"] == "approved" and plan["execution_authorized"] is False
            assert execution.owner_id == owner.id and execution.scope_key == SCOPE
            assert execution.plan_revision == review.revision == plan["approved_revision"]
            assert execution.source_revision == doc.revision
            assert execution.destination_key == filing.destination_key(SCOPE, plan["relative_path"])
            assert execution.scrubbed_at is None and execution.resolved_at is None
            # Every sealed history snapshot is intact and equals the state it describes.
            assert all(e.snapshot is not None for e in events)
            assert events[-1].snapshot == filing.document(execution)
            assert [e.revision for e in events] == list(range(1, execution.revision + 1))
            if name == "pending":
                assert execution.state == "pending" and execution.attempts == 0
                assert execution.authorization_consumed_at is None
                assert [e.operation for e in events] == ["requested"]
            else:
                assert execution.state == "unknown" and execution.attempts == 1
                assert execution.authorization_consumed_at is not None
                assert execution.reason == "ambiguous_outcome"
                assert [e.operation for e in events] == ["requested", "attempted", "unknown"]
        # The guards, the destination reservation and the privacy scrub still exist after restore.
        names = {
            r[0]
            for r in db.execute(
                text(
                    "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE "
                    "'butler_filing_%'"
                )
            )
        }
        assert names == {
            "butler_filing_guard",
            "butler_filing_truncate",
            "butler_filing_event_guard",
            "butler_filing_event_truncate",
        }
        assert db.scalar(
            text("SELECT count(*) FROM pg_indexes WHERE indexname='uq_filing_destination_active'")
        )
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM filing_executions WHERE id IN (SELECT execution_id FROM "
                    "filing_execution_events) AND state IN ('pending','unknown')"
                )
            )
            >= 2
        )
if phase == "check":
    with SessionLocal() as db:
        pending_id = db.scalar(
            select(FilingExecution.id).where(FilingExecution.document_id == identifier("pending"))
        )
    for statement in (
        "DELETE FROM filing_execution_events WHERE execution_id=:id",
        "UPDATE filing_execution_events SET operation='filed' WHERE execution_id=:id",
        "DELETE FROM filing_executions WHERE id=:id",
        (
            "UPDATE filing_executions SET state='filed',next_attempt_at=NULL,"
            "resolved_at=updated_at,revision=revision+1 WHERE id=:id"
        ),
        (
            "UPDATE filing_executions SET authorization_consumed_at=now(),attempts=1,"
            "revision=revision+1 WHERE id=:id"
        ),
    ):
        assert rejected(statement, id=pending_id), statement
    assert rejected("TRUNCATE filing_executions CASCADE")
if phase == "seed":
    print("Synthetic live pending and unknown filing records seeded")
else:
    print(
        "Synthetic live pending and unknown filing records, sealed history, single-use "
        "authorization marker and guards verified (database records only; not destination "
        "durability across application restarts)"
    )
