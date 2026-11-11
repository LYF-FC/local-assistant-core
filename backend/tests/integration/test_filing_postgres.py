"""Restricted synthetic filing: single claims, sealed history, destination uniqueness, scrubbing."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import SYNTHETIC_PASSWORD
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from test_documents import call as document_call
from test_filing import body
from test_invoice_filing import approved, plan_call
from test_invoice_review import TEXT, confirm, source
from test_invoice_review import call as invoice_call

from app import filing, filing_worker, identity
from app.models import DocumentRecord, FilingExecution, FilingExecutionEvent, User

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def forget_owned_test_sources(scenario):
    # Sealed history is retained; only shared source text is forgotten after each test.
    yield
    client, _, _, admin, uid = scenario
    with admin() as db:
        slug = db.get(User, uid).slug
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


def approved_source(scenario, suffix=None):
    client, h, _, _, _ = scenario
    doc = source(client, h, TEXT + "\nSynthetic SQL fixture " + (suffix or uuid4().hex))
    receipt = approved(client, h, doc, confirm(client, h, doc))
    return doc, receipt, receipt["review"]["data"]["filing_plan"]["relative_path"]


def manual_source(scenario, filename):
    client, h, _, _, _ = scenario
    doc = source(client, h, TEXT + "\nSynthetic SQL fixture " + uuid4().hex)
    reviewed = confirm(client, h, doc)
    planned = plan_call(
        client, h, doc, "plan", reviewed, folder="invoices/manual", filename=filename
    ).json()
    receipt = plan_call(
        client,
        h,
        doc,
        "approve_plan",
        planned,
        acknowledge_plan_only=True,
        acknowledge_duplicate_limits=True,
    ).json()
    return doc, receipt, receipt["review"]["data"]["filing_plan"]["relative_path"]


def requested(scenario, runtime_engine):
    client, h, _, admin, _ = scenario
    doc, receipt, path = approved_source(scenario)
    response = client.post("/api/v1/filing/request", headers=h, json=body(doc, receipt))
    assert response.status_code == 201, response.json()
    execution = response.json()["filing"]
    with admin() as db:
        row = db.execute(
            select(
                FilingExecution.id,
                FilingExecution.owner_id,
                FilingExecution.scope_key,
                FilingExecution.document_id,
            ).where(FilingExecution.id == execution["id"])
        ).one()
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    return maker, admin, doc, receipt, path, row


def test_runtime_files_once_and_records_sealed_history(scenario, runtime_engine):
    maker, admin, _, _, path, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    assert filing_worker.process(maker, row, destination) == "filed"
    assert filing_worker.process(maker, row, destination) == "skipped"
    assert destination.writes == 1 and list(destination.files) == [path]
    with admin() as db:
        events = db.scalars(
            select(FilingExecutionEvent)
            .where(FilingExecutionEvent.execution_id == row.id)
            .order_by(FilingExecutionEvent.revision)
        ).all()
    assert [e.operation for e in events] == ["requested", "attempted", "filed"]
    assert events[0].actor_id == row.owner_id and events[1].actor_id is None
    assert path not in str([e.snapshot for e in events])


def test_concurrent_workers_file_a_plan_once(scenario, runtime_engine):
    maker, _, _, _, _, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: filing_worker.process(maker, row, destination), range(2)))
    assert sorted(results) == ["filed", "skipped"]
    assert destination.writes == 1


def test_claim_commits_before_the_effect_so_a_crash_never_refiles(scenario, runtime_engine):
    maker, admin, _, _, _, row = requested(scenario, runtime_engine)

    class Crash(filing.SyntheticDestination):
        def put(self, key, path, sha256, size):
            with admin() as db:  # the claim is already visible to another connection
                state = db.get(FilingExecution, row.id)
                assert state.attempts == 1 and state.attempt_started_at is not None
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        filing_worker.process(maker, row, Crash())
    destination = filing.SyntheticDestination()
    assert filing_worker.process(maker, row, destination) == "skipped"
    with admin.begin() as db:
        state = db.get(FilingExecution, row.id)
        # Age the claim beyond the in-flight deadline: it must turn unknown, never re-apply.
        db.execute(text("ALTER TABLE filing_executions DISABLE TRIGGER butler_filing_guard"))
        state.attempt_started_at = (
            identity.now_utc() - filing.IN_FLIGHT_DEADLINE - timedelta(seconds=1)
        )
        db.flush()
        db.execute(text("ALTER TABLE filing_executions ENABLE TRIGGER butler_filing_guard"))
    assert filing_worker.process(maker, row, destination) == "unknown"
    assert destination.writes == 0
    with admin.begin() as db:
        db.execute(text("ALTER TABLE filing_executions DISABLE TRIGGER butler_filing_guard"))
        db.get(FilingExecution, row.id).next_attempt_at = identity.now_utc()
        db.flush()
        db.execute(text("ALTER TABLE filing_executions ENABLE TRIGGER butler_filing_guard"))
    assert filing_worker.process(maker, row, destination) == "retried"
    assert filing_worker.process(maker, row, destination) == "filed"
    assert destination.writes == 1


def test_timeout_applied_reconciles_to_filed_without_a_second_write(scenario, runtime_engine):
    maker, admin, _, _, path, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination({path: ["timeout_applied"]})
    assert filing_worker.process(maker, row, destination) == "unknown"
    with admin.begin() as db:
        db.execute(text("ALTER TABLE filing_executions DISABLE TRIGGER butler_filing_guard"))
        db.get(FilingExecution, row.id).next_attempt_at = identity.now_utc()
        db.flush()
        db.execute(text("ALTER TABLE filing_executions ENABLE TRIGGER butler_filing_guard"))
    assert filing_worker.process(maker, row, destination) == "filed"
    assert destination.writes == 1
    with admin() as db:
        ops = db.scalars(
            select(FilingExecutionEvent.operation)
            .where(FilingExecutionEvent.execution_id == row.id)
            .order_by(FilingExecutionEvent.revision)
        ).all()
    assert ops == ["requested", "attempted", "unknown", "reconciled"]


def test_same_manual_destination_cannot_be_requested_twice(scenario, runtime_engine):
    client, h, _, _, _ = scenario
    name = "synthetic-" + uuid4().hex[:8] + ".txt"
    first, first_receipt, _ = manual_source(scenario, name)
    second, second_receipt, _ = manual_source(scenario, name)
    created = client.post("/api/v1/filing/request", headers=h, json=body(first, first_receipt))
    assert created.status_code == 201
    refused = client.post("/api/v1/filing/request", headers=h, json=body(second, second_receipt))
    assert refused.status_code == 409


def test_active_destination_unique_index_refuses_a_raw_duplicate(scenario, runtime_engine):
    maker, admin, doc, _, path, _ = requested(scenario, runtime_engine)
    other, other_receipt, _ = approved_source(scenario)
    key = filing.destination_key(doc["scope"], path)
    with admin() as db:
        other_row = db.execute(
            text("SELECT d.owner_id FROM document_records d WHERE d.id=:id"),
            {"id": other["id"]},
        ).one()
    with admin.begin() as db:
        # Point the second approved plan at the first one's path so the seal accepts the shape.
        db.execute(text("ALTER TABLE invoice_reviews DISABLE TRIGGER USER"))
        db.execute(
            text(
                "UPDATE invoice_reviews SET data=jsonb_set(data,'{filing_plan,relative_path}',"
                "to_jsonb(CAST(:path AS text))) WHERE document_id=:id"
            ),
            {"path": path, "id": other["id"]},
        )
        db.execute(text("ALTER TABLE invoice_reviews ENABLE TRIGGER USER"))
    insert = (
        "INSERT INTO filing_executions(id,document_id,owner_id,scope_key,plan_revision,"
        "source_revision,destination_key,destination,revision,state,attempts,next_attempt_at,"
        "created_at,updated_at) VALUES(:new,:doc,:owner,:scope,:plan,:src,:key,'synthetic',1,"
        "'pending',0,now(),now(),now())"
    )
    values = {
        "new": uuid4(),
        "doc": other["id"],
        "owner": other_row.owner_id,
        "scope": other["scope"],
        "plan": other_receipt["review_revision"],
        "src": other["revision"],
        "key": key,
    }
    with maker.begin() as db, pytest.raises(DBAPIError) as refused:
        db.execute(text(insert), values)
    assert "uq_filing_destination_active" in str(refused.value)


MUTATIONS = [
    "owner_id=:other,revision=revision+1",
    "scope_key='member_a_private',revision=revision+1",
    "document_id=:other,revision=revision+1",
    "plan_revision=plan_revision+1,revision=revision+1",
    "source_revision=source_revision+1,revision=revision+1",
    "destination='other',revision=revision+1",
    "destination_key=repeat('a',64),revision=revision+1",
    "destination_key=NULL,revision=revision+1",
    "created_at=created_at+interval '1s',revision=revision+1",
    "revision=revision+2",
    "attempts=attempts+2,revision=revision+1",
    "attempts=4,revision=revision+1",
    "state='filed',next_attempt_at=NULL,resolved_at=updated_at+interval '1s',revision=revision+1",
    "state='failed',next_attempt_at=NULL,resolved_at=updated_at,reason=NULL,revision=revision+1",
    "state='cancelled',next_attempt_at=NULL,resolved_at=updated_at,reason=NULL,revision=revision+1",
    "state='filed',next_attempt_at=NULL,resolved_at=updated_at,reason='collision',revision=revision+1",
]


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_raw_state_identity_destination_and_revision_guards(scenario, runtime_engine, mutation):
    _, _, _, _, _, row = requested(scenario, runtime_engine)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(f"UPDATE filing_executions SET {mutation} WHERE id=:id"),
            {"id": row.id, "other": uuid4()},
        )


UNCLAIMED = [
    "state='filed',next_attempt_at=NULL,resolved_at=updated_at,revision=revision+1",
    (
        "state='failed',reason='attempts_exhausted',next_attempt_at=NULL,"
        "resolved_at=updated_at,revision=revision+1"
    ),
    (
        "state='unknown',reason='ambiguous_outcome',"
        "next_attempt_at=updated_at+interval '1 minute',revision=revision+1"
    ),
]


@pytest.mark.parametrize("mutation", UNCLAIMED)
def test_a_filing_that_was_never_claimed_cannot_be_marked_filed_failed_or_unknown(
    scenario, runtime_engine, mutation
):
    _, _, _, admin, _ = scenario
    _, _, _, _, _, row = requested(scenario, runtime_engine)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError) as refused:
        db.execute(text(f"UPDATE filing_executions SET {mutation} WHERE id=:id"), {"id": row.id})
    assert "Invalid filing transition" in str(refused.value)
    with admin() as db:
        state = db.get(FilingExecution, row.id)
        assert state.state == "pending" and state.attempts == 0
        assert state.authorization_consumed_at is None


def test_terminal_state_cannot_be_revived(scenario, runtime_engine):
    maker, _, _, _, _, row = requested(scenario, runtime_engine)
    assert filing_worker.process(maker, row, filing.SyntheticDestination()) == "filed"
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "UPDATE filing_executions SET state='pending',next_attempt_at=now(),"
                "resolved_at=NULL,revision=revision+1 WHERE id=:id"
            ),
            {"id": row.id},
        )


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM filing_executions WHERE id=:id",
        "TRUNCATE filing_executions CASCADE",
        "UPDATE filing_execution_events SET snapshot='{}' WHERE execution_id=:id",
        "DELETE FROM filing_execution_events WHERE execution_id=:id",
        "TRUNCATE filing_execution_events",
        "SELECT metadata_json FROM audit_events",
    ],
)
def test_runtime_history_and_least_privilege(scenario, runtime_engine, statement):
    _, _, _, _, _, row = requested(scenario, runtime_engine)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(statement), {"id": row.id})


def insert_values(doc, receipt, path, **changes):
    values = {
        "new": uuid4(),
        "doc": doc["id"],
        "owner": None,
        "scope": doc["scope"],
        "plan": receipt["review_revision"],
        "src": doc["revision"],
        "key": filing.destination_key(doc["scope"], path),
        "revision": 1,
        "state": "pending",
        "attempts": 0,
        **changes,
    }
    return values


INSERT = (
    "INSERT INTO filing_executions(id,document_id,owner_id,scope_key,plan_revision,"
    "source_revision,destination_key,destination,revision,state,attempts,next_attempt_at,"
    "created_at,updated_at) VALUES(:new,:doc,:owner,:scope,:plan,:src,:key,'synthetic',"
    ":revision,:state,:attempts,now(),now(),now())"
)


@pytest.mark.parametrize(
    "changes",
    [
        {"plan": 1},
        {"src": 9},
        {"key": "b" * 64},
        {"revision": 2},
        {"state": "filed"},
        {"attempts": 1},
        {"scope": "member_a_private"},
    ],
)
def test_insert_requires_the_exact_current_approved_plan(scenario, runtime_engine, changes):
    _, _, uid = scenario[0], scenario[1], scenario[4]
    doc, receipt, path = approved_source(scenario)
    values = insert_values(doc, receipt, path, owner=uid, **changes)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(INSERT), values)


def test_insert_for_an_unapproved_plan_is_refused_and_honest_insert_is_accepted(
    scenario, runtime_engine
):
    client, h, _, admin, uid = scenario
    doc = source(client, h, TEXT + "\nSynthetic SQL fixture " + uuid4().hex)
    reviewed = confirm(client, h, doc)
    values = insert_values(doc, reviewed, "invoices/none.txt", owner=uid)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(INSERT), values)
    ready, receipt, path = approved_source(scenario)
    honest = insert_values(ready, receipt, path, owner=uid)
    with runtime_engine.begin() as db:
        db.execute(text(INSERT), honest)
    with admin() as db:
        assert db.get(FilingExecution, honest["new"]).state == "pending"


def forged_event(runtime_engine, row, mutate):
    """Advance a filing one valid step, then record history with a tampered snapshot."""
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with maker.begin() as db:
        state = db.get(FilingExecution, row.id)
        now = identity.now_utc()
        state.attempts += 1
        state.attempt_started_at = now
        state.authorization_consumed_at = now
        state.revision += 1
        state.updated_at = now
        db.flush()
        snapshot = filing.document(state)
        mutate(snapshot)
        db.add(
            FilingExecutionEvent(
                execution_id=state.id,
                owner_id=state.owner_id,
                revision=state.revision,
                operation="attempted",
                recorded_at=state.updated_at,
                snapshot=snapshot,
            )
        )
        db.flush()


FORGERIES = {
    "destination": lambda s: s.update(destination="other"),
    "document_id": lambda s: s.update(document_id=str(uuid4())),
    "plan_revision": lambda s: s.update(plan_revision=s["plan_revision"] + 1),
    "source_revision": lambda s: s.update(source_revision=s["source_revision"] + 1),
    "next_attempt_at": lambda s: s.update(next_attempt_at="2099-01-01T00:00:00+00:00"),
    "next_attempt_at_hidden": lambda s: s.update(next_attempt_at=None),
    "resolved_at": lambda s: s.update(resolved_at="2026-01-01T00:00:00+00:00"),
    "created_at": lambda s: s.update(created_at="2001-01-01T00:00:00+00:00"),
    "updated_at": lambda s: s.update(updated_at="2001-01-01T00:00:00+00:00"),
    "updated_at_offset": lambda s: s.update(updated_at=s["updated_at"].replace("+00:00", "+02:00")),
    "state": lambda s: s.update(state="filed"),
    "missing_destination": lambda s: s.pop("destination"),
    "missing_source_revision": lambda s: s.pop("source_revision"),
    "missing_resolved_at": lambda s: s.pop("resolved_at"),
    "revision_as_string": lambda s: s.update(revision=str(s["revision"])),
    "attempts_as_string": lambda s: s.update(attempts=str(s["attempts"])),
    "timestamp_as_number": lambda s: s.update(created_at=1),
    "extra_key": lambda s: s.update(relative_path="invoices/leaked.txt"),
}


@pytest.mark.parametrize("forgery", sorted(FORGERIES))
def test_history_snapshot_must_match_every_parent_field(scenario, runtime_engine, forgery):
    _, _, _, _, _, row = requested(scenario, runtime_engine)
    with pytest.raises(DBAPIError) as refused:
        forged_event(runtime_engine, row, FORGERIES[forgery])
    assert "Filing history mismatch" in str(refused.value)
    with sessionmaker(bind=runtime_engine)() as db:
        state = db.get(FilingExecution, row.id)
        assert state.revision == 1 and state.attempts == 0


def test_honest_snapshot_is_accepted_and_history_stays_append_only(scenario, runtime_engine):
    _, admin, _, _, _, row = requested(scenario, runtime_engine)
    forged_event(runtime_engine, row, lambda s: None)
    with admin() as db:
        ops = db.scalars(
            select(FilingExecutionEvent.operation)
            .where(FilingExecutionEvent.execution_id == row.id)
            .order_by(FilingExecutionEvent.revision)
        ).all()
    assert ops == ["requested", "attempted"]
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text("UPDATE filing_execution_events SET snapshot='{}' WHERE execution_id=:id"),
            {"id": row.id},
        )


def test_forgetting_cancels_pending_and_scrubs_finished_destination_keys(scenario, runtime_engine):
    client, h, _, admin, _ = scenario
    maker, _, done, _, _, finished = requested(scenario, runtime_engine)
    assert filing_worker.process(maker, finished, filing.SyntheticDestination()) == "filed"
    _, _, waiting, _, _, pending = requested(scenario, runtime_engine)
    assert document_call(client, h, done, "forget").status_code == 200
    assert document_call(client, h, waiting, "forget").status_code == 200
    with admin() as db:
        done_row = db.get(FilingExecution, finished.id)
        wait_row = db.get(FilingExecution, pending.id)
        assert done_row.state == "filed" and done_row.destination_key is None
        assert wait_row.state == "cancelled" and wait_row.reason == "source_changed"
        assert wait_row.destination_key is None
        done_ops = db.scalars(
            select(FilingExecutionEvent.operation)
            .where(FilingExecutionEvent.execution_id == finished.id)
            .order_by(FilingExecutionEvent.revision)
        ).all()
    assert done_ops[-1] == "scrubbed"
    destination = filing.SyntheticDestination()
    assert filing_worker.process(maker, pending, destination) == "skipped"
    assert destination.writes == 0


def age_claim_and_make_due(admin, row_id, *, claim=False):
    """Move an in-flight claim past its deadline (or a retry to due) with the seal briefly off."""
    with admin.begin() as db:
        db.execute(text("ALTER TABLE filing_executions DISABLE TRIGGER butler_filing_guard"))
        state = db.get(FilingExecution, row_id)
        if claim:
            state.attempt_started_at = (
                identity.now_utc() - filing.IN_FLIGHT_DEADLINE - timedelta(seconds=1)
            )
        else:
            state.next_attempt_at = identity.now_utc()
        db.flush()
        db.execute(text("ALTER TABLE filing_executions ENABLE TRIGGER butler_filing_guard"))


def test_a_crash_after_the_synthetic_write_but_before_recording_it_is_recovered_by_lookup(
    scenario, runtime_engine
):
    maker, admin, _, _, path, row = requested(scenario, runtime_engine)

    class CrashAfterWrite(filing.SyntheticDestination):
        def put(self, key, path, sha256, size):
            super().put(key, path, sha256, size)
            raise KeyboardInterrupt  # the effect is applied; the process dies before recording it

    destination = CrashAfterWrite()
    with pytest.raises(KeyboardInterrupt):
        filing_worker.process(maker, row, destination)
    assert destination.writes == 1 and list(destination.files) == [path]
    with admin() as db:
        state = db.get(FilingExecution, row.id)
        assert state.state == "pending" and state.attempt_started_at is not None
    assert filing_worker.process(maker, row, destination) == "skipped"
    age_claim_and_make_due(admin, row.id, claim=True)
    assert filing_worker.process(maker, row, destination) == "unknown"
    age_claim_and_make_due(admin, row.id)
    destination.lookup_available = False
    assert filing_worker.process(maker, row, destination) == "unknown"
    assert destination.writes == 1  # an unknown outcome is reconciled, never retried blindly
    age_claim_and_make_due(admin, row.id)
    destination.lookup_available = True
    assert filing_worker.process(maker, row, destination) == "filed"
    assert destination.writes == 1
    with admin() as db:
        ops = db.scalars(
            select(FilingExecutionEvent.operation)
            .where(FilingExecutionEvent.execution_id == row.id)
            .order_by(FilingExecutionEvent.revision)
        ).all()
        assert db.get(FilingExecution, row.id).attempts == 1
    assert ops == ["requested", "attempted", "unknown", "unknown", "reconciled"]


def test_lost_write_is_retried_only_after_lookup_proves_it_absent(scenario, runtime_engine):
    maker, admin, _, _, path, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination({path: ["timeout_lost"]})
    assert filing_worker.process(maker, row, destination) == "unknown"
    assert destination.writes == 1 and destination.files == {}
    age_claim_and_make_due(admin, row.id)
    assert filing_worker.process(maker, row, destination) == "retried"
    assert destination.writes == 1
    assert filing_worker.process(maker, row, destination) == "filed"
    assert destination.writes == 2 and list(destination.files) == [path]


def share_path(admin, other, path):
    """Point a second approved plan at an already requested destination."""
    with admin.begin() as db:
        db.execute(text("ALTER TABLE invoice_reviews DISABLE TRIGGER USER"))
        db.execute(
            text(
                "UPDATE invoice_reviews SET data=jsonb_set(data,'{filing_plan,relative_path}',"
                "to_jsonb(CAST(:path AS text))) WHERE document_id=:id"
            ),
            {"path": path, "id": other["id"]},
        )
        db.execute(text("ALTER TABLE invoice_reviews ENABLE TRIGGER USER"))


def test_concurrent_requests_cannot_reserve_the_same_active_destination(scenario, runtime_engine):
    import threading
    import time

    _, _, uid, admin = scenario[0], scenario[1], scenario[4], scenario[3]
    first, first_receipt, path = approved_source(scenario)
    second, second_receipt, _ = approved_source(scenario)
    share_path(admin, second, path)
    reserved = threading.Event()
    results = {}

    def contender(name, doc, receipt, hold):
        values = insert_values(doc, receipt, path, owner=uid)
        try:
            with runtime_engine.begin() as db:
                db.execute(text(INSERT), values)
                if hold:
                    reserved.set()
                    time.sleep(0.6)  # keep the reservation uncommitted while the rival tries
                else:
                    reserved.wait(5)
            results[name] = "reserved"
        except DBAPIError as exc:
            results[name] = "refused" if "uq_filing_destination_active" in str(exc) else str(exc)

    one = threading.Thread(target=contender, args=("one", first, first_receipt, True))
    two = threading.Thread(target=contender, args=("two", second, second_receipt, False))
    one.start()
    reserved.wait(5)
    two.start()
    one.join(10)
    two.join(10)
    assert sorted(results.values()) == ["refused", "reserved"], results
    with admin() as db:
        count = db.scalar(
            text(
                "SELECT count(*) FROM filing_executions WHERE destination_key=:k AND state='pending'"
            ),
            {"k": filing.destination_key(first["scope"], path)},
        )
    assert count == 1


def test_authorization_consumption_is_sealed_in_the_database(scenario, runtime_engine):
    maker, _, _, _, _, row = requested(scenario, runtime_engine)
    claim = (
        "UPDATE filing_executions SET attempts=1,attempt_started_at=now(),"
        "authorization_consumed_at={consumed},revision=revision+1,updated_at=now() WHERE id=:id"
    )
    for consumed in ("NULL", "now()-interval '1 day'"):
        with runtime_engine.begin() as db, pytest.raises(DBAPIError):
            db.execute(text(claim.format(consumed=consumed)), {"id": row.id})
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "UPDATE filing_executions SET authorization_consumed_at=now(),"
                "revision=revision+1,updated_at=now() WHERE id=:id"
            ),
            {"id": row.id},
        )
    # The honest claim consumes it atomically; afterwards it can be neither cleared nor moved.
    destination = filing.SyntheticDestination({"x": []})
    assert filing_worker.process(maker, row, destination) == "filed"
    for statement in (
        (
            "UPDATE filing_executions SET authorization_consumed_at=NULL,revision=revision+1,"
            "updated_at=now() WHERE id=:id"
        ),
        (
            "UPDATE filing_executions SET authorization_consumed_at=now(),revision=revision+1,"
            "updated_at=now() WHERE id=:id"
        ),
    ):
        with runtime_engine.begin() as db, pytest.raises(DBAPIError):
            db.execute(text(statement), {"id": row.id})


def test_authorization_is_bound_to_the_exact_owner_and_scope(scenario, runtime_engine):
    _, _, _, admin, uid = scenario
    doc, receipt, path = approved_source(scenario)
    with admin.begin() as db:
        from app.manage import provision

        stranger = provision(
            db,
            "synthetic-" + uuid4().hex,
            "Synthetic Stranger",
            SYNTHETIC_PASSWORD,
            {"household_shared"},
        ).id
    for changes in ({"owner": stranger}, {"scope": "member_b_private"}):
        values = insert_values(doc, receipt, path, **{"owner": uid, **changes})
        with runtime_engine.begin() as db, pytest.raises(DBAPIError):
            db.execute(text(INSERT), values)
    honest = insert_values(doc, receipt, path, owner=uid)
    with runtime_engine.begin() as db:
        db.execute(text(INSERT), honest)
    with admin() as db:
        assert db.get(FilingExecution, honest["new"]).owner_id == uid


def event_nulls(admin, execution_id):
    with admin() as db:
        return db.execute(
            text(
                "SELECT count(*) FILTER (WHERE snapshot IS NULL), count(*) "
                "FROM filing_execution_events WHERE execution_id=:id"
            ),
            {"id": execution_id},
        ).one()


def test_forgetting_nulls_history_in_sql_scrubs_once_and_stays_append_only(
    scenario, runtime_engine
):
    client, h, _, admin, _ = scenario
    maker, _, doc, _, path, row = requested(scenario, runtime_engine)
    assert filing_worker.process(maker, row, filing.SyntheticDestination()) == "filed"
    # While the source is active the runtime cannot null, rewrite or hide history.
    for statement in (
        "UPDATE filing_execution_events SET snapshot=NULL WHERE execution_id=:id",
        (
            "UPDATE filing_executions SET scrubbed_at=now(),destination_key=NULL,"
            "revision=revision+1,updated_at=now() WHERE id=:id"
        ),
    ):
        with runtime_engine.begin() as db, pytest.raises(DBAPIError):
            db.execute(text(statement), {"id": row.id})
    assert document_call(client, h, doc, "forget").status_code == 200
    nulls, total = event_nulls(admin, row.id)
    assert nulls == total == 4
    with admin() as db:
        state = db.get(FilingExecution, row.id)
        revision = state.revision
        assert state.destination_key is None and state.scrubbed_at is not None
        text_dump = str(
            db.execute(
                text("SELECT to_jsonb(f)::text FROM filing_executions f WHERE id=:id"),
                {"id": row.id},
            ).all()
        )
    assert path not in text_dump and filing.destination_key(doc["scope"], path) not in text_dump
    # Idempotent; history rows can still not be altered, removed or re-filled afterwards.
    with maker.begin() as db:
        filing.scrub_for_document(db, state.document_id)
    assert event_nulls(admin, row.id) == (4, 4)
    with admin() as db:
        assert db.get(FilingExecution, row.id).revision == revision
    for statement in (
        "UPDATE filing_execution_events SET snapshot='{}' WHERE execution_id=:id",
        "UPDATE filing_execution_events SET operation='filed' WHERE execution_id=:id",
        "DELETE FROM filing_execution_events WHERE execution_id=:id",
        (
            "UPDATE filing_executions SET destination_key=repeat('a',64),revision=revision+1,"
            "updated_at=now() WHERE id=:id"
        ),
        (
            "UPDATE filing_executions SET scrubbed_at=NULL,revision=revision+1,"
            "updated_at=now() WHERE id=:id"
        ),
    ):
        with runtime_engine.begin() as db, pytest.raises(DBAPIError):
            db.execute(text(statement), {"id": row.id})


def test_forgetting_while_the_effect_is_in_flight_cannot_be_undone_by_the_worker(
    scenario, runtime_engine
):
    import threading

    client, h, _, admin, _ = scenario
    maker, _, doc, _, _, row = requested(scenario, runtime_engine)
    started, release = threading.Event(), threading.Event()
    outcome = {}

    class Parked(filing.SyntheticDestination):
        def put(self, key, path, sha256, size):
            started.set()
            release.wait(10)
            return super().put(key, path, sha256, size)

    destination = Parked()
    worker = threading.Thread(
        target=lambda: outcome.update(result=filing_worker.process(maker, row, destination))
    )
    worker.start()
    assert started.wait(10)
    assert document_call(client, h, doc, "forget").status_code == 200
    release.set()
    worker.join(10)
    assert outcome["result"] == "skipped"
    with admin() as db:
        state = db.get(FilingExecution, row.id)
        assert state.state == "cancelled" and state.reason == "source_changed"
        assert state.destination_key is None and state.scrubbed_at is not None
        ops = db.scalars(
            select(FilingExecutionEvent.operation)
            .where(FilingExecutionEvent.execution_id == row.id)
            .order_by(FilingExecutionEvent.revision)
        ).all()
    assert ops == ["requested", "attempted", "cancelled", "scrubbed"]
    assert event_nulls(admin, row.id) == (4, 4)
    # The worker recorded nothing about the late effect; nothing is left to find or reconcile.
    assert filing_worker.process(maker, row, destination) == "skipped"


def test_forgetting_an_unknown_outcome_stops_reconciliation(scenario, runtime_engine):
    client, h, _, admin, _ = scenario
    maker, _, doc, _, path, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination({path: ["timeout_applied"]})
    assert filing_worker.process(maker, row, destination) == "unknown"
    assert document_call(client, h, doc, "forget").status_code == 200
    assert filing_worker.process(maker, row, destination) == "skipped"
    with admin() as db:
        state = db.get(FilingExecution, row.id)
        assert state.state == "cancelled" and state.destination_key is None
    assert event_nulls(admin, row.id)[0] == event_nulls(admin, row.id)[1]


def test_forgetting_racing_a_claiming_worker_leaves_a_consistent_scrubbed_record(
    scenario, runtime_engine
):
    import threading

    client, h, _, admin, _ = scenario
    maker, _, doc, _, _, row = requested(scenario, runtime_engine)
    barrier = threading.Barrier(2)
    outcome = {}

    def work():
        barrier.wait(5)
        try:
            outcome["worker"] = filing_worker.process(maker, row, filing.SyntheticDestination())
        except Exception as exc:  # noqa: BLE001 - recorded and asserted below
            outcome["worker"] = repr(exc)

    thread = threading.Thread(target=work)
    thread.start()
    barrier.wait(5)
    assert document_call(client, h, doc, "forget").status_code == 200
    thread.join(15)
    assert outcome["worker"] in {"filed", "skipped", "cancelled"}, outcome
    with admin() as db:
        state = db.get(FilingExecution, row.id)
        assert state.scrubbed_at is not None and state.destination_key is None
        assert state.state in {"filed", "cancelled"}
    nulls, total = event_nulls(admin, row.id)
    assert nulls == total


def test_forgetting_during_a_reconciliation_lookup_cannot_resurrect_the_filing(
    scenario, runtime_engine
):
    import threading

    client, h, _, admin, _ = scenario
    maker, _, doc, _, path, row = requested(scenario, runtime_engine)
    destination = filing.SyntheticDestination({path: ["timeout_applied"]})
    assert filing_worker.process(maker, row, destination) == "unknown"
    age_claim_and_make_due(admin, row.id)
    started, release = threading.Event(), threading.Event()
    outcome = {}

    class SlowLookup(filing.SyntheticDestination):
        def lookup(self, key):
            started.set()
            release.wait(10)
            return filing.Lookup.FILED

    slow = SlowLookup()
    worker = threading.Thread(
        target=lambda: outcome.update(result=filing_worker.process(maker, row, slow))
    )
    worker.start()
    assert started.wait(10)
    assert document_call(client, h, doc, "forget").status_code == 200
    release.set()
    worker.join(10)
    # The lookup said "filed", but the record was already forgotten: nothing is rewritten.
    assert outcome["result"] == "skipped"
    with admin() as db:
        state = db.get(FilingExecution, row.id)
        assert state.state == "cancelled" and state.destination_key is None
        assert state.scrubbed_at is not None
        ops = db.scalars(
            select(FilingExecutionEvent.operation)
            .where(FilingExecutionEvent.execution_id == row.id)
            .order_by(FilingExecutionEvent.revision)
        ).all()
    assert ops[-2:] == ["cancelled", "scrubbed"] and "reconciled" not in ops
    nulls, total = event_nulls(admin, row.id)
    assert nulls == total


def test_invoice_level_forgetting_scrubs_the_filing_on_postgres(scenario, runtime_engine):
    client, h, _, admin, _ = scenario
    maker, _, doc, receipt, _path, row = requested(scenario, runtime_engine)
    assert invoice_call(client, h, doc, "forget", receipt).status_code == 200
    with admin() as db:
        state = db.get(FilingExecution, row.id)
        assert state.state == "cancelled" and state.reason == "source_changed"
        assert state.destination_key is None and state.scrubbed_at is not None
    nulls, total = event_nulls(admin, row.id)
    assert nulls == total >= 2
    destination = filing.SyntheticDestination()
    assert filing_worker.process(maker, row, destination) == "skipped"
    assert destination.writes == 0


def test_the_reservation_unique_index_alone_turns_a_lost_race_into_a_conflict(
    scenario, runtime_engine, monkeypatch
):
    # A same-owner race is serialised by the owner row lock, so the application pre-check is
    # hidden here to prove the database refusal is translated to 409 and never a server error.
    client, h, _, _, _ = scenario
    name = "synthetic-" + uuid4().hex[:8] + ".txt"
    first, first_receipt, _ = manual_source(scenario, name)
    second, second_receipt, _ = manual_source(scenario, name)
    created = client.post("/api/v1/filing/request", headers=h, json=body(first, first_receipt))
    assert created.status_code == 201
    original = Session.scalar
    hidden = []

    def blind(self, statement, *args, **kwargs):
        text_ = str(statement)
        if "destination_key =" in text_ and "state IN" in text_:
            hidden.append(text_)
            return None
        return original(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "scalar", blind)
    refused = client.post("/api/v1/filing/request", headers=h, json=body(second, second_receipt))
    assert refused.status_code == 409, refused.text
    assert hidden, "the application pre-check was not intercepted, so the fallback was not proven"


def test_one_authorization_per_document_and_plan_revision_even_when_the_first_is_cancelled(
    scenario, runtime_engine
):
    client, h, uid, admin = scenario[0], scenario[1], scenario[4], scenario[3]
    _, _, doc, receipt, path, row = requested(scenario, runtime_engine)
    cancelled = client.post(
        "/api/v1/filing/cancel",
        headers=h,
        json={"scope": doc["scope"], "execution_id": str(row.id), "expected_revision": 1},
    )
    assert cancelled.status_code == 200
    # The cancelled row no longer holds the destination, so only the dedup constraint can refuse.
    with runtime_engine.begin() as db, pytest.raises(DBAPIError) as refused:
        db.execute(text(INSERT), insert_values(doc, receipt, path, owner=uid))
    assert "uq_filing_dedup" in str(refused.value)
    with admin() as db:
        assert (
            db.scalar(
                select(text("count(*)"))
                .select_from(FilingExecution)
                .where(FilingExecution.document_id == doc["id"])
            )
            == 1
        )


def test_no_event_can_be_inserted_after_scrubbing(scenario, runtime_engine):
    client, h, _, admin, _ = scenario
    maker, _, doc, _, _, row = requested(scenario, runtime_engine)
    assert filing_worker.process(maker, row, filing.SyntheticDestination()) == "filed"
    assert document_call(client, h, doc, "forget").status_code == 200
    with admin() as db:
        state = db.get(FilingExecution, row.id)
        revision, stamp, owner = state.revision, state.updated_at, state.owner_id
    event = {
        "execution_id": row.id,
        "owner_id": owner,
        "revision": revision,
        "recorded_at": stamp,
    }
    with maker.begin() as db:
        honest_snapshot = filing.document(db.get(FilingExecution, row.id))
    for operation, snapshot in (
        ("filed", honest_snapshot),
        ("filed", None),
        ("attempted", honest_snapshot),
    ):
        with maker.begin() as db, pytest.raises(DBAPIError) as refused:
            db.add(FilingExecutionEvent(operation=operation, snapshot=snapshot, **event))
            db.flush()
        assert "Filing history mismatch" in str(refused.value)
    # A repeated scrub marker at the same revision is refused by the history key.
    with maker.begin() as db, pytest.raises(DBAPIError):
        db.add(FilingExecutionEvent(operation="scrubbed", snapshot=None, **event))
        db.flush()
    nulls, total = event_nulls(admin, row.id)
    assert nulls == total == 4


PARITY_VARIANTS = {
    "uppercase": lambda token: f"Invoices/Manual/{token.upper()}.TXT",
    "duplicate_separators": lambda token: f"invoices//manual///{token}.txt",
    "trailing_separator": lambda token: f"invoices/manual/{token}.txt/",
    "decomposed_unicode": lambda token: f"invoices/manual/cafe\u0301-{token}.txt",
    "precomposed_unicode": lambda token: f"invoices/manual/caf\u00e9-{token}.txt",
    "mixed": lambda token: f"Invoices//Manual/Cafe\u0301-{token.upper()}.TXT/",
}


@pytest.mark.parametrize("variant", sorted(PARITY_VARIANTS))
def test_python_and_postgresql_derive_the_same_destination_key(scenario, runtime_engine, variant):
    uid, admin = scenario[4], scenario[3]
    doc, receipt, _ = approved_source(scenario)
    raw = PARITY_VARIANTS[variant](uuid4().hex[:12])
    share_path(admin, doc, raw)
    key = filing.destination_key(doc["scope"], raw)
    with runtime_engine.begin() as db:
        db.execute(text(INSERT), insert_values(doc, receipt, raw, owner=uid))
    with admin() as db:
        stored = db.scalar(
            select(FilingExecution.destination_key).where(FilingExecution.document_id == doc["id"])
        )
    assert stored == key
    # A key derived from anything but the canonical form of the plan path is refused.
    other, other_receipt, _ = approved_source(scenario)
    share_path(admin, other, raw)
    raw_key = hashlib.sha256(f"{other['scope']}:{raw}".encode()).hexdigest()
    if raw_key != key:
        with runtime_engine.begin() as db, pytest.raises(DBAPIError) as refused:
            db.execute(
                text(INSERT), insert_values(other, other_receipt, raw, owner=uid, key=raw_key)
            )
        assert "Filing requires a current approved plan" in str(refused.value)
    # The honest key for the same path is refused only because the destination is already held.
    with runtime_engine.begin() as db, pytest.raises(DBAPIError) as held:
        db.execute(text(INSERT), insert_values(other, other_receipt, raw, owner=uid))
    assert "uq_filing_destination_active" in str(held.value)


def test_bounded_repeated_forgetting_races_neither_deadlock_nor_leave_residue(
    scenario, runtime_engine
):
    import threading
    import time

    client, h, _, admin, _ = scenario
    started = time.monotonic()
    for _ in range(6):
        maker, _, doc, _, _, row = requested(scenario, runtime_engine)
        barrier = threading.Barrier(2)
        outcome = {}
        destination = filing.SyntheticDestination()

        def work(maker=maker, row=row, barrier=barrier, outcome=outcome, destination=destination):
            barrier.wait(5)
            try:
                outcome["worker"] = filing_worker.process(maker, row, destination)
            except Exception as exc:  # noqa: BLE001 - recorded and asserted below
                outcome["worker"] = repr(exc)

        thread = threading.Thread(target=work)
        thread.start()
        barrier.wait(5)
        assert document_call(client, h, doc, "forget").status_code == 200
        thread.join(15)
        assert not thread.is_alive()
        assert outcome["worker"] in {"filed", "skipped", "cancelled"}, outcome
        assert destination.writes <= 1
        with admin() as db:
            state = db.get(FilingExecution, row.id)
            assert state.scrubbed_at is not None and state.destination_key is None
            assert state.state in {"filed", "cancelled"}
        nulls, total = event_nulls(admin, row.id)
        assert nulls == total
    assert time.monotonic() - started < 120


def test_bounded_repeated_contended_claims_file_exactly_once(scenario, runtime_engine):
    started = __import__("time").monotonic()
    for _ in range(6):
        maker, _, _, _, _, row = requested(scenario, runtime_engine)
        destination = filing.SyntheticDestination()

        def attempt(_, maker=maker, row=row, destination=destination):
            try:
                return filing_worker.process(maker, row, destination)
            except Exception as exc:  # noqa: BLE001 - recorded and asserted below
                return repr(exc)

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        assert results.count("filed") == 1, results
        assert set(results) <= {"filed", "skipped"}, results
        assert destination.writes == 1
    assert __import__("time").monotonic() - started < 120
