"""Migration 0034 downgrade is intentionally destructive: it is evidence, not a rollback strategy.

Downgrading drops ``filing_executions``, ``filing_execution_events`` and both seal functions. That
destroys every execution record and its sealed history, including the evidence that a filing
request was consumed. ``audit_events`` metadata survives, and an effect already applied to a
destination is not recalled. After a re-upgrade the same approved plan revision can be requested
again; only the destination's own no-overwrite rule then stands between it and a second write.
"""

import subprocess
from pathlib import Path

import pytest
from conftest import RUNTIME_PASSWORD
from sqlalchemy import select, text
from test_filing import body
from test_filing_postgres import approved_source, forget_owned_test_sources  # noqa: F401

from app import filing, filing_worker
from app.models import AuditEvent, FilingExecution
from app.runtime_role import configure

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
FILING_FUNCTIONS = ("butler_seal_filing", "butler_seal_filing_event")
FILING_TABLES = ("filing_executions", "filing_execution_events")


def migrate(*args):
    result = subprocess.run(
        ["alembic", *args], cwd=BACKEND, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def objects(admin):
    with admin() as db:
        tables = db.execute(
            text(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relkind='r' AND c.relname = ANY(:names)"
            ),
            {"names": list(FILING_TABLES)},
        ).scalar()
        functions = db.execute(
            text("SELECT count(*) FROM pg_proc WHERE proname = ANY(:names)"),
            {"names": list(FILING_FUNCTIONS)},
        ).scalar()
        triggers = db.execute(
            text("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'butler\\_filing\\_%'")
        ).scalar()
    return tables, functions, triggers


def test_downgrading_0034_destroys_filing_records_but_keeps_audit_and_reopens_the_plan(
    scenario, runtime_engine
):
    client, h, _, admin, _ = scenario
    doc, receipt, path = approved_source(scenario)
    created = client.post("/api/v1/filing/request", headers=h, json=body(doc, receipt))
    assert created.status_code == 201, created.json()
    identifier = created.json()["filing"]["id"]
    from sqlalchemy.orm import sessionmaker

    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with admin() as db:
        row = db.execute(
            select(
                FilingExecution.id,
                FilingExecution.owner_id,
                FilingExecution.scope_key,
                FilingExecution.document_id,
            ).where(FilingExecution.id == identifier)
        ).one()
    destination = filing.SyntheticDestination()  # the external destination outlives the schema
    assert filing_worker.process(maker, row, destination) == "filed"
    assert destination.writes == 1
    with admin() as db:
        consumed = db.get(FilingExecution, row.id)
        assert consumed.state == "filed" and consumed.authorization_consumed_at is not None
        events = db.execute(
            text("SELECT count(*) FROM filing_execution_events WHERE execution_id=:i"),
            {"i": row.id},
        ).scalar()
        audits = db.scalars(
            select(AuditEvent.event_type).where(
                AuditEvent.entity_type == "filing_execution", AuditEvent.entity_id == identifier
            )
        ).all()
    assert events == 3 and {"filing.requested", "filing.attempted", "filing.filed"} <= set(audits)
    assert objects(admin) == (2, 2, 4)

    migrate("downgrade", "0033_notification_integrity")
    try:
        # Tables, seal functions and their triggers are gone, with all records and history.
        assert objects(admin) == (0, 0, 0)
        with admin() as db:
            kept = db.scalars(
                select(AuditEvent.event_type).where(
                    AuditEvent.entity_type == "filing_execution",
                    AuditEvent.entity_id == identifier,
                )
            ).all()
        # Metadata audit survives; nothing about the consumption itself does.
        assert {"filing.requested", "filing.attempted", "filing.filed"} <= set(kept)
    finally:
        migrate("upgrade", "head")
        migrate("check")
        with admin.begin() as db:  # recreated tables need the restricted role's grants again
            configure(db.connection().connection.driver_connection, RUNTIME_PASSWORD)
    assert objects(admin) == (2, 2, 4)
    with admin() as db:
        assert db.scalar(text("SELECT count(*) FROM filing_executions")) == 0
        assert db.scalar(text("SELECT count(*) FROM filing_execution_events")) == 0

    # Consequence: the consumed request is no longer remembered, so the same approved plan
    # revision can be requested again and starts as a brand-new, unconsumed authorization.
    again = client.post("/api/v1/filing/request", headers=h, json=body(doc, receipt))
    assert again.status_code == 201 and again.json()["replayed"] is False, again.json()
    reopened = again.json()["filing"]
    assert reopened["id"] != identifier and reopened["state"] == "pending"
    assert reopened["attempts"] == 0 and reopened["plan_revision"] == receipt["review_revision"]
    with admin() as db:
        fresh = db.get(FilingExecution, reopened["id"])
        assert fresh.authorization_consumed_at is None
        new_row = db.execute(
            select(
                FilingExecution.id,
                FilingExecution.owner_id,
                FilingExecution.scope_key,
                FilingExecution.document_id,
            ).where(FilingExecution.id == reopened["id"])
        ).one()
    # The effect applied before the downgrade is not recalled; the destination's own
    # no-overwrite rule is the only remaining defence against a second write.
    assert filing_worker.process(maker, new_row, destination) == "failed"
    assert destination.writes == 1 and list(destination.files) == [path]
    assert destination.files[path][0] == identifier  # still owned by the original filing
    with admin() as db:
        failed = db.get(FilingExecution, reopened["id"])
        assert failed.state == "failed" and failed.reason == "collision"
