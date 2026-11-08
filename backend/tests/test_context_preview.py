import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_memory import create, patch

from app import identity
from app.manage import set_active, set_scope
from app.models import AuditEvent, AuthSession, MemoryRecord, User


def preview(client, headers, records, scope="household_shared", **changes):
    body = {
        "scope": scope,
        "selections": [{"id": r["id"], "expected_revision": r["revision"]} for r in records],
    }
    body.update(changes)
    return client.post("/api/v1/context/preview", headers=headers, json=body)


def catalogue(client, scope="household_shared", suffix=""):
    return client.get("/api/v1/context/candidates?scope=" + scope + suffix)


def test_explicit_catalogue_metadata_pages_and_preview(auth_client, auth_store):
    headers = signin(auth_client)
    records = [create(auth_client, headers).json() for _ in range(3)]
    page = catalogue(auth_client, suffix="&limit=2").json()
    assert len(page["items"]) == 2
    assert all("content" not in row for row in page["items"])
    second = catalogue(auth_client, suffix="&after=" + page["next_cursor"]).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    result = preview(auth_client, headers, records[:2])
    assert result.status_code == 200
    bundle = result.json()
    assert bundle["mode"] == "preview_only" and bundle["reference_only"] is True
    assert bundle["model_invoked"] is False and bundle["execution_allowed"] is False
    assert [r["id"] for r in bundle["items"]] == [r["id"] for r in records[:2]]
    assert bundle["items"][0]["source_reference"] == "synthetic-source-1"
    assert bundle["items"][0]["assessment"] == "confirmed"
    assert result.headers["cache-control"] == "no-store"
    with auth_store() as db:
        events = list(
            db.scalars(select(AuditEvent).where(AuditEvent.event_type == "context.preview"))
        )
        assert len(events) == 1 and len(events[0].metadata_json["records"]) == 2
        assert "synthetic-only" not in str(events[0].metadata_json)
        assert "synthetic-source-1" not in str(events[0].metadata_json)


@pytest.mark.parametrize(
    "changes",
    [
        {"assessment": "tentative"},
        {"kind": "experience"},
        {"content": {"record_type": "discovery_proposal"}},
        {"content": {"record_type": None}},
        {"content": {"record_type": False}},
    ],
)
def test_ineligible_records_never_appear_or_enter_preview(auth_client, changes):
    headers = signin(auth_client)
    record = create(auth_client, headers, **changes).json()
    assert catalogue(auth_client).json()["items"] == []
    response = preview(auth_client, headers, [record])
    assert response.status_code == 404 and response.json() == {"detail": "Access denied"}


@pytest.mark.parametrize("scope", ["technical_admin", "work_private", "finance_private"])
def test_unknown_admin_work_or_unassigned_scope_is_denied(auth_client, scope):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    assert catalogue(auth_client, scope).status_code == 403
    assert preview(auth_client, headers, [record], scope).status_code == 403


def test_same_private_scope_does_not_reveal_another_owner_or_partial_result(
    auth_client, auth_store
):
    bob_headers = signin(auth_client, "bob")
    private = create(auth_client, bob_headers, scope="member_b_private").json()
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "member_b_private", True)
    headers = signin(auth_client)
    mine = create(auth_client, headers, scope="member_b_private").json()
    assert [r["id"] for r in catalogue(auth_client, "member_b_private").json()["items"]] == [
        mine["id"]
    ]
    for unavailable in [private, dict(mine, id=str(uuid4()))]:
        response = preview(auth_client, headers, [mine, unavailable], "member_b_private")
        assert response.status_code == 404 and "items" not in response.json()
    assert preview(auth_client, headers, [private], "household_shared").status_code == 404


def test_current_shared_reader_can_preview_but_current_revocation_and_disablement_apply(
    auth_client, auth_store
):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "bob")), "household_shared", True)
    bob_headers = signin(auth_client, "bob")
    assert preview(auth_client, bob_headers, [record]).status_code == 200
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, bob, "household_shared", False)
    assert catalogue(auth_client).status_code == 403
    assert preview(auth_client, bob_headers, [record]).status_code == 403
    with auth_store.begin() as db:
        set_active(db, db.scalar(select(User).where(User.slug == "bob")), False)
    assert preview(auth_client, bob_headers, [record]).status_code == 401


@pytest.mark.parametrize("change,status", [("scope", 403), ("session_expiry", 401)])
def test_rechecks_authority_after_a_row_wait(auth_client, auth_store, monkeypatch, change, status):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    if change == "scope":
        original = identity.memberships
        calls = 0

        def current_memberships(db, user):
            nonlocal calls
            calls += 1
            return original(db, user) if calls == 1 else []

        monkeypatch.setattr(identity, "memberships", current_memberships)
    else:
        now = identity.now_utc()
        with auth_store.begin() as db:
            session = db.scalar(
                select(AuthSession).where(
                    AuthSession.token_hash
                    == identity.digest(auth_client.cookies.get(identity.COOKIE))
                )
            )
            session.expires_at = now + timedelta(seconds=1)
        times = iter([now, now + timedelta(seconds=2)])
        monkeypatch.setattr(identity, "now_utc", lambda: next(times))
    result = preview(auth_client, headers, [record])
    assert result.status_code == status and "items" not in result.json()


def test_changed_revision_and_forgotten_sources_release_no_context(auth_client):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    newer = patch(auth_client, headers, record, content={"text": "Synthetic corrected"}).json()
    assert preview(auth_client, headers, [record]).status_code == 409
    assert preview(auth_client, headers, [newer]).json()["items"][0]["content"] == {
        "text": "Synthetic corrected"
    }
    assert (
        auth_client.post(
            f"/api/v1/memory/{record['id']}/forget", headers=headers, json={"expected_revision": 2}
        ).status_code
        == 200
    )
    assert catalogue(auth_client).json()["items"] == []
    assert preview(auth_client, headers, [newer]).status_code == 404


def test_expiry_and_tentative_change_after_selection_are_rechecked(auth_client, monkeypatch):
    headers = signin(auth_client)
    now = identity.now_utc()
    record = create(
        auth_client, headers, kind="context", expires_at=(now + timedelta(seconds=10)).isoformat()
    ).json()
    assert len(catalogue(auth_client).json()["items"]) == 1
    monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(seconds=11))
    assert catalogue(auth_client).json()["items"] == []
    assert preview(auth_client, headers, [record]).status_code == 404
    other = create(auth_client, headers).json()
    tentative = patch(auth_client, headers, other, assessment="tentative").json()
    assert preview(auth_client, headers, [tentative]).status_code == 404


@pytest.mark.parametrize(
    "source_seconds,session_seconds,expected", [(None, 120, 60), (12, 120, 12), (None, 20, 20)]
)
def test_preview_lifetime_clamps_source_and_session(
    auth_client, auth_store, monkeypatch, source_seconds, session_seconds, expected
):
    headers = signin(auth_client)
    now = identity.now_utc()
    record = create(
        auth_client,
        headers,
        expires_at=(now + timedelta(seconds=source_seconds)).isoformat()
        if source_seconds
        else None,
    ).json()
    with auth_store.begin() as db:
        session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == identity.digest(auth_client.cookies.get(identity.COOKIE))
            )
        )
        session.expires_at = now + timedelta(seconds=session_seconds)
    monkeypatch.setattr(identity, "now_utc", lambda: now)
    bundle = preview(auth_client, headers, [record]).json()
    from datetime import datetime

    assert (
        datetime.fromisoformat(bundle["valid_until"])
        - datetime.fromisoformat(bundle["generated_at"])
    ).total_seconds() == expected


def test_utf8_full_items_budget_without_truncation(auth_client):
    headers = signin(auth_client)
    record = create(auth_client, headers, content={"text": "é" * 1000}).json()
    small = preview(auth_client, headers, [record], max_bytes=2048)
    assert small.status_code == 413 and "items" not in small.json()
    bundle = preview(auth_client, headers, [record], max_bytes=16384).json()
    size = len(
        json.dumps(
            bundle["items"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )
    assert size == bundle["items_bytes"] and size > 2048
    assert bundle["items"][0]["content"]["text"] == "é" * 1000


@pytest.mark.parametrize(
    "changes",
    [
        {"selections": []},
        {"max_bytes": 511},
        {"max_bytes": 16385},
        {"max_bytes": True},
        {"content": {"text": "caller injection"}},
        {"owner_id": str(uuid4())},
        {"selections": [{"id": str(uuid4()), "expected_revision": True}]},
        {"selections": [{"id": str(uuid4()), "expected_revision": 1}] * 2},
        {"selections": [{"id": str(uuid4()), "expected_revision": 1} for _ in range(11)]},
    ],
)
def test_invalid_selection_contracts(auth_client, changes):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    assert preview(auth_client, headers, [record], **changes).status_code == 422


def test_session_csrf_origin_and_catalogue_bounds(auth_client):
    assert catalogue(auth_client).status_code == 401
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    assert preview(auth_client, {}, [record]).status_code == 403
    assert (
        preview(auth_client, dict(headers, Origin="https://other.example"), [record]).status_code
        == 403
    )
    assert catalogue(auth_client, suffix="&limit=26").status_code == 422
    assert catalogue(auth_client, suffix="&after=invalid").status_code == 422


def test_malformed_current_payload_fails_closed(auth_client, auth_store):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()
    with auth_store.begin() as db:
        db.get(MemoryRecord, UUID(record["id"])).content = ["Synthetic invalid object"]
    assert catalogue(auth_client).status_code == 422
    assert preview(auth_client, headers, [record]).status_code == 404


@pytest.mark.parametrize("operation", ["catalogue", "preview"])
@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_failure_releases_no_payload(auth_client, auth_store, monkeypatch, operation, failure):
    headers = signin(auth_client)
    record = create(auth_client, headers).json()

    def fail(*args, **kwargs):
        raise SQLAlchemyError("Synthetic unavailable")

    if failure == "audit":
        monkeypatch.setattr(identity, "audit", fail)
    else:
        event.listen(auth_store, "before_commit", fail)
    try:
        response = (
            catalogue(auth_client)
            if operation == "catalogue"
            else preview(auth_client, headers, [record])
        )
        assert response.status_code == 503 and "items" not in response.json()
    finally:
        if failure == "commit":
            event.remove(auth_store, "before_commit", fail)
