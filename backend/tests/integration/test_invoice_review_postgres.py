"""Actual restricted-role invoice provenance, aggregate cleanup and row-wait evidence."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from conftest import SYNTHETIC_PASSWORD
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_documents import call as document_call
from test_invoice_review import TEXT, call, confirm, prepare, source

from app import identity
from app.models import AuthSession, DocumentRecord, InvoiceReview, InvoiceRevision, User

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def forget_owned_test_sources(scenario):
    # Retain sealed audit/tombstone evidence, but do not leave shared source text
    # for unrelated retrieval/lifecycle tests or later focused reruns.
    yield
    client, _, _, admin, uid = scenario
    with admin() as db:
        owner = db.get(User, uid)
        slug = owner.slug
        rows = [
            {"id": str(r.id), "scope": r.scope_key, "revision": r.revision}
            for r in db.scalars(
                select(DocumentRecord).where(
                    DocumentRecord.owner_id == uid, DocumentRecord.state == "active"
                )
            )
        ]
    if rows:
        response = client.post(
            "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
        )
        assert response.status_code == 200
        headers = {"X-CSRF-Token": response.json()["csrf_token"]}
        for row in rows:
            assert document_call(client, headers, row, "forget").status_code == 200


def test_runtime_invoice_lifecycle_duplicates_and_document_forget(scenario):
    client, h, _, admin, _ = scenario
    unique_text = TEXT + "\nSynthetic SQL fixture " + uuid4().hex
    doc = source(client, h, unique_text)
    prepare(client, h, doc)
    other = source(client, h, unique_text)
    assert call(client, h, doc, "duplicates").json()["items"][0]["document"]["id"] == other["id"]
    r = confirm(client, h, doc)
    assert r["status"] == "reviewed"
    assert document_call(client, h, doc, "forget").status_code == 200
    with admin() as db:
        row = db.get(InvoiceReview, UUID(doc["id"]))
        assert row.data is None and row.issuer_key is None and row.number_key is None
        assert all(
            x.snapshot is None
            for x in db.scalars(
                select(InvoiceRevision).where(InvoiceRevision.document_id == row.document_id)
            )
        )


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM invoice_reviews WHERE document_id=:id",
        "TRUNCATE invoice_reviews CASCADE",
        "UPDATE invoice_reviews SET revision=revision+2 WHERE document_id=:id",
        "UPDATE invoice_reviews SET owner_id=:other,revision=revision+1 WHERE document_id=:id",
        "UPDATE invoice_reviews SET scope_key='member_a_private',revision=revision+1 WHERE document_id=:id",
        "UPDATE invoice_revisions SET snapshot=NULL WHERE document_id=:id",
        "DELETE FROM invoice_revisions WHERE document_id=:id",
        "TRUNCATE invoice_revisions",
    ],
)
def test_sql_identity_history_and_privilege_guards(scenario, runtime_engine, statement):
    client, h, _, _, _ = scenario
    doc = source(client, h)
    prepare(client, h, doc)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(statement), {"id": UUID(doc["id"]), "other": uuid4()})


def wait_for_source_lock(admin):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        with admin() as db:
            if db.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%document_records%FOR %'"
                )
            ):
                return
        time.sleep(0.02)
    raise AssertionError("Invoice request did not reach actual source wait")


@pytest.mark.parametrize(
    "operation",
    ["read", "review", "history", "export", "duplicates", "plan", "approve_plan", "withdraw_plan"],
)
def test_expiry_after_actual_source_wait(scenario, monkeypatch, operation):
    client, h, _, admin, uid = scenario
    doc = source(client, h)
    r = prepare(client, h, doc)
    with admin() as db:
        expiry = db.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == uid))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(
                select(DocumentRecord).where(DocumentRecord.id == UUID(doc["id"])).with_for_update()
            )
            payload = (
                {"acknowledge_copy_limits": True}
                if operation == "export"
                else {"acknowledge_plan_only": True, "acknowledge_duplicate_limits": True}
                if operation == "approve_plan"
                else {}
            )
            if operation in {"plan", "approve_plan", "withdraw_plan"}:
                payload.update(
                    expected_document_revision=doc["revision"],
                    expected_review_revision=r["review_revision"],
                )
            pending = pool.submit(call, client, h, doc, operation, r, **payload)
            wait_for_source_lock(admin)
            monkeypatch.setattr(
                identity, "now_utc", lambda: identity.aware(expiry) + timedelta(seconds=1)
            )
        assert pending.result(timeout=5).status_code == 401
    with admin() as db:
        assert db.get(InvoiceReview, UUID(doc["id"])).revision == 1


def test_actual_source_revision_change_and_concurrent_review_conflict(scenario):
    client, h, _, admin, _ = scenario
    doc = source(client, h)
    r = prepare(client, h, doc)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            locked = db.scalar(
                select(DocumentRecord).where(DocumentRecord.id == UUID(doc["id"])).with_for_update()
            )
            pending = pool.submit(call, client, h, doc, "review", r)
            wait_for_source_lock(admin)
            locked.title = "Synthetic concurrent correction"
            locked.revision += 1
            locked.updated_at = identity.now_utc()
        assert pending.result(timeout=5).status_code == 409
    assert call(client, h, doc, "read").json()["review"] is None


def test_runtime_audit_failure_rolls_back_aggregate_forget(scenario, runtime_engine):
    client, h, _, admin, _ = scenario
    doc = source(client, h)
    confirm(client, h, doc)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic invoice audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        assert document_call(client, h, doc, "forget").status_code == 503
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert db.get(DocumentRecord, UUID(doc["id"])).state == "active"
        assert db.get(InvoiceReview, UUID(doc["id"])).state == "reviewed"


def test_human_review_quota_keeps_aggregate_forget_available(scenario):
    client, h, _, _, _ = scenario
    doc = source(client, h)
    r = prepare(client, h, doc)
    for _ in range(99):
        response = call(client, h, doc, "review", r)
        assert response.status_code == 200
        r = response.json()
    assert r["review_revision"] == 100
    assert call(client, h, doc, "review", r).status_code == 429
    from test_invoice_filing import plan_call

    assert plan_call(client, h, doc, "plan", r).status_code == 429
    assert document_call(client, h, doc, "forget").status_code == 200


def test_runtime_filing_plan_concurrent_source_and_sealed_history(scenario):
    from test_invoice_filing import approved, plan_call

    client, h, _, admin, _ = scenario
    doc = source(client, h)
    r = approved(client, h, doc, confirm(client, h, doc))
    with admin() as db:
        row = db.get(InvoiceReview, UUID(doc["id"]))
        assert row.data["filing_plan"]["state"] == "approved"
        assert row.data["filing_plan"]["execution_authorized"] is False
        assert (
            db.scalar(
                select(InvoiceRevision.snapshot).where(
                    InvoiceRevision.document_id == row.document_id, InvoiceRevision.revision == 4
                )
            )["data"]["filing_plan"]
            == row.data["filing_plan"]
        )
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            locked = db.scalar(
                select(DocumentRecord).where(DocumentRecord.id == UUID(doc["id"])).with_for_update()
            )
            pending = pool.submit(plan_call, client, h, doc, "withdraw_plan", r)
            wait_for_source_lock(admin)
            locked.title = "Synthetic changed plan source"
            locked.revision += 1
            locked.updated_at = identity.now_utc()
        assert pending.result(timeout=5).status_code == 409
    assert call(client, h, doc, "read").json()["review"] is None


def test_runtime_plan_audit_failure_then_derived_forget_scrubs_all(scenario, runtime_engine):
    from test_invoice_filing import approved, plan_call

    client, h, _, admin, _ = scenario
    doc = source(client, h)
    r = approved(client, h, doc, confirm(client, h, doc))

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic plan audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        assert plan_call(client, h, doc, "withdraw_plan", r).status_code == 503
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert db.get(InvoiceReview, UUID(doc["id"])).data["filing_plan"]["state"] == "approved"
    assert call(client, h, doc, "forget", r).status_code == 200
    with admin() as db:
        row = db.get(InvoiceReview, UUID(doc["id"]))
        assert row.data is None and row.revision == 5
        assert all(
            x.snapshot is None
            for x in db.scalars(
                select(InvoiceRevision).where(InvoiceRevision.document_id == row.document_id)
            )
        )
