"""MVP-01 synthetic invoice journey (spec 076): durable synthetic destination on PostgreSQL.

Real application paths and real operating-system worker processes against a disposable PostgreSQL
database and the opt-in durable synthetic ledger (``app.synthetic_ledger``). Everything is
synthetic; the ledger holds filing identity, logical path, SHA-256 and size and never the original
invoice bytes. No real filesystem destination, NAS, mailbox or network exists.

Acceptance mapping (spec 076 validation contract): AC3 forwarded twice without duplication, AC6
plan approval causes no effect, AC7 separate exact authorization and auditable history, AC8 worker
kill/restart without duplicate effect, AC9 failures before/after the effect and inconclusive
lookups, AC10 peer/stale/missing-acknowledgement/reused/concurrent/conflicting-destination
refusals. The browser-visible parts (AC1, AC2, AC4, AC5, AC11, AC12) are mapped in the spec and the
owner script tests. In-process application restarts are *not* host restart proof.
"""

import base64
import hashlib
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from conftest import SYNTHETIC_PASSWORD, client_for
from restart_support import Worker
from test_email_intake import ingest, mail_call
from test_filing import body
from test_filing_fence_postgres import FULL_HISTORY, age, due, snap
from test_filing_postgres import forget_owned_test_sources  # noqa: F401
from test_invoice_filing import approved, plan_call
from test_invoice_review import TEXT, confirm, source
from test_mvp03_journey_postgres import filings, journey_to_request, request, row_for

from app import filing_worker, synthetic_ledger
from app.config import settings
from app.manage import provision, set_scope
from app.models import DocumentRecord, EmailEnvelope, User
from app.synthetic_ledger import DurableSyntheticDestination

pytestmark = pytest.mark.integration
Root = namedtuple("Root", "root")


@pytest.fixture
def procs():
    started = []
    yield started
    for worker in started:
        worker.stop()


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    root = tmp_path / "synthetic-ledger"
    root.mkdir()
    synthetic_ledger.initialize(root)
    monkeypatch.setattr(settings, "filing_synthetic_ledger_directory", root)
    return root


def spawn(url, ledger, row, procs, crash_at=None):
    worker = Worker("filing_durable", url, Root(ledger), row.id, crash_at).start()
    procs.append(worker)
    return worker


def fresh(url, ledger, row, procs):
    return spawn(url, ledger, row, procs).finish()


def summary(ledger):
    return DurableSyntheticDestination(ledger).summary()


def url_of(runtime_engine):
    return runtime_engine.url.render_as_string(hide_password=False)


def test_forwarded_twice_approval_is_inert_then_separate_request_files_one_metadata_effect(
    scenario, runtime_engine, ledger, procs
):
    client, h, _, admin, _ = scenario
    maker, admin, raw, original, doc, receipt, path, row = journey_to_request(
        scenario, runtime_engine
    )
    # AC6: the approved plan alone caused no filing and no destination effect.
    assert summary(ledger)["effects"] == 0
    # AC7: the explicit request is replayed, never duplicated.
    again = request(client, h, doc, receipt)
    assert again.status_code == 200 and again.json()["replayed"] is True
    assert len(filings(admin, doc["id"])) == 1
    assert fresh(url_of(runtime_engine), ledger, row, procs) == "filed"
    state = summary(ledger)
    [entry] = state["items"]
    assert state["effects"] == 1 and entry["path"] == path
    assert entry["sha256"] == hashlib.sha256(original).hexdigest()
    assert entry["size"] == len(original) and entry["key"] == str(row.id)[:12]
    # Metadata only: no file in the ledger contains the original invoice or email bytes.
    blobs = [p.read_bytes() for p in ledger.rglob("*") if p.is_file()]
    assert blobs and not any(original in blob or raw in blob for blob in blobs)
    assert not any(base64.b64encode(original) in blob for blob in blobs)
    # AC3: one document, one envelope, original email lineage inspectable.
    with admin() as db:
        envelope = db.get(EmailEnvelope, doc["id"])
        source_row = db.get(DocumentRecord, doc["id"])
        assert envelope.original_message == raw and source_row.sha256 == entry["sha256"]
    assert (
        mail_call(client, h, doc, "read").json()["message_sha256"]
        == hashlib.sha256(raw).hexdigest()
    )
    third = ingest(client, h, raw, title="Replay after filing must not rename")
    assert third.status_code == 200 and third.json()["status"] == "replayed"
    # AC8: terminal stays terminal and repeated passes by fresh workers repeat nothing.
    assert fresh(url_of(runtime_engine), ledger, row, procs) == "skipped"
    assert filing_worker.run_once(DurableSyntheticDestination(ledger), maker)["checked"] == 0
    assert summary(ledger)["effects"] == 1
    page = client.post(
        "/api/v1/filing/history",
        headers=h,
        json={"scope": doc["scope"], "execution_id": str(row.id)},
    ).json()
    assert [e["operation"] for e in page["items"]] == ["requested", "attempted", "filed"]
    assert path not in str(page) and entry["sha256"] not in str(page)


def test_kill_after_the_effect_is_reconciled_by_a_fresh_process_without_a_second_effect(
    scenario, runtime_engine, ledger, procs
):
    _maker, admin, _raw, _original, _doc, _, _path, row = journey_to_request(
        scenario, runtime_engine
    )
    url = url_of(runtime_engine)
    worker = spawn(url, ledger, row, procs, "after_effect")
    assert worker.wait_reached() == "after_effect"
    worker.kill()
    assert summary(ledger)["effects"] == 1 and snap(admin, row)["in_flight"]
    assert fresh(url, ledger, row, procs) == "skipped"  # the dead claim is not stolen early
    age(admin, row)
    assert fresh(url, ledger, row, procs) == "unknown"
    due(admin, row)
    assert fresh(url, ledger, row, procs) == "filed"
    final = snap(admin, row)
    assert final["operations"] == ["requested", "attempted", "unknown", "reconciled"]
    state = summary(ledger)
    assert state["effects"] == 1 and state["calls"] == 1 and state["entries"] == 1


def test_kill_before_the_effect_with_an_inconclusive_lookup_stays_unknown_until_resolved(
    scenario, runtime_engine, ledger, procs
):
    _maker, admin, _raw, _original, _doc, _, _path, row = journey_to_request(
        scenario, runtime_engine
    )
    url = url_of(runtime_engine)
    worker = spawn(url, ledger, row, procs, "before_effect")
    assert worker.wait_reached() == "before_effect"
    worker.kill()
    assert summary(ledger)["effects"] == 0
    age(admin, row)
    assert fresh(url, ledger, row, procs) == "unknown"
    synthetic_ledger.main(["control", "lookup-unavailable", "on"])
    for _ in range(2):
        due(admin, row)
        assert fresh(url, ledger, row, procs) == "unknown"  # cannot tell absent from unreachable
        assert snap(admin, row)["reason"] == "ambiguous_outcome"
    assert summary(ledger)["calls"] == 1 and summary(ledger)["effects"] == 0
    synthetic_ledger.main(["control", "lookup-unavailable", "off"])
    due(admin, row)
    assert fresh(url, ledger, row, procs) == "retried"  # only a conclusive absence allows retry
    assert fresh(url, ledger, row, procs) == "filed"
    state = summary(ledger)
    assert state["effects"] == 1 and state["calls"] == 2


def test_timeout_after_the_effect_is_found_by_lookup_and_never_resent(
    scenario, runtime_engine, ledger
):
    maker, admin, _raw, _original, _doc, _, _path, row = journey_to_request(
        scenario, runtime_engine
    )
    synthetic_ledger.main(["control", "timeout-after-effect", "on"])
    destination = DurableSyntheticDestination(ledger)
    assert filing_worker.process(maker, row, destination) == "unknown"
    assert not (ledger / "control" / "timeout-after-effect").exists()  # one shot
    due(admin, row)
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "filed"
    state = summary(ledger)
    assert state["effects"] == 1 and state["calls"] == 1
    assert snap(admin, row)["operations"] == ["requested", "attempted", "unknown", "reconciled"]


def test_timeout_before_the_effect_retries_once_after_a_conclusive_absence(
    scenario, runtime_engine, ledger
):
    maker, admin, _raw, _original, _doc, _, _path, row = journey_to_request(
        scenario, runtime_engine
    )
    synthetic_ledger.main(["control", "timeout-before-effect", "on"])
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "unknown"
    assert summary(ledger)["effects"] == 0
    due(admin, row)
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "retried"
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "filed"
    state = summary(ledger)
    assert state["effects"] == 1 and state["calls"] == 2
    assert snap(admin, row)["operations"] == FULL_HISTORY


def test_a_conflicting_existing_destination_entry_is_never_overwritten(
    scenario, runtime_engine, ledger
):
    maker, admin, _raw, _original, _doc, _, path, row = journey_to_request(scenario, runtime_engine)
    DurableSyntheticDestination(ledger).put("e" * 64, path, "f" * 64, 3)
    before = summary(ledger)
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "failed"
    after = summary(ledger)
    assert after["items"] == before["items"] and after["effects"] == before["effects"]
    assert snap(admin, row)["reason"] == "collision"


def test_a_plan_changed_after_the_request_cancels_it_with_no_effect(
    scenario, runtime_engine, ledger
):
    client, h, _, admin, _ = scenario
    maker, admin, _raw, _original, doc, receipt, _path, row = journey_to_request(
        scenario, runtime_engine
    )
    changed = client.post(
        f"/api/v1/documents/{doc['id']}/correct",
        headers=h,
        json={
            "scope": doc["scope"],
            "expected_revision": doc["revision"],
            "title": "Source changed after the exact request",
            "source_reference": doc["source_reference"],
            "reviewed": True,
        },
    )
    assert changed.status_code == 200, changed.json()
    assert filing_worker.process(maker, row, DurableSyntheticDestination(ledger)) == "cancelled"
    assert summary(ledger)["effects"] == 0 and snap(admin, row)["reason"] == "plan_changed"
    stale = client.post("/api/v1/filing/request", headers=h, json=body(doc, receipt))
    assert stale.status_code == 409  # the old source revision cannot authorize anything


def test_a_revoked_scope_or_inactive_owner_cancels_without_effect(scenario, runtime_engine, ledger):
    _client, _h, _, admin, user_id = scenario
    maker, admin, _raw, _original, doc, _, _path, row = journey_to_request(scenario, runtime_engine)
    with admin.begin() as db:
        set_scope(db, db.get(User, user_id), doc["scope"], False)
    try:
        outcome = filing_worker.process(maker, row, DurableSyntheticDestination(ledger))
    finally:
        with admin.begin() as db:  # the shared cleanup fixture must be able to sign in again
            set_scope(db, db.get(User, user_id), doc["scope"], True)
    assert outcome == "cancelled"
    assert summary(ledger)["effects"] == 0 and snap(admin, row)["reason"] == "scope_unavailable"


def test_peer_stale_unapproved_unacknowledged_and_malicious_requests_fail_closed(
    scenario, runtime_engine, ledger
):
    client, h, _, admin, _ = scenario
    doc = source(client, h)
    plan = approved(client, h, doc, confirm(client, h, doc))
    peer_slug = "peer-" + uuid4().hex[:12]
    with admin.begin() as db:
        provision(db, peer_slug, "Synthetic peer", SYNTHETIC_PASSWORD, {doc["scope"]})
    runtime = type(admin)(bind=runtime_engine, expire_on_commit=False)
    with client_for(runtime) as peer:
        login = peer.post(
            "/api/v1/auth/login", json={"slug": peer_slug, "password": SYNTHETIC_PASSWORD}
        )
        assert login.status_code == 200
        ph = {"X-CSRF-Token": login.json()["csrf_token"]}
        denied = peer.post("/api/v1/filing/request", headers=ph, json=body(doc, plan))
        assert denied.status_code in {403, 404}
    assert filings(admin, doc["id"]) == []
    stale = client.post(
        "/api/v1/filing/request",
        headers=h,
        json=body(doc, plan, expected_document_revision=doc["revision"] + 1),
    )
    assert stale.status_code == 409
    for flag in ("acknowledge_synthetic_destination", "acknowledge_exact_plan"):
        assert (
            client.post(
                "/api/v1/filing/request", headers=h, json=body(doc, plan, **{flag: False})
            ).status_code
            == 422
        )
    other = source(client, h, TEXT + "\nSynthetic unapproved " + uuid4().hex)
    unapproved = client.post(
        "/api/v1/filing/request",
        headers=h,
        json=body(other, {"review_revision": 1}),
    )
    assert unapproved.status_code == 409
    for folder, name in (
        ("invoices/../etc", "a.txt"),
        ("/invoices/x", "a.txt"),
        ("invoices/x", "../a.txt"),
    ):
        bad = plan_call(client, h, doc, "plan", plan, folder=folder, filename=name)
        assert bad.status_code == 422
    assert filings(admin, doc["id"]) == [] and summary(ledger)["effects"] == 0


def test_concurrent_exact_requests_create_one_filing_and_one_effect(
    scenario, runtime_engine, ledger
):
    client, h, _, admin, _ = scenario
    doc = source(client, h)
    plan = approved(client, h, doc, confirm(client, h, doc))
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = sorted(
            r.status_code
            for r in pool.map(
                lambda _: client.post("/api/v1/filing/request", headers=h, json=body(doc, plan)),
                range(4),
            )
        )
    assert codes.count(201) == 1 and set(codes) <= {200, 201, 409}
    [row] = filings(admin, doc["id"])
    maker = type(admin)(bind=runtime_engine, expire_on_commit=False)
    candidate = row_for(admin, doc["id"])
    destination = DurableSyntheticDestination(ledger)
    assert filing_worker.process(maker, candidate, destination) == "filed"
    assert summary(ledger)["effects"] == 1 and row.destination == "synthetic"
