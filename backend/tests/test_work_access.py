from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_memory import signin

from app import identity
from app.manage import set_active, set_scope
from app.models import AuditEvent, AuthSession, User, WorkGrant, WorkWorkspace
from app.work_manage import administer

URL = "/api/v1/work/workspaces"


def setup_work(store):
    with store.begin() as db:
        administer(db, "create-workspace", "synthetic-team-a")
        administer(db, "create-workspace", "synthetic-team-b")
        administer(db, "grant", "synthetic-team-a", "alice")
        administer(db, "grant", "synthetic-team-b", "bob")
        return {row.slug: str(row.id) for row in db.scalars(select(WorkWorkspace))}


def test_only_explicit_grants_and_disabled_status(auth_client, auth_store):
    ids = setup_work(auth_store)
    signin(auth_client)
    page = auth_client.get(URL)
    assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
    assert page.json()["items"] == [{"id": ids["synthetic-team-a"], "slug": "synthetic-team-a"}]
    status = auth_client.get(f"{URL}/{ids['synthetic-team-a']}/status").json()
    assert status["mode"] == "access_foundation_only"
    assert (
        status["ingestion_allowed"]
        is status["model_invoked"]
        is status["execution_allowed"]
        is False
    )
    assert len(status["pending_gates"]) == 5
    for denied_id in [ids["synthetic-team-b"], str(uuid4())]:
        denied = auth_client.get(f"{URL}/{denied_id}/status")
        assert denied.status_code == 404 and denied.json() == {"detail": "Access denied"}
    assert "work_private" not in auth_client.get("/api/v1/auth/me").json()["scopes"]
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-a']}/debriefs", json={"text": "Synthetic"}
        ).status_code
        == 404
    )
    with auth_store() as db:
        events = list(db.scalars(select(AuditEvent).where(AuditEvent.event_type.like("work.%"))))
        assert any(e.event_type == "work.access_denied" for e in events)
        assert all(
            "synthetic-team"
            not in str(e.metadata_json)
            + str(e.source_context)
            + str(e.before_json)
            + str(e.after_json)
            for e in events
        )


def test_family_and_technical_admin_grants_never_imply_work(auth_client, auth_store):
    ids = setup_work(auth_store)
    with auth_store.begin() as db:
        administer(db, "revoke", "synthetic-team-a", "alice")
        user = db.scalar(select(User).where(User.slug == "alice"))
        for scope in identity.SCOPES:
            set_scope(db, user, scope, True)
    headers = signin(auth_client)
    assert auth_client.get(URL).json()["items"] == []
    assert auth_client.get(f"{URL}/{ids['synthetic-team-a']}/status").status_code == 404
    assert auth_client.get("/api/v1/context/candidates?scope=work_private").status_code == 403
    assert auth_client.get("/api/v1/memory?scope=work_private").json()["items"] == []
    from test_memory import content

    assert (
        auth_client.post(
            "/api/v1/memory",
            headers=headers,
            json={"scope": "work_private", "kind": "context", **content()},
        ).status_code
        == 403
    )
    assert auth_client.get("/api/v1/auth/scopes/work_private").status_code == 403


@pytest.mark.parametrize(
    "change,status", [("revoke", 404), ("disable", 404), ("user", 401), ("session", 401)]
)
def test_current_authority_applies_without_relogin(auth_client, auth_store, change, status):
    ids = setup_work(auth_store)
    signin(auth_client)
    url = f"{URL}/{ids['synthetic-team-a']}/status"
    assert auth_client.get(url).status_code == 200
    with auth_store.begin() as db:
        if change in {"revoke", "disable"}:
            administer(db, change, "synthetic-team-a", "alice")
        elif change == "user":
            set_active(db, db.scalar(select(User).where(User.slug == "alice")), False)
        else:
            for session in db.scalars(select(AuthSession)):
                session.revoked_at = identity.now_utc()
    assert auth_client.get(url).status_code == status
    assert auth_client.get(URL).json().get("items", []) == []


def test_bounds_pagination_and_anonymous_access(auth_client, auth_store):
    assert auth_client.get(URL).status_code == 401
    with auth_store.begin() as db:
        for n in range(26):
            slug = f"synthetic-team-{n}"
            administer(db, "create-workspace", slug)
            administer(db, "grant", slug, "alice")
    signin(auth_client)
    first = auth_client.get(URL).json()
    assert len(first["items"]) == 25
    second = auth_client.get(URL + "?after=" + first["next_cursor"]).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert {x["id"] for x in first["items"]}.isdisjoint(x["id"] for x in second["items"])
    assert auth_client.get(URL + "?limit=26").status_code == 422
    assert auth_client.get(URL + "?after=bad").status_code == 422
    assert auth_client.get(URL, headers={"Host": "other.invalid"}).status_code == 403


@pytest.mark.parametrize("operation", ["list", "status"])
@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_persistence_failure_releases_no_metadata(
    auth_client, auth_store, monkeypatch, operation, failure
):
    ids = setup_work(auth_store)
    signin(auth_client)

    def fail(*args, **kwargs):
        raise SQLAlchemyError("Synthetic private error")

    if failure == "audit":
        monkeypatch.setattr(identity, "audit", fail)
    else:
        event.listen(auth_store, "before_commit", fail)
    try:
        response = auth_client.get(
            URL if operation == "list" else f"{URL}/{ids['synthetic-team-a']}/status"
        )
        assert response.status_code == 503
        assert "synthetic-team" not in response.text and "private error" not in response.text
    finally:
        if failure == "commit":
            event.remove(auth_store, "before_commit", fail)


def test_admin_validation_idempotence_and_audit_rollback(auth_store):
    ids = setup_work(auth_store)
    with auth_store.begin() as db:
        administer(db, "grant", "synthetic-team-a", "alice")
        assert len(list(db.scalars(select(WorkGrant)))) == 2
        for invalid in ["real-company", "synthetic-", "synthetic-" + "a" * 55]:
            with pytest.raises(ValueError):
                administer(db, "create-workspace", invalid)
        with pytest.raises(ValueError):
            administer(db, "create-workspace", "synthetic-team-a")
        with pytest.raises(ValueError):
            administer(db, "grant", "synthetic-team-a", "unknown")
        administer(db, "disable", "synthetic-team-a")
        administer(db, "enable", "synthetic-team-a")
    with pytest.raises(RuntimeError), auth_store.begin() as db:
        administer(db, "revoke", "synthetic-team-a", "alice")
        raise RuntimeError("Synthetic transaction rollback")
    with auth_store() as db:
        assert (
            db.get(
                WorkGrant,
                (
                    db.scalar(select(User).where(User.slug == "alice")).id,
                    UUID(ids["synthetic-team-a"]),
                ),
            )
            is not None
        )


def test_work_membership_does_not_grant_family_access(auth_client, auth_store):
    ids = setup_work(auth_store)
    with auth_store.begin() as db:
        user = db.scalar(select(User).where(User.slug == "alice"))
        set_scope(db, user, "household_shared", False)
    signin(auth_client)
    assert auth_client.get(f"{URL}/{ids['synthetic-team-a']}/status").status_code == 200
    assert auth_client.get("/api/v1/auth/me").json()["scopes"] == []
    assert auth_client.get("/api/v1/context/candidates?scope=household_shared").status_code == 403
