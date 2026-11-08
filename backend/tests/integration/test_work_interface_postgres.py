"""Real restricted catalogues/inspection and metadata-only current-session recovery."""

import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from psycopg import sql
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from work_storage_helpers import connect

from app import identity, work_capture, work_capture_worker, work_interface, work_read
from app.main import app
from app.models import AuthSession, User
from app.work_notes_storage import provision_changes

pytestmark = pytest.mark.integration


@pytest.fixture
def interface_case(review_case):
    case = review_case
    with connect() as db:
        provision_changes(db, case["slug"])
    source = lambda: work_read.WorkspaceEngines({case["workspace"]: case["engine"]})
    app.dependency_overrides[work_interface.get_interface_engines] = source
    app.dependency_overrides[work_capture.get_capture_engines] = source
    try:
        yield case
    finally:
        app.dependency_overrides.pop(work_interface.get_interface_engines, None)
        app.dependency_overrides.pop(work_capture.get_capture_engines, None)


def send(case, body=None, record=None, workspace=None):
    suffix = f"notes/{record}/inspect" if record else "notes/catalogue"
    return case["client"].post(
        f"/api/v1/work/workspaces/{workspace or case['workspace']}/{suffix}",
        json=body or {},
        headers=case["headers"],
    )


def test_setup_and_inspection_use_labels_without_implicit_write_authority(interface_case):
    case = interface_case
    setup = send(case)
    assert setup.status_code == 200, setup.text
    data = setup.json()
    assert set(data["pages"]) == {"notes", "sources", "parties", "policies", "requests"}
    assert data["pages"]["notes"]["items"][0]["label"] == "review-note"
    assert data["pages"]["policies"]["items"] == [
        {"id": str(case["policy"]), "max_age_seconds": 86400}
    ]
    assert data["pages"]["sources"]["items"][0]["id"] == str(case["source"])
    assert data["pages"]["requests"]["pending_count"] == 0
    assert all(value is False for value in data["features"].values())
    inspection = send(case, record=case["item"].id)
    assert inspection.status_code == 200
    note = inspection.json()
    assert note["item"]["id"] == str(case["item"].id) and len(note["payload_hash"]) == 64
    assert note["references"]["sources"][0]["id"] == str(case["source"])
    assert note["references"]["owner"] is None
    assert note["execution_allowed"] is False and note["model_invoked"] is False
    with connect() as db:
        audits = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE entity_id=%s AND event_type IN ('work.notes_catalogue','work.notes_inspected')",
            (str(case["workspace"]),),
        ).fetchall()
    assert "synthetic:review-note" not in json.dumps(audits) and note[
        "payload_hash"
    ] not in json.dumps(audits)


def test_hidden_content_appears_only_as_metadata_and_inspection_denies(interface_case):
    case = interface_case
    with connect() as db:
        db.execute(
            "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
            (case["workspace"],),
        )
    response = send(case, {"section": "notes"})
    assert response.status_code == 200
    row = response.json()["pages"]["notes"]["items"][0]
    assert row["label"] is None and row["content_available"] is False
    assert "review-note" not in response.text
    assert send(case, record=case["item"].id).status_code == 404


def test_catalogue_cursor_is_bounded_and_scope_filtered(interface_case):
    case = interface_case
    first = send(case, {"section": "policies", "limit": 1})
    assert first.status_code == 200
    with connect() as db:
        for _ in range(3):
            db.execute(
                "INSERT INTO work.retention_policies VALUES(%s,%s,3600)",
                (case["workspace"], uuid4()),
            )
    identifiers = []
    after = None
    for _ in range(4):
        value = send(
            case, dict(section="policies", limit=1, **({"after": after} if after else {}))
        ).json()["pages"]["policies"]
        identifiers.extend(item["id"] for item in value["items"])
        after = value["next_cursor"]
        if after is None:
            break
    assert (
        len(identifiers) == 4 and len(set(identifiers)) == 4 and identifiers == sorted(identifiers)
    )
    assert send(case, workspace=case["storage"]["b"]["workspace"]).status_code == 404


def capture(case, nonce=None):
    from datetime import UTC, datetime

    nonce = nonce or uuid4()
    response = case["client"].post(
        f"/api/v1/work/workspaces/{case['workspace']}/captures",
        headers=case["headers"],
        json={
            "request_id": str(nonce),
            "decision": "capture_draft",
            "policy_id": str(case["policy"]),
            "draft": {
                "kind": "question",
                "marker": "synthetic:interface-recovery",
                "source_ids": [str(case["source"])],
                "retain_until": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
        },
    )
    return nonce, response


def test_nonce_recovery_is_current_session_metadata_and_terminal_safe(interface_case):
    case = interface_case
    nonce, response = capture(case)
    assert response.status_code == 202
    body = {"section": "requests", "request_id": str(nonce), "operation": "capture_draft"}
    recovered = send(case, body)
    assert recovered.status_code == 200
    item = recovered.json()["pages"]["requests"]["items"][0]
    assert item["id"] == response.json()["capture_preparation_id"] and item["state"] == "pending"
    assert "interface-recovery" not in recovered.text and str(case["source"]) not in recovered.text
    with connect() as db, db.transaction():
        work_capture_worker.execute(db, UUID(item["id"]))
    result = send(case, body).json()["pages"]["requests"]["items"][0]
    assert result["state"] == "applied" and result["revision"] == 1
    assert (
        send(case, dict(body, operation="forget_note")).json()["pages"]["requests"]["items"] == []
    )
    from conftest import SYNTHETIC_PASSWORD

    with case["maker"]() as db:
        slug = db.get(User, case["actor"]).slug
    login = case["client"].post(
        "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
    )
    case["headers"] = {"X-CSRF-Token": login.json()["csrf_token"]}
    assert send(case, body).json()["pages"]["requests"]["items"] == []


def test_recovery_does_not_supply_missing_identity_intent(interface_case):
    case = interface_case

    def fail(session):
        if session.bind is not None and session.bind.url.username == "butler_runtime":
            raise SQLAlchemyError("synthetic orphan capture")

    event.listen(Session, "before_commit", fail)
    try:
        nonce, response = capture(case)
    finally:
        event.remove(Session, "before_commit", fail)
    assert response.status_code == 503
    recovery = send(
        case, {"section": "requests", "request_id": str(nonce), "operation": "capture_draft"}
    )
    row = recovery.json()["pages"]["requests"]["items"][0]
    with connect() as db, db.transaction():
        assert work_capture_worker.execute(db, UUID(row["id"]))["state"] == "denied"
    assert "interface-recovery" not in recovery.text


def test_inspection_private_audit_failure_releases_no_payload(interface_case):
    case = interface_case
    name = "synthetic_interface_audit_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE work.draft_audit ADD CONSTRAINT {} CHECK(event_type<>'draft.read_prepared') NOT VALID"
            ).format(sql.Identifier(name))
        )
    try:
        response = send(case, record=case["item"].id)
        assert response.status_code == 503 and "item" not in response.json()
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE work.draft_audit DROP CONSTRAINT {}").format(
                    sql.Identifier(name)
                )
            )


def test_expiry_after_private_commit_clears_inspection(interface_case, monkeypatch):
    case = interface_case
    now = identity.now_utc()
    clock = [now]
    with case["maker"].begin() as db:
        session = (
            db.query(AuthSession)
            .filter_by(token_hash=identity.digest(case["client"].cookies.get(identity.COOKIE)))
            .one()
        )
        session.expires_at = now + timedelta(seconds=1)
    monkeypatch.setattr(identity, "now_utc", lambda: clock[0])

    def expire(connection):
        clock[0] = now + timedelta(seconds=2)

    event.listen(case["engine"], "commit", expire)
    try:
        response = send(case, record=case["item"].id)
        assert response.status_code == 401 and "item" not in response.json()
    finally:
        event.remove(case["engine"], "commit", expire)
