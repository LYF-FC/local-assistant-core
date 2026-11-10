"""Fixed disposable restore proof for financial values/history; never an owner-data tool."""

import sys
from uuid import UUID

from sqlalchemy import select, update

from app import finance, identity
from app.config import settings
from app.db import SessionLocal
from app.manage import set_scope
from app.models import FinancialRecord, FinancialRevision, User

assert (
    settings.env == "test"
    and settings.postgres_user == "postgres"
    and settings.postgres_db in {"butler_test", "butler_test_restore"}
)
identifier = UUID("fa111111-1111-4111-8111-111111111111")
with SessionLocal.begin() as db:
    if sys.argv[1] == "seed":
        user = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
        set_scope(db, user, "finance_private", True)
        now = identity.now_utc()
        payload = {
            "schema_version": 1,
            "topic": "general",
            "basis": "unknown",
            "title": "Synthetic restore goal",
            "statement": "Unknown is not zero",
            "as_of": "2026-11-10",
            "target_date": None,
            "source_reference": "Synthetic financial restore",
            "source_date": None,
            "amount": None,
            "currency": None,
        }
        row = FinancialRecord(
            id=identifier,
            owner_id=user.id,
            scope_key="finance_private",
            kind="plan",
            state="active",
            revision=1,
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        finance.snapshot(db, user, row)
        db.flush()
        row.revision = 2
        row.accepted_by = user.id
        row.accepted_at = identity.now_utc()
        row.updated_at = row.accepted_at
        db.flush()
        finance.snapshot(db, user, row)
        finance.audit(db, user, row, "restore_fixture")
        for offset, basis in enumerate(["confirmed_input", "assumption", "forecast", "unknown"], 1):
            now = identity.now_utc()
            extra = FinancialRecord(
                id=UUID(int=identifier.int + offset),
                owner_id=user.id,
                scope_key="finance_private",
                kind="goal",
                state="active",
                revision=1,
                payload={
                    **payload,
                    "basis": basis,
                    "amount": "0.00" if basis != "unknown" else None,
                    "currency": "EUR" if basis != "unknown" else None,
                },
                created_at=now,
                updated_at=now,
            )
            db.add(extra)
            db.flush()
            finance.snapshot(db, user, extra)
            db.flush()
            if offset == 4:
                extra.state = "forgotten"
                extra.payload = None
                extra.revision = 2
                extra.updated_at = identity.now_utc()
                db.flush()
                db.execute(
                    update(FinancialRevision)
                    .where(FinancialRevision.record_id == extra.id)
                    .values(snapshot=None)
                )
                finance.snapshot(db, user, extra)
    else:
        row = db.get(FinancialRecord, identifier)
        assert (
            row.payload["amount"] is None
            and row.payload["basis"] == "unknown"
            and row.accepted_by == row.owner_id
        )
        revisions = list(
            db.scalars(
                select(FinancialRevision)
                .where(FinancialRevision.record_id == identifier)
                .order_by(FinancialRevision.revision)
            )
        )
        assert (
            len(revisions) == 2
            and revisions[0].snapshot["plan_status"] == "proposed"
            and revisions[1].snapshot == finance.document(row)
        )

if sys.argv[1] == "check":
    with SessionLocal() as db:
        for offset, basis in enumerate(["confirmed_input", "assumption", "forecast", "unknown"], 1):
            extra = db.get(FinancialRecord, UUID(int=identifier.int + offset))
            if offset == 4:
                assert extra.state == "forgotten" and extra.payload is None
                snapshots = list(
                    db.scalars(
                        select(FinancialRevision.snapshot).where(
                            FinancialRevision.record_id == extra.id
                        )
                    )
                )
                assert len(snapshots) == 2 and all(value is None for value in snapshots)
            else:
                assert extra.payload["basis"] == basis and extra.payload["amount"] == "0.00"

print("Synthetic financial current/history/basis/plan acceptance and scrubbed restoration verified")
