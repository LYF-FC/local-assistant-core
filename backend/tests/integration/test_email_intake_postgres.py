import base64
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_documents import call as document_call
from test_email_intake import ingest, mail_call, message
from test_invoice_review_postgres import forget_owned_test_sources  # noqa: F401

from app import identity
from app.models import AuthSession, DocumentRecord, EmailEnvelope

pytestmark = pytest.mark.integration


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
    raise AssertionError("Request did not reach source wait")


def test_runtime_raw_email_fidelity_export_and_terminal_scrubbing(scenario):
    client, h, _, admin, _ = scenario
    raw = message()
    r = ingest(client, h, raw)
    assert r.status_code == 201, r.json()
    doc = r.json()["document"]
    assert (
        base64.b64decode(
            mail_call(client, h, doc, "export", acknowledge_copy_limits=True).json()[
                "original_base64"
            ]
        )
        == raw
    )
    with admin() as db:
        assert db.get(EmailEnvelope, UUID(doc["id"])).original_message == raw
    assert document_call(client, h, doc, "forget").status_code == 200
    with admin() as db:
        row = db.get(EmailEnvelope, UUID(doc["id"]))
        assert (
            row.original_message is None
            and row.attachment_sha256 is None
            and row.state == "forgotten"
        )
    assert ingest(client, h, raw).status_code == 410


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE email_envelopes SET original_message=original_message WHERE document_id=:id",
        "UPDATE email_envelopes SET attachment_filename='changed.txt' WHERE document_id=:id",
        "UPDATE email_envelopes SET attachment_sha256=repeat('a',64) WHERE document_id=:id",
        "UPDATE email_envelopes SET message_sha256=repeat('a',64) WHERE document_id=:id",
        "UPDATE email_envelopes SET state='forgotten',original_message=NULL,attachment_filename=NULL,attachment_sha256=NULL,forgotten_at=now() WHERE document_id=:id",
        "DELETE FROM email_envelopes WHERE document_id=:id",
        "TRUNCATE email_envelopes",
    ],
)
def test_runtime_immutable_original_and_privilege_guards(scenario, runtime_engine, statement):
    client, h, _, _, _ = scenario
    doc = ingest(client, h).json()["document"]
    with pytest.raises(DBAPIError), runtime_engine.begin() as db:
        db.execute(text(statement), {"id": doc["id"]})


def test_concurrent_exact_intake_creates_one_source_and_no_partial_receipt(scenario):
    client, h, _, admin, uid = scenario
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(ingest, client, h) for _ in range(2)]
        results = [f.result(timeout=5) for f in futures]
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json()["document"]["id"] == results[1].json()["document"]["id"]
    with admin() as db:
        assert (
            len(list(db.scalars(select(EmailEnvelope).where(EmailEnvelope.owner_id == uid)))) == 1
        )


@pytest.mark.parametrize("operation", ["read", "export", "replay"])
def test_expiry_after_actual_email_source_wait(scenario, monkeypatch, operation):
    client, h, _, admin, uid = scenario
    doc = ingest(client, h).json()["document"]
    with admin() as db:
        expiry = db.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == uid))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(
                select(DocumentRecord).where(DocumentRecord.id == UUID(doc["id"])).with_for_update()
            )
            pending = (
                pool.submit(ingest, client, h)
                if operation == "replay"
                else pool.submit(
                    mail_call,
                    client,
                    h,
                    doc,
                    operation,
                    **({"acknowledge_copy_limits": True} if operation == "export" else {}),
                )
            )
            wait_for_source_lock(admin)
            monkeypatch.setattr(
                identity, "now_utc", lambda: identity.aware(expiry) + timedelta(seconds=1)
            )
        assert pending.result(timeout=5).status_code == 401


def test_email_audit_failure_rolls_back_import_and_entire_forget(scenario, runtime_engine):
    client, h, _, admin, uid = scenario

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        assert ingest(client, h).status_code == 503
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert list(db.scalars(select(EmailEnvelope).where(EmailEnvelope.owner_id == uid))) == []
    doc = ingest(client, h).json()["document"]
    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        assert document_call(client, h, doc, "forget").status_code == 503
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert db.get(DocumentRecord, UUID(doc["id"])).state == "active"
        assert db.get(EmailEnvelope, UUID(doc["id"])).original_message == message()


def test_runtime_rejects_wrong_original_hash_on_initial_envelope(scenario, runtime_engine):
    from test_invoice_review import TEXT

    client, h, _, _, _ = scenario
    response = client.post(
        "/api/v1/documents",
        headers=h,
        json={
            "scope": "household_shared",
            "title": "Synthetic unlinked source",
            "source_reference": "Synthetic fixture",
            "filename": "synthetic-invoice.txt",
            "original_base64": base64.b64encode(TEXT.encode()).decode(),
        },
    )
    assert response.status_code == 201
    raw = message()
    with pytest.raises(DBAPIError), runtime_engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO email_envelopes(document_id,owner_id,scope_key,state,message_sha256,message_size,attachment_sha256,attachment_filename,original_message,created_at) SELECT id,owner_id,scope_key,'active',repeat('0',64),:size,sha256,filename,:raw,created_at FROM document_records WHERE id=:id"
            ),
            {"id": response.json()["id"], "raw": raw, "size": len(raw)},
        )
