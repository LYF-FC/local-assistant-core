"""Current, scoped, hash-bound archives and honest receipt failure paths."""

import json
import time
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from psycopg import sql
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from work_storage_helpers import connect

from app import identity, work_drafts, work_interface, work_lifecycle, work_parties, work_read
from app.config import settings
from app.main import app
from app.work_notes_storage import provision_changes

pytestmark = pytest.mark.integration


@pytest.fixture
def export_case(review_case, monkeypatch):
    case = review_case
    with connect() as db:
        provision_changes(db, case["slug"])
    monkeypatch.setattr(settings, "work_notes_interface_enabled", True)
    monkeypatch.setattr(settings, "work_notes_export_enabled", True)
    app.dependency_overrides[work_interface.get_export_engines] = lambda: (
        work_read.WorkspaceEngines({case["workspace"]: case["engine"]})
    )
    try:
        yield case
    finally:
        app.dependency_overrides.pop(work_interface.get_export_engines, None)


def send(case, body=None, workspace=None):
    value = {
        "purpose": "preview",
        "include_drafts": True,
        "selections": [{"id": str(case["item"].id), "expected_revision": case["item"].revision}],
    }
    value.update(body or {})
    return case["client"].post(
        f"/api/v1/work/workspaces/{workspace or case['workspace']}/notes/export",
        json=value,
        headers=case["headers"],
    )


def download(case, preview, **change):
    return send(
        case,
        {
            "purpose": "download",
            "acknowledge_copy_limits": True,
            "reviewed_hash": preview["reviewed_hash"],
            **change,
        },
    )


def test_fresh_download_preserves_unknowns_provenance_and_metadata_receipt(export_case):
    case = export_case
    first = send(case)
    assert first.status_code == 200, first.text
    preview, bundle = first.json(), first.json()["bundle"]
    assert (
        bundle["items"][0]["item"]["owner_id"] is None
        and bundle["items"][0]["item"]["due_at"] is None
    )
    assert bundle["items"][0]["references"]["sources"][0]["id"] == str(case["source"])
    assert (
        not bundle["managed_copy"]
        and not bundle["raw_transcripts_included"]
        and bundle["current_revisions_only"]
    )
    assert case["item"].retain_until == datetime.fromisoformat(bundle["retain_until"])
    assert len(work_interface._canonical(bundle)) == preview["bundle_bytes"] <= 32768
    result = download(case, preview)
    assert result.status_code == 200, result.text
    assert result.json()["reviewed_hash"] == preview["reviewed_hash"]
    assert result.json()["bundle"]["export_id"] != bundle[
        "export_id"
    ] and "payload_hash" not in json.dumps(bundle)
    with connect() as db:
        events = db.execute(
            "SELECT event_type,metadata_json FROM public.audit_events WHERE entity_id=%s AND event_type LIKE 'work.notes_export_%%_prepared'",
            (str(case["workspace"]),),
        ).fetchall()
    assert len(events) == 2
    assert all(row[1]["drafts_permitted"] is True for row in events)
    encoded = json.dumps(events)
    assert "synthetic:review-note" not in encoded and preview["reviewed_hash"] not in encoded
    assert all(row[1]["records"] == [{"id": str(case["item"].id), "revision": 1}] for row in events)


def test_drafts_need_explicit_inclusion_and_confirmed_default_is_accepted(export_case):
    case = export_case
    assert send(case, {"include_drafts": False}).status_code == 404
    with connect() as db, db.transaction():
        work_drafts.transition(db, case["workspace"], case["actor"], case["item"].id, 1, "confirm")
    result = send(
        case,
        {
            "include_drafts": False,
            "selections": [{"id": str(case["item"].id), "expected_revision": 2}],
        },
    )
    assert (
        result.status_code == 200
        and result.json()["bundle"]["items"][0]["item"]["state"] == "confirmed"
    )


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("stale", 409),
        ("source", 404),
        ("workspace", 404),
        ("missing", 404),
        ("forgotten", 404),
        ("expired", 404),
    ],
)
def test_unavailable_or_changed_selection_has_no_partial_archive(export_case, fault, expected):
    case = export_case
    body, workspace = {}, None
    if fault == "stale":
        body = {"selections": [{"id": str(case["item"].id), "expected_revision": 2}]}
    elif fault == "workspace":
        workspace = case["storage"]["b"]["workspace"]
    elif fault == "missing":
        body = {
            "selections": [
                {"id": str(case["item"].id), "expected_revision": 1},
                {"id": str(uuid4()), "expected_revision": 1},
            ]
        }
    elif fault == "forgotten":
        with connect() as db, db.transaction():
            work_drafts.transition(
                db, case["workspace"], case["actor"], case["item"].id, 1, "forget"
            )
    elif fault == "expired":
        with connect() as db, db.transaction():
            case["item"] = work_drafts.transition(
                db,
                case["workspace"],
                case["actor"],
                case["item"].id,
                1,
                "correct",
                work_lifecycle.Draft(
                    kind="decision",
                    marker="synthetic:short-export",
                    source_ids=(case["source"],),
                    retain_until=identity.now_utc() + timedelta(seconds=2),
                ),
            )
        time.sleep(2.1)
    else:
        with connect() as db:
            db.execute(
                "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
                (case["workspace"],),
            )
    response = send(case, body, workspace)
    assert (
        response.status_code == expected
        and "bundle" not in response.json()
        and "review-note" not in response.text
    )


def test_download_rechecks_references_at_same_note_revision(export_case):
    case = export_case
    with connect() as db, db.transaction():
        owner = work_parties.create(
            db,
            case["workspace"],
            case["policy"],
            "synthetic:export-owner",
            identity.now_utc() + timedelta(minutes=30),
        )
        case["item"] = work_drafts.create(
            db,
            case["workspace"],
            case["actor"],
            case["policy"],
            work_lifecycle.Draft(
                kind="action",
                marker="synthetic:owned-export",
                source_ids=(case["source"],),
                owner_id=owner.id,
                retain_until=identity.now_utc() + timedelta(hours=1),
            ),
        )
    preview = send(case).json()
    assert datetime.fromisoformat(preview["bundle"]["retain_until"]) == owner.retain_until
    with connect() as db, db.transaction():
        work_parties.transition(db, case["workspace"], owner.id, 1, "retire")
    result = download(case, preview)
    assert result.status_code == 409 and "bundle" not in result.json()


def test_download_requires_exact_reviewed_hash(export_case):
    case = export_case
    preview = send(case).json()
    assert download(case, preview, reviewed_hash="0" * 64).status_code == 409


def test_private_audit_or_public_commit_failure_releases_no_archive(export_case):
    case = export_case
    name = "synthetic_export_audit_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE work.draft_audit ADD CONSTRAINT {} CHECK(event_type<>'draft.read_prepared') NOT VALID"
            ).format(sql.Identifier(name))
        )
    try:
        result = send(case)
        assert result.status_code == 503 and "bundle" not in result.json()
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE work.draft_audit DROP CONSTRAINT {}").format(
                    sql.Identifier(name)
                )
            )

    def fail(session):
        if session.bind is not None and session.bind.url.username == "butler_runtime":
            raise SQLAlchemyError("synthetic export commit failure")

    event.listen(Session, "before_commit", fail)
    try:
        result = send(case)
        assert result.status_code == 503 and "bundle" not in result.json()
    finally:
        event.remove(Session, "before_commit", fail)


def test_expiry_during_identity_commit_releases_no_archive(export_case, monkeypatch):
    case = export_case
    now = identity.now_utc()

    def advance(session):
        monkeypatch.setattr(identity, "now_utc", lambda: now + timedelta(hours=2))

    event.listen(Session, "after_commit", advance)
    try:
        result = send(case)
        assert result.status_code == 409 and "bundle" not in result.json()
    finally:
        event.remove(Session, "after_commit", advance)


def test_download_rechecks_version_after_preview(export_case):
    case = export_case
    preview = send(case).json()
    with connect() as db, db.transaction():
        work_drafts.transition(db, case["workspace"], case["actor"], case["item"].id, 1, "confirm")
    assert download(case, preview).status_code == 409


def test_archive_byte_ceiling_never_truncates_selected_records(export_case):
    case = export_case
    with connect() as db, db.transaction():
        sources = tuple(uuid4() for _ in range(10))
        for source in sources:
            db.execute(
                "INSERT INTO work.validation_records(workspace_id,id,marker) VALUES(%s,%s,%s)",
                (case["workspace"], source, "synthetic:" + "x" * 246),
            )
            db.execute(
                "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
                (case["workspace"], source),
            )
        notes = [
            work_drafts.create(
                db,
                case["workspace"],
                case["actor"],
                case["policy"],
                work_lifecycle.Draft(
                    kind="observation",
                    marker="synthetic:" + "y" * 246,
                    source_ids=sources,
                    retain_until=identity.now_utc() + timedelta(hours=1),
                ),
            )
            for _ in range(10)
        ]
    result = send(case, {"selections": [{"id": str(n.id), "expected_revision": 1} for n in notes]})
    assert result.status_code == 413 and "bundle" not in result.json()


@pytest.mark.parametrize("fault", ["grant", "source"])
def test_download_rechecks_authority_and_sources_after_preview(export_case, fault):
    case = export_case
    preview = send(case).json()
    if fault == "grant":
        from app.models import User
        from app.work_manage import administer

        with case["maker"].begin() as db:
            administer(db, "revoke", case["slug"], db.get(User, case["actor"]).slug)
    else:
        with connect() as db:
            db.execute(
                "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
                (case["workspace"],),
            )
    response = download(case, preview)
    assert response.status_code == 404 and "bundle" not in response.json()
