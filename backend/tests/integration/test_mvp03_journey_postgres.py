"""MVP-03 synthetic journey on PostgreSQL: forwarded email twice to a filed synthetic destination.

Real application paths only: the email-intake API, invoice preparation and review, the filing plan
and its approval, the explicit filing request and the restricted worker. Fixtures are synthetic
and no filesystem, mailbox or network is touched.

Limits, stated precisely. Job state lives in PostgreSQL and survives fresh sessions and new
connections. The synthetic destination is an in-process object: the crash tests model a worker
that died while the *destination* (an external system) survived, by reusing the same object. They
do not prove that a destination effect survives a process restart: an in-memory ledger cannot, and
real process-kill evidence belongs to a host procedure or a real-adapter acceptance.
"""

import base64
import hashlib
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from test_email_intake import ingest, mail_call, message
from test_filing import body
from test_filing_fence_postgres import age, claim, due, snap
from test_filing_postgres import forget_owned_test_sources  # noqa: F401
from test_invoice_filing import approved
from test_invoice_review import TEXT, confirm, prepare

from app import filing, filing_worker
from app.models import DocumentRecord, EmailEnvelope, FilingExecution

pytestmark = pytest.mark.integration


def forwarded(scenario):
    """The same synthetic invoice forwarded twice, then extracted, reviewed, planned, approved."""
    client, h, _, admin, _ = scenario
    original = TEXT.encode() + b"\nSynthetic MVP-03 journey " + uuid4().hex.encode()
    raw = message(original)
    first = ingest(client, h, raw)
    assert first.status_code == 201, first.json()
    second = ingest(client, h, raw, title="A replay must not rename or duplicate")
    assert second.status_code == 200 and second.json()["status"] == "replayed"
    doc = first.json()["document"]
    assert second.json()["document"] == doc
    with admin() as db:
        envelopes = db.scalars(
            select(EmailEnvelope).where(
                EmailEnvelope.message_sha256 == hashlib.sha256(raw).hexdigest()
            )
        ).all()
        # Replay protection: one envelope and one document for two identical forwards.
        assert [str(e.document_id) for e in envelopes] == [doc["id"]]
    doc = client.post(
        f"/api/v1/documents/{doc['id']}/correct",
        headers=h,
        json={
            "scope": doc["scope"],
            "expected_revision": doc["revision"],
            "title": doc["title"],
            "source_reference": doc["source_reference"],
            "reviewed": True,
        },
    ).json()
    candidates = prepare(client, h, doc)["review"]["data"]["candidates"]
    assert candidates["total"][0]["value"] == "123.45" and candidates["issuer"]
    receipt = approved(client, h, doc, confirm(client, h, doc))
    return raw, original, doc, receipt


def request(client, h, doc, receipt):
    return client.post("/api/v1/filing/request", headers=h, json=body(doc, receipt))


def row_for(admin, document_id):
    with admin() as db:
        return db.execute(
            select(
                FilingExecution.id,
                FilingExecution.owner_id,
                FilingExecution.scope_key,
                FilingExecution.document_id,
            ).where(FilingExecution.document_id == UUID(document_id))
        ).one()


def filings(admin, document_id):
    with admin() as db:
        return db.scalars(
            select(FilingExecution).where(FilingExecution.document_id == UUID(document_id))
        ).all()


def journey_to_request(scenario, runtime_engine):
    client, h, _, admin, _ = scenario
    raw, original, doc, receipt = forwarded(scenario)
    plan = receipt["review"]["data"]["filing_plan"]
    # The plan names a contained destination and is bound to the exact reviewed revision.
    assert plan["state"] == "approved" and plan["execution_authorized"] is False
    assert plan["approved_revision"] == receipt["review_revision"]
    assert plan["relative_path"].startswith("invoices/")
    assert filing.canonical_path(plan["relative_path"]) == plan["relative_path"]
    assert filings(admin, doc["id"]) == []  # approval alone starts nothing
    created = request(client, h, doc, receipt)
    assert created.status_code == 201, created.json()
    execution = created.json()["filing"]
    assert (
        execution["state"] == "pending" and execution["plan_revision"] == receipt["review_revision"]
    )
    assert execution["source_revision"] == doc["revision"]
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    return (
        maker,
        admin,
        raw,
        original,
        doc,
        receipt,
        plan["relative_path"],
        row_for(admin, doc["id"]),
    )


def assert_lineage(scenario, raw, original, doc, row, path, destination):
    """Email -> imported document -> filing execution -> destination entry."""
    client, h, _, admin, _ = scenario
    entry = destination.files[filing.canonical_path(path)]
    key, entry_sha256, entry_size = entry
    with admin() as db:
        execution = db.get(FilingExecution, row.id)
        source = db.get(DocumentRecord, execution.document_id)
        envelope = db.get(EmailEnvelope, execution.document_id)
        # The filing references the imported document, which resolves to the original email.
        assert str(execution.document_id) == doc["id"] and envelope is not None
        assert envelope.owner_id == execution.owner_id and envelope.scope_key == execution.scope_key
        assert envelope.message_sha256 == hashlib.sha256(raw).hexdigest()
        assert envelope.original_message == raw
        # The destination entry carries the source checksum and size of the original attachment...
        assert entry_sha256 == source.sha256 == envelope.attachment_sha256
        assert entry_sha256 == hashlib.sha256(original).hexdigest()
        assert entry_size == source.byte_size == len(original)
        # ...and corresponds to exactly this filing, keyed by the filing id.
        assert key == str(execution.id) == str(row.id)
        assert execution.source_revision == source.revision
    # The owner-facing API resolves the same lineage from the document id.
    provenance = mail_call(client, h, doc, "read").json()
    assert provenance["document_id"] == doc["id"] == str(execution.document_id)
    assert provenance["message_sha256"] == hashlib.sha256(raw).hexdigest()
    assert provenance["attachment_sha256"] == entry_sha256 and provenance["attachment_is_current"]
    page = client.post(
        "/api/v1/filing/query",
        headers=h,
        json={"scope": doc["scope"], "state": "filed", "document_id": doc["id"]},
    ).json()
    assert [(i["id"], i["document_id"]) for i in page["items"]] == [(str(row.id), doc["id"])]


def test_forwarded_invoice_twice_is_extracted_reviewed_filed_once_with_lineage(
    scenario, runtime_engine
):
    client, h, _, admin, _ = scenario
    maker, admin, raw, original, doc, receipt, path, row = journey_to_request(
        scenario, runtime_engine
    )
    # The explicit request is replayed, never duplicated.
    again = request(client, h, doc, receipt)
    assert again.status_code == 200 and again.json()["replayed"] is True
    assert len(filings(admin, doc["id"])) == 1
    destination = filing.SyntheticDestination()
    assert filing_worker.process(maker, row, destination) == "filed"
    state = filings(admin, doc["id"])[0]
    assert state.state == "filed" and state.attempts == 1 and state.authorization_consumed_at
    assert destination.writes == 1 and list(destination.files) == [path]
    assert_lineage(scenario, raw, original, doc, row, path, destination)
    # Forwarding the same email again after filing creates no document, filing or write.
    third = ingest(client, h, raw, title="Replay after filing")
    assert third.status_code == 200 and third.json()["status"] == "replayed"
    assert third.json()["document"]["id"] == doc["id"]
    assert len(filings(admin, doc["id"])) == 1
    assert request(client, h, doc, receipt).json()["replayed"] is True
    assert filing_worker.run_once(destination, maker)["checked"] == 0
    assert destination.writes == 1 and len(filings(admin, doc["id"])) == 1
    history = client.post(
        "/api/v1/filing/history",
        headers=h,
        json={"scope": doc["scope"], "execution_id": str(row.id)},
    ).json()
    assert [e["operation"] for e in history["items"]] == ["requested", "attempted", "filed"]
    assert path not in str(history) and base64.b64encode(raw).decode() not in str(history)


def fresh(runtime_engine):
    """A brand-new engine and connections, as a restarted worker process would open."""
    engine = create_engine(runtime_engine.url)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_failure_before_the_effect_recovers_by_lookup_then_files_once(scenario, runtime_engine):
    maker, admin, raw, original, doc, _, path, row = journey_to_request(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    # The worker committed its claim and died before calling the destination at all.
    assert claim(maker, row)[0] == "apply"
    assert destination.writes == 0 and snap(admin, row)["in_flight"]
    engine, recovered = fresh(runtime_engine)
    try:
        # While the claim may still be live, nothing is started.
        assert filing_worker.process(recovered, row, destination) == "skipped"
        age(admin, row)
        assert filing_worker.process(recovered, row, destination) == "unknown"
        assert destination.writes == 0
        due(admin, row)
        # Reconciliation (lookup says absent) comes before the single retry.
        assert filing_worker.process(recovered, row, destination) == "retried"
        assert destination.writes == 0
        assert filing_worker.process(recovered, row, destination) == "filed"
    finally:
        engine.dispose()
    assert destination.writes == 1
    final = snap(admin, row)
    assert final["operations"] == [
        "requested",
        "attempted",
        "unknown",
        "reconciled",
        "attempted",
        "filed",
    ]
    assert_lineage(scenario, raw, original, doc, row, path, destination)


def test_failure_during_the_effect_is_found_by_lookup_and_never_rewritten(scenario, runtime_engine):
    maker, admin, raw, original, doc, _, path, row = journey_to_request(scenario, runtime_engine)

    class Dies(filing.SyntheticDestination):
        def put(self, key, path, sha256, size):
            super().put(key, path, sha256, size)  # the effect lands...
            raise KeyboardInterrupt  # ...and the worker dies before learning of it

    destination = Dies()
    with pytest.raises(KeyboardInterrupt):
        filing_worker.process(maker, row, destination)
    assert destination.writes == 1 and snap(admin, row)["in_flight"]
    engine, recovered = fresh(runtime_engine)
    try:
        age(admin, row)
        assert filing_worker.process(recovered, row, destination) == "unknown"
        due(admin, row)
        assert filing_worker.process(recovered, row, destination) == "filed"
    finally:
        engine.dispose()
    assert destination.writes == 1  # reconciled by lookup; no second write
    assert snap(admin, row)["operations"] == ["requested", "attempted", "unknown", "reconciled"]
    assert_lineage(scenario, raw, original, doc, row, path, destination)


def test_effect_succeeds_but_recording_fails_is_reconciled_never_resent(
    scenario, runtime_engine, monkeypatch
):
    maker, admin, raw, original, doc, _, path, row = journey_to_request(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    real_finish = filing_worker.finish
    broken = []

    def finish_then_lose_connection(db, candidate, outcome, fence):
        if not broken:
            broken.append(outcome)
            raise OperationalError("UPDATE", {}, Exception("synthetic connection loss"))
        return real_finish(db, candidate, outcome, fence)

    monkeypatch.setattr(filing_worker, "finish", finish_then_lose_connection)
    result = filing_worker.run_once(destination, maker)
    assert result["errors"] == 1 and broken == [filing.Outcome.ACCEPTED]
    assert destination.writes == 1 and snap(admin, row)["in_flight"]
    monkeypatch.setattr(filing_worker, "finish", real_finish)
    assert filing_worker.run_once(destination, maker)["checked"] == 0  # claim still live
    engine, recovered = fresh(runtime_engine)
    try:
        age(admin, row)
        assert filing_worker.process(recovered, row, destination) == "unknown"
        due(admin, row)
        assert filing_worker.process(recovered, row, destination) == "filed"
    finally:
        engine.dispose()
    assert destination.writes == 1
    assert snap(admin, row)["operations"] == ["requested", "attempted", "unknown", "reconciled"]
    assert_lineage(scenario, raw, original, doc, row, path, destination)


def test_an_unknown_outcome_stays_visible_until_lookup_can_settle_it(scenario, runtime_engine):
    client, h, _, _, _ = scenario
    maker, admin, raw, original, doc, _, path, row = journey_to_request(scenario, runtime_engine)
    destination = filing.SyntheticDestination({path: ["timeout_applied"]}, lookup_available=False)
    assert filing_worker.process(maker, row, destination) == "unknown"
    for _ in range(2):  # the destination cannot be asked: the ambiguity is kept, not guessed
        due(admin, row)
        assert filing_worker.process(maker, row, destination) == "unknown"
        state = snap(admin, row)
        assert state["state"] == "unknown" and state["reason"] == "ambiguous_outcome"
    assert destination.writes == 1  # never resent while unknown
    page = client.post(
        "/api/v1/filing/query", headers=h, json={"scope": doc["scope"], "state": "unknown"}
    ).json()
    assert [(i["id"], i["state"], i["reason"]) for i in page["items"]] == [
        (str(row.id), "unknown", "ambiguous_outcome")
    ]
    # An unknown filing cannot be cancelled away; it must be reconciled.
    cancel = client.post(
        "/api/v1/filing/cancel",
        headers=h,
        json={
            "scope": doc["scope"],
            "execution_id": str(row.id),
            "expected_revision": state["revision"],
        },
    )
    assert cancel.status_code == 409
    destination.lookup_available = True
    due(admin, row)
    assert filing_worker.process(maker, row, destination) == "filed"
    assert destination.writes == 1
    assert_lineage(scenario, raw, original, doc, row, path, destination)


def test_an_existing_destination_fails_the_filing_without_overwriting(scenario, runtime_engine):
    maker, admin, _, _, _, _, path, row = journey_to_request(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    destination.files[filing.canonical_path(path)] = ("someone-else", "0" * 64, 1)
    assert filing_worker.process(maker, row, destination) == "failed"
    state = snap(admin, row)
    assert state["state"] == "failed" and state["reason"] == "collision"
    assert destination.files[filing.canonical_path(path)] == ("someone-else", "0" * 64, 1)
    assert destination.writes == 0


def test_job_state_is_in_postgres_and_visible_to_a_fresh_connection(scenario, runtime_engine):
    maker, _, _, _, _, _, _, row = journey_to_request(scenario, runtime_engine)
    assert claim(maker, row)[0] == "apply"
    engine, recovered = fresh(runtime_engine)
    try:
        with recovered() as db:
            seen = db.execute(
                text(
                    "SELECT state, attempts, attempt_started_at IS NOT NULL, "
                    "authorization_consumed_at IS NOT NULL FROM filing_executions WHERE id=:i"
                ),
                {"i": row.id},
            ).one()
        assert tuple(seen) == ("pending", 1, True, True)
    finally:
        engine.dispose()
