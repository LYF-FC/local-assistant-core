from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin

from app import identity
from app.manage import set_scope
from app.models import AuditEvent, ManualTask, ManualTaskRevision, User


def values(**changes):
    return {
        "title": "Synthetic task",
        "details": "Synthetic details",
        "source_reference": "Synthetic manual source",
        "due_at": None,
        "assignment": "unknown",
        **changes,
    }


def create(client, headers, **changes):
    return client.post(
        "/api/v1/tasks", headers=headers, json={"scope": "household_shared", **values(), **changes}
    )


def call(client, headers, row, operation, **changes):
    body = {"scope": row["scope"]}
    if operation in {"correct", "transition", "forget"}:
        body["expected_revision"] = row["revision"]
    if operation == "correct":
        body.update(values())
    body.update(changes)
    return client.post(f"/api/v1/tasks/{row['id']}/{operation}", headers=headers, json=body)


def query(client, headers, **changes):
    return client.post(
        "/api/v1/tasks/query", headers=headers, json={"scope": "household_shared", **changes}
    )


def test_lifecycle_status_corrections_provenance_and_history(auth_client):
    h = signin(auth_client)
    response = create(auth_client, h, assignment="me")
    assert response.status_code == 201
    row = response.json()
    assert row["status"] == "open" and row["assignee_id"] == row["owner_id"]
    assert row["due_at"] is None and row["completed_at"] is None and row["can_edit"]
    original = row
    row = call(auth_client, h, row, "correct", title="Synthetic corrected", assignment="me").json()
    assert row["revision"] == 2 and row["status"] == "open"
    assert call(auth_client, h, original, "transition", status="done").status_code == 409
    row = call(auth_client, h, row, "transition", status="done").json()
    completion = row["completed_at"]
    assert completion == row["updated_at"] and row["cancelled_at"] is None
    assert call(auth_client, h, row, "transition", status="cancelled").status_code == 409
    row = call(auth_client, h, row, "correct", details="Synthetic closure note").json()
    assert row["completed_at"] == completion and row["status"] == "done"
    row = call(auth_client, h, row, "transition", status="open").json()
    assert row["completed_at"] is None
    row = call(auth_client, h, row, "transition", status="cancelled").json()
    assert row["cancelled_at"] == row["updated_at"]
    row = call(auth_client, h, row, "transition", status="open").json()
    history = call(auth_client, h, row, "history").json()
    assert [r["operation"] for r in history["items"]] == [
        "created",
        "corrected",
        "completed",
        "corrected",
        "reopened",
        "cancelled",
        "reopened",
    ]
    assert [r["revision"] for r in history["items"]] == list(range(1, 8))
    assert history["items"][0]["snapshot"]["title"] == "Synthetic task"
    assert history["items"][2]["snapshot"]["completed_at"] == completion
    assert call(auth_client, h, row, "transition", status="open").status_code == 409


def test_forgetting_scrubs_all_snapshots_and_is_terminal(auth_client, auth_store):
    h = signin(auth_client)
    row = create(auth_client, h, assignment="me", due_at=identity.now_utc().isoformat()).json()
    row = call(auth_client, h, row, "transition", status="done").json()
    tombstone = call(auth_client, h, row, "forget").json()
    assert tombstone["state"] == "forgotten" and "title" not in tombstone
    assert query(auth_client, h, status="all").json()["items"] == []
    assert call(auth_client, h, tombstone, "read").status_code == 410
    assert call(auth_client, h, tombstone, "correct").status_code == 410
    assert call(auth_client, h, tombstone, "forget").status_code == 410
    history = call(auth_client, h, tombstone, "history").json()
    assert [x["snapshot"] for x in history["items"]] == [None, None, None]
    with auth_store() as db:
        stored = db.get(ManualTask, UUID(row["id"]))
        assert all(
            getattr(stored, key) is None
            for key in [
                "title",
                "details",
                "source_reference",
                "due_at",
                "status",
                "assignee_id",
                "completed_at",
                "cancelled_at",
            ]
        )
        audit = list(db.scalars(select(AuditEvent).where(AuditEvent.entity_id == row["id"])))
        assert audit and all(
            "Synthetic" not in str(x.metadata_json) + str(x.after_json) + str(x.before_json)
            for x in audit
        )


def test_shared_read_only_and_private_owner_even_same_grant(auth_client, auth_store):
    h = signin(auth_client)
    shared = create(auth_client, h).json()
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, bob, "household_shared", True)
        alice = db.scalar(select(User).where(User.slug == "alice"))
        set_scope(db, alice, "member_b_private", True)
    bob_h = signin(auth_client, "bob")
    private = create(auth_client, bob_h, scope="member_b_private").json()
    read = call(auth_client, bob_h, shared, "read")
    assert read.status_code == 200 and not read.json()["can_edit"]
    for operation, body in [
        ("correct", {}),
        ("transition", {"status": "done"}),
        ("forget", {}),
        ("history", {}),
    ]:
        assert call(auth_client, bob_h, shared, operation, **body).status_code == 403
    alice_h = signin(auth_client)
    for operation, body in [
        ("read", {}),
        ("correct", {}),
        ("transition", {"status": "done"}),
        ("forget", {}),
        ("history", {}),
    ]:
        response = call(auth_client, alice_h, private, operation, **body)
        assert response.status_code == 404 and response.json() == {"detail": "Access denied"}
    assert query(auth_client, alice_h, scope="member_b_private").json()["items"] == []


def test_agenda_literal_search_boundaries_and_export(auth_client, monkeypatch):
    h = signin(auth_client)
    now = identity.now_utc()
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    due = lambda delta: (now + delta).isoformat()
    past = create(
        auth_client, h, title="Synthetic 100%_ match", due_at=due(timedelta(seconds=-1))
    ).json()
    today = create(auth_client, h, due_at=due(timedelta())).json()
    create(auth_client, h, due_at=due(timedelta(days=7)))
    unknown = create(auth_client, h).json()
    closed = create(auth_client, h, due_at=due(timedelta(days=-1))).json()
    call(auth_client, h, closed, "transition", status="done")
    assert [
        r["id"] for r in query(auth_client, h, due="overdue", status="all").json()["items"]
    ] == [past["id"]]
    assert [r["id"] for r in query(auth_client, h, due="next_seven_days").json()["items"]] == [
        today["id"]
    ]
    assert [r["id"] for r in query(auth_client, h, due="unknown").json()["items"]] == [
        unknown["id"]
    ]
    assert [r["id"] for r in query(auth_client, h, search="100%_").json()["items"]] == [past["id"]]
    assert query(auth_client, h, search="100%%").json()["items"] == []
    response = auth_client.post(
        "/api/v1/tasks/export",
        headers=h,
        json={"scope": "household_shared", "status": "all", "acknowledge_copy_limits": True},
    )
    assert response.status_code == 200 and response.json()["managed_copy"] is False
    assert response.json()["schema_version"] == 1 and len(response.json()["items"]) == 5
    assert response.headers["Cache-Control"] == "no-store"
    assert "attachment" in response.headers["Content-Disposition"]
    call(auth_client, h, past, "forget")
    assert (
        len(
            auth_client.post(
                "/api/v1/tasks/export",
                headers=h,
                json={
                    "scope": "household_shared",
                    "status": "all",
                    "acknowledge_copy_limits": True,
                },
            ).json()["items"]
        )
        == 4
    )


def test_keyset_pages_and_bounded_history(auth_client):
    h = signin(auth_client)
    rows = [create(auth_client, h, title=f"Synthetic page {i}").json() for i in range(27)]
    first = query(auth_client, h).json()
    second = query(auth_client, h, after=first["next_cursor"]).json()
    assert len(first["items"]) == 25 and len(second["items"]) == 2 and second["next_cursor"] is None
    ids = [r["id"] for r in first["items"] + second["items"]]
    assert ids == sorted(r["id"] for r in rows)
    row = rows[0]
    for i in range(27):
        row = call(auth_client, h, row, "correct", title=f"Synthetic revision {i}").json()
    first = call(auth_client, h, row, "history").json()
    second = call(auth_client, h, row, "history", after=first["next_cursor"]).json()
    assert len(first["items"]) == 25 and len(second["items"]) == 3 and second["next_cursor"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"scope": "technical_admin"},
        {"scope": "finance_private"},
        {"scope": "work_private"},
        {"title": "  "},
        {"title": "x" * 161},
        {"details": "x" * 4001},
        {"source_reference": " "},
        {"due_at": "2026-11-07T12:00:00"},
        {"assignment": "bob"},
        {"assignee_id": str(uuid4())},
        {"status": "done"},
        {"expected_revision": 1},
        {"owner_id": str(uuid4())},
    ],
)
def test_invalid_content_is_sanitized(auth_client, change):
    h = signin(auth_client)
    response = create(auth_client, h, **change)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}


@pytest.mark.parametrize("revision", [True, 0, -1, "1", 1.0])
def test_strict_revision(auth_client, revision):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    assert call(auth_client, h, row, "forget", expected_revision=revision).status_code == 422


@pytest.mark.parametrize("ack", [None, False, 1, "true"])
def test_export_requires_explicit_boolean(auth_client, ack):
    h = signin(auth_client)
    assert (
        auth_client.post(
            "/api/v1/tasks/export",
            headers=h,
            json={"scope": "household_shared", "acknowledge_copy_limits": ack},
        ).status_code
        == 422
    )


def test_csrf_origin_revocation_and_missing_record(auth_client, auth_store):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    assert query(auth_client, {}).status_code == 403
    assert query(auth_client, {**h, "Origin": "https://example.org"}).status_code == 403
    assert call(auth_client, h, {**row, "id": str(uuid4())}, "read").status_code == 404
    with auth_store.begin() as db:
        alice = db.scalar(select(User).where(User.slug == "alice"))
        set_scope(db, alice, "household_shared", False)
    for operation in ["read", "history", "forget"]:
        assert call(auth_client, h, row, operation).status_code == 403
    assert query(auth_client, h).status_code == 403


def test_audit_failure_rolls_back_task_and_history(auth_client, auth_store, auth_engine):
    h = signin(auth_client)
    row = create(auth_client, h).json()

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic audit failure")

    event.listen(auth_engine, "before_cursor_execute", fail)
    try:
        assert call(auth_client, h, row, "transition", status="done").status_code == 503
    finally:
        event.remove(auth_engine, "before_cursor_execute", fail)
    with auth_store() as db:
        stored = db.get(ManualTask, UUID(row["id"]))
        assert stored.status == "open" and stored.revision == 1
        assert (
            len(
                list(
                    db.scalars(
                        select(ManualTaskRevision).where(ManualTaskRevision.task_id == stored.id)
                    )
                )
            )
            == 1
        )


def test_due_instant_preserves_precision_with_consistent_utc_responses(auth_client):
    h = signin(auth_client)
    row = create(auth_client, h, due_at="2026-01-02T12:00:30.123456+05:30").json()
    assert row["due_at"] == "2026-01-02T06:30:30.123456+00:00"
    assert call(auth_client, h, row, "read").json()["due_at"] == row["due_at"]
    assert (
        call(
            auth_client,
            h,
            row,
            "correct",
            due_at=row["due_at"],
            details="Synthetic precision correction",
        ).json()["due_at"]
        == row["due_at"]
    )
