from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_approvals import signin
from test_documents import call as document_call
from test_invoice_filing import approved, plan_call
from test_invoice_review import TEXT, confirm, source

from app import filing, filing_worker, identity
from app.models import FilingExecution, FilingExecutionEvent


@pytest.fixture
def clock(monkeypatch):
    state = {"now": datetime(2026, 11, 8, 12, tzinfo=UTC)}
    monkeypatch.setattr(identity, "now_utc", lambda: state["now"])
    return state


def plan_ready(client, h, text=None):
    doc = source(client, h) if text is None else source(client, h, text)
    receipt = approved(client, h, doc, confirm(client, h, doc))
    return doc, receipt, receipt["review"]["data"]["filing_plan"]["relative_path"]


def body(doc, receipt, **changes):
    return {
        "scope": doc["scope"],
        "document_id": doc["id"],
        "expected_document_revision": doc["revision"],
        "expected_review_revision": receipt["review_revision"],
        "acknowledge_synthetic_destination": True,
        "acknowledge_exact_plan": True,
        **changes,
    }


def request(client, h, doc, receipt, **changes):
    return client.post("/api/v1/filing/request", headers=h, json=body(doc, receipt, **changes))


def filed(client, h, doc, receipt):
    r = request(client, h, doc, receipt)
    assert r.status_code == 201, r.json()
    return r.json()["filing"]


def rows(store):
    with store() as db:
        return list(db.scalars(select(FilingExecution).order_by(FilingExecution.id)))


def operations(store):
    with store() as db:
        return [
            e.operation
            for e in db.scalars(
                select(FilingExecutionEvent).order_by(
                    FilingExecutionEvent.recorded_at, FilingExecutionEvent.revision
                )
            )
        ]


def test_plan_approval_alone_never_files_and_request_is_the_exact_authorization(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    doc, receipt, path = plan_ready(auth_client, h)
    destination = filing.SyntheticDestination()
    assert filing_worker.run_once(destination, auth_store)["checked"] == 0
    assert destination.writes == 0 and rows(auth_store) == []
    created = filed(auth_client, h, doc, receipt)
    assert created["state"] == "pending" and created["revision"] == 1
    assert path not in str(created) and "relative_path" not in str(created)
    first = filing_worker.run_once(destination, auth_store)
    assert first["filed"] == 1 and destination.writes == 1
    assert list(destination.files) == [path]
    assert filing_worker.run_once(destination, auth_store)["checked"] == 0
    assert destination.writes == 1
    (row,) = rows(auth_store)
    assert row.state == "filed" and row.attempts == 1 and row.destination == "synthetic"
    assert row.destination_key == filing.destination_key(doc["scope"], path)
    assert operations(auth_store) == ["requested", "attempted", "filed"]


def test_request_is_replayed_not_duplicated_and_history_is_metadata_only(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    doc, receipt, path = plan_ready(auth_client, h)
    created = filed(auth_client, h, doc, receipt)
    again = request(auth_client, h, doc, receipt)
    assert again.status_code == 200 and again.json()["replayed"] is True
    assert again.json()["filing"]["id"] == created["id"] and len(rows(auth_store)) == 1
    filing_worker.run_once(filing.SyntheticDestination(), auth_store)
    page = auth_client.post(
        "/api/v1/filing/query", headers=h, json={"scope": doc["scope"], "state": "filed"}
    ).json()
    assert [i["state"] for i in page["items"]] == ["filed"]
    history = auth_client.post(
        "/api/v1/filing/history",
        headers=h,
        json={"scope": doc["scope"], "execution_id": created["id"]},
    ).json()
    assert [e["operation"] for e in history["items"]] == ["requested", "attempted", "filed"]
    for text in (str(page), str(history)):
        assert path not in text and "Synthetic Vendor" not in text and "INV-001" not in text


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"acknowledge_exact_plan": False}, 422),
        ({"acknowledge_synthetic_destination": 1}, 422),
        ({"expected_document_revision": 99}, 409),
        ({"expected_review_revision": 99}, 409),
    ],
)
def test_request_requires_explicit_acknowledgement_and_exact_revisions(
    auth_client, auth_store, clock, changes, status
):
    h = signin(auth_client)
    doc, receipt, _ = plan_ready(auth_client, h)
    assert request(auth_client, h, doc, receipt, **changes).status_code == status
    assert rows(auth_store) == []


def test_unapproved_withdrawn_or_missing_plan_cannot_be_requested(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc = source(auth_client, h)
    reviewed = confirm(auth_client, h, doc)
    assert request(auth_client, h, doc, reviewed).status_code == 409
    receipt = approved(auth_client, h, doc, reviewed)
    withdrawn = plan_call(auth_client, h, doc, "withdraw_plan", receipt).json()
    assert request(auth_client, h, doc, withdrawn).status_code == 409
    assert rows(auth_store) == []


def test_only_the_owner_can_request_and_others_cannot_see_filings(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc, receipt, _ = plan_ready(auth_client, h)
    created = filed(auth_client, h, doc, receipt)
    other = signin(auth_client, "bob")
    assert request(auth_client, other, doc, receipt).status_code in {403, 404}
    page = auth_client.post("/api/v1/filing/query", headers=other, json={"scope": doc["scope"]})
    assert page.status_code in {200, 403} and created["id"] not in str(page.json())
    assert auth_client.post(
        "/api/v1/filing/history",
        headers=other,
        json={"scope": doc["scope"], "execution_id": created["id"]},
    ).status_code in {403, 404}


@pytest.mark.parametrize("step", ["timeout_applied", "timeout_lost"])
def test_ambiguous_timeout_reconciles_by_lookup_and_never_double_files(
    auth_client, auth_store, clock, step
):
    h = signin(auth_client)
    doc, receipt, path = plan_ready(auth_client, h)
    filed(auth_client, h, doc, receipt)
    destination = filing.SyntheticDestination({path: [step]})
    assert filing_worker.run_once(destination, auth_store)["unknown"] == 1
    assert rows(auth_store)[0].state == "unknown"
    assert filing_worker.run_once(destination, auth_store)["checked"] == 0
    clock["now"] += filing.RECONCILE_INTERVAL
    result = filing_worker.run_once(destination, auth_store)
    if step == "timeout_applied":
        assert result["filed"] == 1 and destination.writes == 1
        assert operations(auth_store)[-1] == "reconciled"
    else:
        assert result["retried"] == 1 and destination.writes == 1
        assert filing_worker.run_once(destination, auth_store)["filed"] == 1
        assert destination.writes == 2
    (row,) = rows(auth_store)
    assert row.state == "filed" and list(destination.files) == [path]


def test_unavailable_lookup_keeps_the_ambiguity_visible_without_rewriting(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    doc, receipt, path = plan_ready(auth_client, h)
    filed(auth_client, h, doc, receipt)
    destination = filing.SyntheticDestination({path: ["timeout_applied"]}, lookup_available=False)
    assert filing_worker.run_once(destination, auth_store)["unknown"] == 1
    clock["now"] += filing.RECONCILE_INTERVAL
    assert filing_worker.run_once(destination, auth_store)["unknown"] == 1
    clock["now"] += filing.BACKOFF[-1]
    destination.lookup_available = True
    assert filing_worker.run_once(destination, auth_store)["filed"] == 1
    assert destination.writes == 1


def test_destination_exception_is_ambiguous_not_failed(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc, receipt, _ = plan_ready(auth_client, h)
    filed(auth_client, h, doc, receipt)

    class Broken(filing.SyntheticDestination):
        def put(self, key, path, sha256, size):
            raise ConnectionError("synthetic network drop")

    assert filing_worker.run_once(Broken(), auth_store)["unknown"] == 1
    assert rows(auth_store)[0].state == "unknown"


def test_transient_failures_retry_with_backoff_then_exhaust(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc, receipt, path = plan_ready(auth_client, h)
    filed(auth_client, h, doc, receipt)
    destination = filing.SyntheticDestination({path: ["transient"] * 3})
    assert filing_worker.run_once(destination, auth_store)["retried"] == 1
    assert filing_worker.run_once(destination, auth_store)["checked"] == 0
    clock["now"] += filing.BACKOFF[0]
    assert filing_worker.run_once(destination, auth_store)["retried"] == 1
    clock["now"] += filing.BACKOFF[1]
    assert filing_worker.run_once(destination, auth_store)["failed"] == 1
    (row,) = rows(auth_store)
    assert row.state == "failed" and row.reason == "attempts_exhausted" and row.attempts == 3
    clock["now"] += timedelta(days=1)
    assert filing_worker.run_once(destination, auth_store)["checked"] == 0
    assert destination.writes == 3 and destination.files == {}


def test_existing_destination_is_never_overwritten(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc, receipt, path = plan_ready(auth_client, h)
    filed(auth_client, h, doc, receipt)
    destination = filing.SyntheticDestination()
    destination.files[path] = ("someone-else", "0" * 64, 1)
    assert filing_worker.run_once(destination, auth_store)["failed"] == 1
    (row,) = rows(auth_store)
    assert row.state == "failed" and row.reason == "collision"
    assert destination.files[path] == ("someone-else", "0" * 64, 1)
    assert destination.writes == 0


def test_plan_withdrawn_after_request_cancels_without_any_effect(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc, receipt, _ = plan_ready(auth_client, h)
    filed(auth_client, h, doc, receipt)
    assert plan_call(auth_client, h, doc, "withdraw_plan", receipt).status_code == 200
    destination = filing.SyntheticDestination()
    assert filing_worker.run_once(destination, auth_store)["cancelled"] == 1
    (row,) = rows(auth_store)
    assert row.state == "cancelled" and row.reason == "plan_changed"
    assert destination.writes == 0


def test_owner_can_cancel_only_work_that_has_not_started(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc, receipt, _ = plan_ready(auth_client, h)
    created = filed(auth_client, h, doc, receipt)

    def cancel(revision):
        return auth_client.post(
            "/api/v1/filing/cancel",
            headers=h,
            json={
                "scope": doc["scope"],
                "execution_id": created["id"],
                "expected_revision": revision,
            },
        )

    assert cancel(7).status_code == 409
    done = cancel(1)
    assert done.status_code == 200 and done.json()["filing"]["state"] == "cancelled"
    destination = filing.SyntheticDestination()
    assert filing_worker.run_once(destination, auth_store)["checked"] == 0
    assert cancel(2).status_code == 409 and destination.writes == 0
    assert operations(auth_store) == ["requested", "cancelled"]
    # A cancelled request frees the destination and may be requested again only for a new plan.
    assert request(auth_client, h, doc, receipt).json()["replayed"] is True


def test_unknown_work_cannot_be_cancelled_it_must_be_reconciled(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc, receipt, path = plan_ready(auth_client, h)
    created = filed(auth_client, h, doc, receipt)
    filing_worker.run_once(filing.SyntheticDestination({path: ["timeout_applied"]}), auth_store)
    refused = auth_client.post(
        "/api/v1/filing/cancel",
        headers=h,
        json={"scope": doc["scope"], "execution_id": created["id"], "expected_revision": 3},
    )
    assert refused.status_code == 409 and rows(auth_store)[0].state == "unknown"


def test_forgetting_the_document_scrubs_the_finished_destination_key(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    done, done_receipt, _ = plan_ready(auth_client, h)
    filed(auth_client, h, done, done_receipt)
    filing_worker.run_once(filing.SyntheticDestination(), auth_store)
    assert document_call(auth_client, h, done, "forget").status_code == 200
    states = {r.state: r for r in rows(auth_store)}
    assert states["filed"].destination_key is None
    assert operations(auth_store) == ["requested", "attempted", "filed", "scrubbed"]


def test_forgetting_a_pending_document_cancels_it_and_never_files(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc, receipt, _ = plan_ready(auth_client, h)
    filed(auth_client, h, doc, receipt)
    assert document_call(auth_client, h, doc, "forget").status_code == 200
    destination = filing.SyntheticDestination()
    assert filing_worker.run_once(destination, auth_store)["checked"] == 0
    (row,) = rows(auth_store)
    assert row.state == "cancelled" and row.reason == "source_changed"
    assert row.destination_key is None and destination.writes == 0


def test_bounded_pass_is_enforced(auth_store):
    for limit in (0, 101):
        with pytest.raises(ValueError):
            filing_worker.run_once(filing.SyntheticDestination(), auth_store, limit=limit)


def test_destination_key_is_scope_qualified_and_opaque():
    one = filing.destination_key("household_shared", "invoices/a.txt")
    assert one != filing.destination_key("member_a_private", "invoices/a.txt")
    assert len(one) == 64 and "invoices" not in one


def test_a_destination_already_requested_by_another_plan_is_refused(auth_client, auth_store, clock):
    h = signin(auth_client)
    receipts = []
    for _ in range(2):
        doc = source(auth_client, h, TEXT + "\nSynthetic copy " + str(len(receipts)))
        reviewed = confirm(auth_client, h, doc)
        planned = plan_call(
            auth_client, h, doc, "plan", reviewed, folder="invoices/manual", filename="same.txt"
        ).json()
        receipt = plan_call(
            auth_client,
            h,
            doc,
            "approve_plan",
            planned,
            acknowledge_plan_only=True,
            acknowledge_duplicate_limits=True,
        ).json()
        receipts.append((doc, receipt))
    (first, first_receipt), (second, second_receipt) = receipts
    assert request(auth_client, h, first, first_receipt).status_code == 201
    refused = request(auth_client, h, second, second_receipt)
    assert refused.status_code == 409 and len(rows(auth_store)) == 1
    # Once the first filing is cancelled the destination is free again.
    (existing,) = rows(auth_store)
    cancelled = auth_client.post(
        "/api/v1/filing/cancel",
        headers=h,
        json={"scope": first["scope"], "execution_id": str(existing.id), "expected_revision": 1},
    )
    assert cancelled.status_code == 200
    assert request(auth_client, h, second, second_receipt).status_code == 201


@pytest.mark.parametrize(
    "path",
    [
        "invoices/2026/vendor/a.txt",
        "invoices//2026///vendor/a.txt",
        "invoices/2026/vendor/a.txt/",
        "Invoices/2026/Vendor/A.TXT",
        "invoices/2026/vendor/a.txt//",
    ],
)
def test_destination_policy_collapses_separators_and_case(path):
    assert filing.canonical_path(path) == "invoices/2026/vendor/a.txt"
    assert filing.destination_key("household_shared", path) == filing.destination_key(
        "household_shared", "invoices/2026/vendor/a.txt"
    )


def test_destination_policy_normalises_unicode_composition():
    composed = "invoices/caf\u00e9/a.txt"
    decomposed = "invoices/cafe\u0301/a.txt"
    assert composed != decomposed
    assert filing.canonical_path(composed) == filing.canonical_path(decomposed)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/invoices/a.txt",
        "invoices/../a.txt",
        "invoices/./a.txt",
        "invoices\\a.txt",
        "c:/invoices/a.txt",
        "invoices/a.txt:stream",
        "invoices/a\x00.txt",
        "invoices/a\n.txt",
        "///",
        "x" * 400,
        None,
        7,
    ],
)
def test_destination_policy_refuses_unsafe_paths(path):
    with pytest.raises(ValueError):
        filing.canonical_path(path)


def test_case_variant_of_an_existing_destination_is_a_collision_never_an_overwrite():
    destination = filing.SyntheticDestination()
    assert destination.put("one", "Invoices/A.txt", "0" * 64, 1) == filing.Outcome.ACCEPTED
    assert destination.put("two", "invoices//a.TXT/", "1" * 64, 1) == filing.Outcome.COLLISION
    assert destination.put("one", "invoices/a.txt", "0" * 64, 1) == filing.Outcome.ACCEPTED
    assert list(destination.files) == ["invoices/a.txt"] and destination.writes == 1


def test_authorization_is_consumed_by_the_first_claim_and_never_again(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    doc, receipt, path = plan_ready(auth_client, h)
    created = filed(auth_client, h, doc, receipt)
    (row,) = rows(auth_store)
    assert row.authorization_consumed_at is None and row.attempts == 0
    destination = filing.SyntheticDestination({path: ["transient"]})
    assert filing_worker.run_once(destination, auth_store)["retried"] == 1
    (row,) = rows(auth_store)
    consumed = row.authorization_consumed_at
    assert identity.aware(consumed) == clock["now"] and row.attempts == 1
    clock["now"] += filing.BACKOFF[0]
    assert filing_worker.run_once(destination, auth_store)["filed"] == 1
    (row,) = rows(auth_store)
    assert row.attempts == 2 and row.authorization_consumed_at == consumed
    # A replayed request neither creates a second authorization nor files again.
    again = request(auth_client, h, doc, receipt)
    assert again.status_code == 200 and again.json()["filing"]["id"] == created["id"]
    assert filing_worker.run_once(destination, auth_store)["checked"] == 0
    assert len(rows(auth_store)) == 1 and destination.writes == 2


def test_cancelled_authorization_stays_unconsumed_and_cannot_be_replayed(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    doc, receipt, _ = plan_ready(auth_client, h)
    created = filed(auth_client, h, doc, receipt)
    cancelled = auth_client.post(
        "/api/v1/filing/cancel",
        headers=h,
        json={"scope": doc["scope"], "execution_id": created["id"], "expected_revision": 1},
    )
    assert cancelled.status_code == 200
    (row,) = rows(auth_store)
    assert row.authorization_consumed_at is None and row.attempts == 0
    destination = filing.SyntheticDestination()
    replay = request(auth_client, h, doc, receipt)
    assert replay.json()["replayed"] is True and replay.json()["filing"]["state"] == "cancelled"
    assert filing_worker.run_once(destination, auth_store)["checked"] == 0
    assert destination.writes == 0 and len(rows(auth_store)) == 1


def test_an_authorization_for_one_plan_revision_never_files_a_newer_revision(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    doc, receipt, old_path = plan_ready(auth_client, h)
    old = filed(auth_client, h, doc, receipt)
    withdrawn = plan_call(auth_client, h, doc, "withdraw_plan", receipt).json()
    replanned = plan_call(
        auth_client, h, doc, "plan", withdrawn, folder="invoices/manual", filename="newer.txt"
    ).json()
    newer = plan_call(
        auth_client,
        h,
        doc,
        "approve_plan",
        replanned,
        acknowledge_plan_only=True,
        acknowledge_duplicate_limits=True,
    ).json()
    assert newer["review_revision"] > receipt["review_revision"]
    destination = filing.SyntheticDestination()
    # The old authorization is bound to the old revision: it cancels, it never files the new plan.
    assert filing_worker.run_once(destination, auth_store)["cancelled"] == 1
    assert destination.writes == 0
    (row,) = rows(auth_store)
    assert row.state == "cancelled" and row.reason == "plan_changed"
    assert row.plan_revision == receipt["review_revision"]
    assert row.authorization_consumed_at is None
    # The stale receipt cannot request the newer plan, and a new authorization is a new row.
    assert request(auth_client, h, doc, receipt).status_code == 409
    fresh = request(auth_client, h, doc, newer)
    assert fresh.status_code == 201 and fresh.json()["filing"]["id"] != old["id"]
    assert filing_worker.run_once(destination, auth_store)["filed"] == 1
    assert list(destination.files) == ["invoices/manual/newer.txt"]
    assert old_path not in destination.files
    states = {r.plan_revision: r.state for r in rows(auth_store)}
    assert states == {receipt["review_revision"]: "cancelled", newer["review_revision"]: "filed"}


def test_the_approved_plan_keeps_execution_unauthorized_throughout(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc, receipt, _ = plan_ready(auth_client, h)
    assert receipt["review"]["data"]["filing_plan"]["execution_authorized"] is False
    filed(auth_client, h, doc, receipt)
    filing_worker.run_once(filing.SyntheticDestination(), auth_store)
    read = auth_client.post(
        f"/api/v1/invoices/{doc['id']}/read", headers=h, json={"scope": doc["scope"]}
    )
    assert read.json()["review"]["data"]["filing_plan"]["execution_authorized"] is False


def test_forgetting_nulls_every_snapshot_appends_a_scrubbed_event_and_is_idempotent(
    auth_client, auth_store, clock
):
    h = signin(auth_client)
    doc, receipt, path = plan_ready(auth_client, h)
    created = filed(auth_client, h, doc, receipt)
    filing_worker.run_once(filing.SyntheticDestination(), auth_store)
    assert document_call(auth_client, h, doc, "forget").status_code == 200
    history = auth_client.post(
        "/api/v1/filing/history",
        headers=h,
        json={"scope": doc["scope"], "execution_id": created["id"]},
    ).json()
    assert [e["operation"] for e in history["items"]] == [
        "requested",
        "attempted",
        "filed",
        "scrubbed",
    ]
    assert all(e["snapshot"] is None for e in history["items"])
    page = auth_client.post("/api/v1/filing/query", headers=h, json={"scope": doc["scope"]}).json()
    (item,) = page["items"]
    assert item["scrubbed"] is True and item["state"] == "filed"
    assert item["document_id"] is None and item["plan_revision"] is None
    assert item["source_revision"] is None
    assert doc["id"] not in str(history) and doc["id"] not in str(page) and path not in str(page)
    (row,) = rows(auth_store)
    assert row.destination_key is None and row.scrubbed_at is not None
    before = operations(auth_store)
    with auth_store.begin() as db:
        filing.scrub_for_document(db, row.document_id)
        filing.scrub_for_document(db, row.document_id)
    assert operations(auth_store) == before and rows(auth_store)[0].revision == row.revision


def test_nothing_can_be_requested_or_recreated_after_forgetting(auth_client, auth_store, clock):
    h = signin(auth_client)
    doc, receipt, _ = plan_ready(auth_client, h)
    assert document_call(auth_client, h, doc, "forget").status_code == 200
    assert request(auth_client, h, doc, receipt).status_code in {404, 409}
    destination = filing.SyntheticDestination()
    assert filing_worker.run_once(destination, auth_store)["checked"] == 0
    assert rows(auth_store) == [] and destination.writes == 0
