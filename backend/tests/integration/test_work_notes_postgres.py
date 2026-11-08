"""Revision-bound current-human changes, metadata-only cleanup and atomic copy redaction."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from work_migration_helpers import assert_downgrade_refused
from work_storage_helpers import connect

from app import (
    work_capture,
    work_capture_worker,
    work_drafts,
    work_lifecycle,
    work_notes,
    work_notes_worker,
    work_parties,
    work_read,
)
from app.main import app
from app.models import User
from app.work_manage import administer
from app.work_notes_storage import provision_changes

pytestmark = pytest.mark.integration


@pytest.fixture
def note_case(review_case):
    case = review_case
    with connect() as db:
        provision_changes(db, case["slug"])
    app.dependency_overrides[work_notes.get_change_engines] = lambda: work_read.WorkspaceEngines(
        {case["workspace"]: case["engine"]}
    )
    app.dependency_overrides[work_capture.get_capture_engines] = lambda: work_read.WorkspaceEngines(
        {case["workspace"]: case["engine"]}
    )
    try:
        yield case
    finally:
        app.dependency_overrides.pop(work_notes.get_change_engines, None)
        app.dependency_overrides.pop(work_capture.get_capture_engines, None)


def body(case, action="correct", revision=1):
    result = {
        "request_id": str(uuid4()),
        "decision": f"{action}_note",
        "expected_revision": revision,
    }
    if action == "correct":
        result["draft"] = {
            "kind": "decision",
            "marker": "synthetic:human-corrected",
            "source_ids": [str(case["source"])],
            "owner_id": None,
            "due_at": None,
            "retain_until": case["item"].retain_until.isoformat(),
        }
    return result


def send(case, action="correct", value=None, command=None, record=None):
    suffix = (
        f"note-changes/{command}/status"
        if command
        else f"drafts/{record or case['item'].id}/{action}"
    )
    return case["client"].post(
        f"/api/v1/work/workspaces/{case['workspace']}/{suffix}",
        json={} if command else value or body(case, action),
        headers=case["headers"],
    )


def prepare(case, action="correct", value=None):
    response = send(case, action, value)
    assert response.status_code == 202, response.text
    return UUID(response.json()["change_request_id"])


def execute(command):
    with connect() as db, db.transaction():
        return work_notes_worker.execute(db, command)


def stored(case):
    with connect() as db:
        return db.execute(
            "SELECT id,intent,state,payload,payload_hash,result_revision,reason_code FROM work.capture_intents WHERE workspace_id=%s ORDER BY prepared_at",
            (case["workspace"],),
        ).fetchall()


def current(case):
    with connect() as db:
        return db.execute(
            "SELECT revision,state,snapshot FROM work.drafts WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["item"].id),
        ).fetchone()


def test_correct_then_forget_are_once_and_history_redacted(note_case):
    case = note_case
    value = body(case)
    correction = prepare(case, value=value)
    replay = send(case, value=value)
    assert replay.status_code == 202 and replay.json()["replayed"]
    applied = execute(correction)
    assert applied == {"state": "applied", "record_id": str(case["item"].id), "revision": 2}
    assert execute(correction) == applied
    assert (
        current(case)[:2] == (2, "draft")
        and current(case)[2]["marker"] == "synthetic:human-corrected"
    )
    assert send(case, command=correction).json()["revision"] == 2
    forget = prepare(case, "forget", body(case, "forget", 2))
    assert execute(forget)["revision"] == 3
    assert current(case)[:2] == (3, "forgotten")
    assert current(case)[2]["marker"] is None and current(case)[2]["owner_id"] is None
    assert all(row[3] is None and row[4] is None for row in stored(case))
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_revisions WHERE workspace_id=%s AND record_id=%s AND snapshot IS NOT NULL",
                (case["workspace"], case["item"].id),
            ).fetchone()[0]
            == 0
        )
    assert execute(forget)["revision"] == 3


def test_confirmed_note_correction_returns_to_draft_without_reconfirmation(note_case):
    case = note_case
    with connect() as db, db.transaction():
        work_drafts.transition(db, case["workspace"], case["actor"], case["item"].id, 1, "confirm")
    command = prepare(case, value=body(case, revision=2))
    assert execute(command)["revision"] == 3 and current(case)[:2] == (3, "draft")


@pytest.mark.parametrize("fault", ["stale", "kind", "extend", "owner", "source"])
def test_invalid_correction_never_prepares(note_case, fault):
    case = note_case
    value = body(case)
    if fault == "stale":
        value["expected_revision"] = 2
    elif fault == "kind":
        value["draft"]["kind"] = "action"
    elif fault == "extend":
        value["draft"]["retain_until"] = (
            case["item"].retain_until + timedelta(hours=1)
        ).isoformat()
    elif fault == "owner":
        value["draft"]["owner_id"] = str(uuid4())
    else:
        value["draft"]["source_ids"] = [str(uuid4())]
    response = send(case, value=value)
    assert response.status_code == (404 if fault in {"owner", "source"} else 409)
    assert stored(case) == [] and current(case)[0] == 1


def test_metadata_only_forget_works_when_source_content_is_hidden(note_case):
    case = note_case
    with connect() as db:
        db.execute(
            "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
            (case["workspace"],),
        )
    with case["storage"]["session"]() as db:
        assert db.execute("SELECT snapshot FROM work.drafts").fetchall() == []
        metadata = db.execute("SELECT id,revision,state FROM work.note_metadata").fetchall()
        assert metadata == [(case["item"].id, 1, "draft")]
    assert send(case).status_code == 404
    command = prepare(case, "forget")
    assert execute(command)["state"] == "applied" and current(case)[1] == "forgotten"


def test_forget_expired_note_uses_no_payload_read(note_case):
    case = note_case
    with connect() as db, db.transaction():
        case["item"] = work_drafts.create(
            db,
            case["workspace"],
            case["actor"],
            case["policy"],
            work_lifecycle.Draft(
                kind="decision",
                marker="synthetic:expiring-note",
                source_ids=(case["source"],),
                retain_until=datetime.now(UTC) + timedelta(milliseconds=250),
            ),
        )
    with connect() as db:
        db.execute("SELECT pg_sleep(0.3)")
    command = prepare(case, "forget")
    assert execute(command)["state"] == "applied" and current(case)[1] == "forgotten"


def test_forget_atomically_denies_and_redacts_pending_corrections(note_case):
    case = note_case
    correction = prepare(case)
    forget = prepare(case, "forget")
    assert execute(forget)["state"] == "applied"
    records = {row[0]: row for row in stored(case)}
    assert (
        records[correction][2:5] == ("denied", None, None)
        and records[correction][-1] == "forgotten"
    )
    assert execute(correction) == {"state": "denied", "record_id": None, "revision": None}
    assert current(case)[0] == 2


@pytest.mark.parametrize("fault", ["source", "party", "grant", "revision"])
def test_fresh_execution_rejects_changed_authority_and_target(note_case, fault):
    case = note_case
    value = body(case)
    if fault == "party":
        with connect() as db, db.transaction():
            party = work_parties.create(
                db,
                case["workspace"],
                case["policy"],
                "synthetic:change-owner",
                datetime.now(UTC) + timedelta(hours=1),
            )
        value["draft"]["owner_id"] = str(party.id)
    command = prepare(case, value=value)
    if fault == "source":
        with connect() as db:
            db.execute(
                "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
                (case["workspace"],),
            )
    elif fault == "party":
        with connect() as db, db.transaction():
            work_parties.transition(db, case["workspace"], party.id, 1, "retire")
    elif fault == "grant":
        with case["maker"].begin() as db:
            administer(db, "revoke", case["slug"], db.get(User, case["actor"]).slug)
    else:
        with connect() as db, db.transaction():
            work_drafts.transition(
                db,
                case["workspace"],
                case["actor"],
                case["item"].id,
                1,
                "correct",
                work_lifecycle.Draft(
                    kind="decision",
                    marker="synthetic:other-edit",
                    source_ids=(case["source"],),
                    retain_until=case["item"].retain_until,
                ),
            )
    assert execute(command)["state"] == "denied"
    assert stored(case)[0][3:5] == (None, None)


def test_orphan_change_is_denied_without_note_write(note_case):
    case = note_case

    def fail(session):
        if session.bind is not None and session.bind.url.username == "butler_runtime":
            raise SQLAlchemyError("synthetic note identity failure")

    event.listen(Session, "before_commit", fail)
    try:
        response = send(case)
    finally:
        event.remove(Session, "before_commit", fail)
    assert response.status_code == 503
    assert execute(stored(case)[0][0])["state"] == "denied" and current(case)[0] == 1


@pytest.mark.parametrize("fault", ["draft", "intent", "public", "scrub"])
def test_application_and_pending_copy_redaction_roll_back_on_audit_failure(note_case, fault):
    case = note_case
    correction = prepare(case)
    command = correction if fault != "scrub" else prepare(case, "forget")
    table, event_type = {
        "draft": ("work.draft_audit", "draft.corrected"),
        "intent": ("work.capture_audit", "capture.applied"),
        "public": ("public.audit_events", "work.note_change_finished"),
        "scrub": ("work.capture_audit", "capture.denied"),
    }[fault]
    name = "synthetic_note_audit_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} CHECK(event_type<>{}) NOT VALID").format(
                sql.SQL(table), sql.Identifier(name), sql.Literal(event_type)
            )
        )
    try:
        with pytest.raises(psycopg.Error):
            execute(command)
        assert current(case)[0] == 1 and current(case)[1] == "draft"
        assert stored(case)[0][2] == "pending" and stored(case)[0][3] is not None
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                    sql.SQL(table), sql.Identifier(name)
                )
            )


def test_duplicate_and_competing_changes_serialize_without_double_revision(note_case):
    case = note_case
    correction = prepare(case)
    forget = prepare(case, "forget")
    start = Barrier(2)

    def apply(command):
        start.wait(timeout=5)
        return execute(command)

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(apply, correction), pool.submit(apply, forget)
        results = [a.result(timeout=15), b.result(timeout=15)]
    assert sorted(result["state"] for result in results) == ["applied", "denied"]
    assert current(case)[0] == 2
    for command in (correction, forget):
        assert execute(command)["state"] in {"applied", "denied"}


def test_capture_and_note_change_handles_cannot_cross_handlers(note_case):
    case = note_case
    command = prepare(case)
    response = case["client"].post(
        f"/api/v1/work/workspaces/{case['workspace']}/captures/{command}/status",
        json={},
        headers=case["headers"],
    )
    assert response.status_code == 404
    with pytest.raises(ValueError), connect() as db, db.transaction():
        work_capture_worker.execute(db, command)


def test_metadata_view_does_not_cross_workspace_and_role_cannot_apply(note_case):
    case = note_case
    command = prepare(case)
    with connect() as db:
        db.execute(
            sql.SQL("GRANT SELECT ON work.note_metadata TO {}").format(
                sql.Identifier(case["storage"]["b"]["role"])
            )
        )
    with case["storage"]["session"]("b") as db:
        assert db.execute("SELECT * FROM work.note_metadata").fetchall() == []
    with pytest.raises(psycopg.Error), case["storage"]["session"]() as db:
        db.execute("UPDATE work.capture_intents SET state='applied' WHERE id=%s", (command,))
    with pytest.raises(psycopg.Error), case["storage"]["session"]() as db:
        db.execute("UPDATE work.note_metadata SET state='forgotten'")


def test_nonce_action_target_and_session_bindings(note_case):
    from conftest import SYNTHETIC_PASSWORD

    case = note_case
    value = body(case)
    command = prepare(case, value=value)
    value["draft"]["marker"] = "synthetic:nonce-conflict"
    assert send(case, value=value).status_code == 409
    forgotten = body(case, "forget")
    forgotten["request_id"] = value["request_id"]
    assert send(case, "forget", forgotten).status_code == 409
    with case["maker"]() as db:
        slug = db.get(User, case["actor"]).slug
    login = case["client"].post(
        "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
    )
    case["headers"] = {"X-CSRF-Token": login.json()["csrf_token"]}
    assert send(case, command=command).status_code == 404


def test_change_payload_never_enters_identity_audit(note_case):
    case = note_case
    command = prepare(case)
    execute(command)
    with connect() as db:
        metadata = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE entity_id=%s AND event_type IN ('work.note_change_requested','work.note_change_finished')",
            (str(case["workspace"]),),
        ).fetchall()
    encoded = json.dumps(metadata)
    assert len(metadata) == 2
    for secret in (
        "synthetic:human-corrected",
        str(case["source"]),
        str(case["policy"]),
        "payload_hash",
    ):
        assert secret not in encoded


def test_deferred_forget_failure_restores_note_and_pending_copies(note_case):
    case = note_case
    correction = prepare(case)
    forget = prepare(case, "forget")
    name = "synthetic_note_commit_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "CREATE FUNCTION work.{}() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN RAISE EXCEPTION 'synthetic deferred note failure' USING ERRCODE='23514'; END; $$"
            ).format(sql.Identifier(name))
        )
        db.execute(
            sql.SQL(
                "CREATE CONSTRAINT TRIGGER {} AFTER UPDATE ON work.capture_intents DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN(NEW.intent='forget_note' AND NEW.state='applied') EXECUTE FUNCTION work.{}()"
            ).format(sql.Identifier(name), sql.Identifier(name))
        )
    try:
        with pytest.raises(psycopg.Error):
            execute(forget)
        assert current(case)[0:2] == (1, "draft")
        records = {row[0]: row for row in stored(case)}
        assert records[correction][2] == "pending" and records[correction][3] is not None
        assert records[forget][2] == "pending"
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("DROP TRIGGER {} ON work.capture_intents").format(sql.Identifier(name))
            )
            db.execute(sql.SQL("DROP FUNCTION work.{}()").format(sql.Identifier(name)))


def test_post_write_expiry_rolls_back_forget_and_correction_redaction(note_case, monkeypatch):
    case = note_case
    prepare(case)
    forget = prepare(case, "forget")
    original = work_drafts._now

    def expire(db):
        outcome = db.execute(
            "SELECT state,expires_at FROM work.capture_intents WHERE id=%s", (forget,)
        ).fetchone()
        return outcome[1] + timedelta(seconds=1) if outcome[0] == "applied" else original(db)

    monkeypatch.setattr(work_drafts, "_now", expire)
    with pytest.raises(ValueError, match="expired during write"):
        execute(forget)
    assert current(case)[0:2] == (1, "draft")
    assert all(row[2] == "pending" and row[3] is not None for row in stored(case))


def test_expired_correction_is_denied_and_redacted(note_case):
    case = note_case
    value = body(case)
    value["draft"]["retain_until"] = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    command = prepare(case, value=value)
    with connect() as db:
        db.execute("SELECT pg_sleep(1.1)")
    assert execute(command)["state"] == "denied"
    assert stored(case)[0][3:5] == (None, None) and current(case)[0] == 1


def test_note_change_evidence_blocks_destructive_downgrade(note_case):
    case = note_case
    prepare(case)
    assert_downgrade_refused(
        "0014_work_capture", "0015_work_note_changes", "Note-change evidence exists"
    )
    assert stored(case)[0][2] == "pending" and current(case)[0] == 1


def test_unprovisioned_workspace_role_has_no_metadata_view_access(storage_case):
    with pytest.raises(psycopg.errors.InsufficientPrivilege), storage_case["session"]() as db:
        db.execute("SELECT * FROM work.note_metadata")
