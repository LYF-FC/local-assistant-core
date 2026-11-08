"""Committed identity intent plus same-database, one-time synthetic application."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import psycopg
import pytest
from conftest import RUNTIME_PASSWORD
from psycopg import sql
from sqlalchemy import event
from sqlalchemy.orm import Session
from test_work_review_postgres import request, send
from work_storage_helpers import connect

from app import work_confirmation, work_drafts
from app import work_confirmation_worker as worker
from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
def confirmation_case(review_case):
    case = review_case
    app.dependency_overrides[work_confirmation.get_confirmation_engines] = lambda: (
        work_confirmation.work_read.WorkspaceEngines({case["workspace"]: case["engine"]})
    )
    try:
        yield case
    finally:
        app.dependency_overrides.pop(work_confirmation.get_confirmation_engines, None)


def queue(case):
    review = send(case, "review", request(case))
    assert review.status_code == 200
    body = {
        "review_preparation_id": review.json()["review_preparation_id"],
        "expected_revision": 1,
        "decision": "confirm_note",
        "request_id": str(uuid4()),
    }
    response = send(case, "confirm", body)
    assert response.status_code == 202, response.text
    return UUID(response.json()["confirmation_request_id"]), body


def execute(command):
    with connect() as db, db.transaction():
        return worker.execute(db, command)


def state(case, command):
    with connect() as db:
        return db.execute(
            "SELECT r.state,d.state,d.revision,(SELECT count(*) FROM work.draft_confirmations WHERE request_id=r.id) FROM public.work_confirmation_requests r JOIN work.drafts d ON d.workspace_id=r.workspace_id AND d.id=r.record_id WHERE r.id=%s",
            (command,),
        ).fetchone()


def test_confirmation_applies_exact_review_once_and_status_is_historical(confirmation_case):
    case = confirmation_case
    command, body = queue(case)
    assert state(case, command) == ("pending", "draft", 1, 0)
    assert send(case, "confirm", body).json()["confirmation_request_id"] == str(command)
    assert execute(command) == {"state": "applied", "applied_revision": 2}
    assert execute(command) == {"state": "applied", "applied_revision": 2}
    assert state(case, command) == ("applied", "confirmed", 2, 1)
    status = case["client"].post(
        f"/api/v1/work/workspaces/{case['workspace']}/confirmations/{command}/status",
        json={},
        headers=case["headers"],
    )
    assert status.status_code == 200 and status.json()["confirmation_applied"] is True
    assert "synthetic:review-note" not in status.text
    with connect() as db, db.transaction():
        work_drafts.transition(db, case["workspace"], case["actor"], case["item"].id, 2, "forget")
    assert execute(command)["state"] == "applied"
    with connect() as db:
        assert db.execute(
            "SELECT payload_hash FROM work.draft_reviews WHERE workspace_id=%s AND id=%s",
            (case["workspace"], UUID(body["review_preparation_id"])),
        ).fetchone() == (None,)
        assert db.execute(
            "SELECT count(*) FROM work.draft_audit WHERE workspace_id=%s AND record_id=%s AND event_type='draft.confirmed'",
            (case["workspace"], case["item"].id),
        ).fetchone() == (1,)


def test_nonce_conflict_and_receipt_replay(confirmation_case):
    case = confirmation_case
    command, body = queue(case)
    assert send(case, "confirm", dict(body, expected_revision=2)).status_code == 409
    assert send(case, "confirm", dict(body, request_id=str(uuid4()))).json()[
        "confirmation_request_id"
    ] == str(command)
    assert send(case, "confirm", dict(body, review_preparation_id=str(uuid4()))).status_code == 409


@pytest.mark.parametrize(
    "change",
    ["source", "workspace", "grant", "user", "session", "idle", "expired", "correct", "forget"],
)
def test_worker_rechecks_fresh_authority_content_and_sources(confirmation_case, change):
    case = confirmation_case
    command, _ = queue(case)
    with connect() as db, db.transaction():
        if change == "source":
            db.execute(
                "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s AND id=%s",
                (case["workspace"], case["source"]),
            )
        elif change == "workspace":
            db.execute(
                "UPDATE public.work_workspaces SET is_active=false WHERE id=%s",
                (case["workspace"],),
            )
        elif change == "grant":
            db.execute(
                "DELETE FROM public.work_access_grants WHERE workspace_id=%s AND user_id=%s",
                (case["workspace"], case["actor"]),
            )
        elif change == "user":
            db.execute("UPDATE public.users SET is_active=false WHERE id=%s", (case["actor"],))
        elif change in {"session", "idle", "expired"}:
            assignment = {
                "session": "revoked_at=clock_timestamp()",
                "idle": "last_seen_at=clock_timestamp()-interval '31 minutes'",
                "expired": "expires_at=clock_timestamp()-interval '1 second'",
            }[change]
            db.execute(
                sql.SQL("UPDATE public.auth_sessions SET " + assignment + " WHERE user_id=%s"),
                (case["actor"],),
            )
        else:
            payload = case["item"].model_dump(
                include={"kind", "marker", "source_ids", "retain_until", "owner_id"}
            )
            work_drafts.transition(
                db,
                case["workspace"],
                case["actor"],
                case["item"].id,
                1,
                change,
                work_confirmation.work_review.work_lifecycle.Draft(**payload)
                if change == "correct"
                else None,
            )
    assert execute(command)["state"] == "denied"
    assert state(case, command)[0] == "denied" and state(case, command)[3] == 0


def test_orphan_private_review_without_committed_identity_evidence_is_denied(confirmation_case):
    case = confirmation_case

    # Audit insertion failure is a SQLAlchemy error caught by route wrapper.
    def fail_audit(session):
        if session.get_bind().url.username == "butler_runtime":
            from sqlalchemy.exc import SQLAlchemyError

            raise SQLAlchemyError("synthetic identity commit")

    review_body = request(case)
    event.listen(Session, "before_commit", fail_audit)
    try:
        response = send(case, "review", review_body)
        assert response.status_code == 503
    finally:
        event.remove(Session, "before_commit", fail_audit)
    with connect() as db:
        row = db.execute(
            "SELECT id,session_id FROM work.draft_reviews WHERE workspace_id=%s AND record_id=%s",
            (case["workspace"], case["item"].id),
        ).fetchone()
    assert row is not None
    body = {
        "review_preparation_id": str(row[0]),
        "expected_revision": 1,
        "decision": "confirm_note",
        "request_id": str(uuid4()),
    }
    response = send(case, "confirm", body)
    assert response.status_code == 202
    command = UUID(response.json()["confirmation_request_id"])
    assert execute(command)["state"] == "denied"
    assert state(case, command) == ("denied", "draft", 1, 0)


@pytest.mark.parametrize("failure", ["ledger", "private_audit", "outcome_audit", "commit"])
def test_failure_rolls_back_confirmation_history_consumption_and_status(confirmation_case, failure):
    case = confirmation_case
    command, _ = queue(case)
    target = {
        "ledger": "work.draft_confirmations",
        "commit": "work.draft_confirmations",
        "private_audit": "work.draft_audit",
        "outcome_audit": "public.audit_events",
    }[failure]
    timing = "AFTER" if failure == "commit" else "BEFORE"
    condition = {
        "private_audit": "WHEN (NEW.event_type='draft.confirmed')",
        "outcome_audit": "WHEN (NEW.event_type='work.draft_confirmation_finished')",
    }.get(failure, "")
    with connect() as db:
        db.execute(
            "CREATE FUNCTION work.synthetic_fail_confirmation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic transaction failure'; END; $$"
        )
        if failure == "commit":
            db.execute(
                "CREATE CONSTRAINT TRIGGER synthetic_fail_confirmation AFTER INSERT ON work.draft_confirmations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION work.synthetic_fail_confirmation()"
            )
        else:
            db.execute(
                sql.SQL(
                    "CREATE TRIGGER synthetic_fail_confirmation "
                    + timing
                    + " INSERT ON "
                    + target
                    + " FOR EACH ROW "
                    + condition
                    + " EXECUTE FUNCTION work.synthetic_fail_confirmation()"
                )
            )
    try:
        with pytest.raises(psycopg.Error), connect() as db, db.transaction():
            worker.execute(db, command)
    finally:
        with connect() as db:
            db.execute(sql.SQL("DROP TRIGGER synthetic_fail_confirmation ON " + target))
            db.execute("DROP FUNCTION work.synthetic_fail_confirmation()")
    assert state(case, command) == ("pending", "draft", 1, 0)
    with connect() as db:
        assert db.execute(
            "SELECT count(*) FROM work.draft_revisions WHERE workspace_id=%s AND record_id=%s",
            (case["workspace"], case["item"].id),
        ).fetchone() == (1,)
        assert db.execute(
            "SELECT count(*) FROM work.draft_audit WHERE workspace_id=%s AND record_id=%s AND event_type='draft.confirmed'",
            (case["workspace"], case["item"].id),
        ).fetchone() == (0,)


def test_two_workers_apply_only_one_confirmation(confirmation_case):
    case = confirmation_case
    command, _ = queue(case)
    barrier = Barrier(2)

    def run():
        barrier.wait(timeout=5)
        return execute(command)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert results == [{"state": "applied", "applied_revision": 2}] * 2
    assert state(case, command) == ("applied", "confirmed", 2, 1)


def test_api_credential_cannot_mutate_outcome_or_call_owner_executor(confirmation_case):
    case = confirmation_case
    command, _ = queue(case)
    with connect(user="butler_runtime", password=RUNTIME_PASSWORD) as db:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
            db.execute(
                "UPDATE public.work_confirmation_requests SET state='applied' WHERE id=%s",
                (command,),
            )
        # PostgreSQL rejects the API credential at the schema boundary before
        # the executor can even inspect the owner profile. Keep that ACL strict.
        with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
            worker.execute(db, command)
    with connect() as db, pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute("DELETE FROM public.work_confirmation_requests WHERE id=%s", (command,))
    assert state(case, command) == ("pending", "draft", 1, 0)


def test_enqueue_commit_failure_does_not_leave_a_pending_command(confirmation_case):
    case = confirmation_case
    reviewed = send(case, "review", request(case)).json()
    body = {
        "review_preparation_id": reviewed["review_preparation_id"],
        "expected_revision": 1,
        "decision": "confirm_note",
        "request_id": str(uuid4()),
    }

    def fail(session):
        if session.get_bind().url.username == "butler_runtime":
            from sqlalchemy.exc import SQLAlchemyError

            raise SQLAlchemyError("synthetic enqueue commit failure")

    event.listen(Session, "before_commit", fail)
    try:
        assert send(case, "confirm", body).status_code == 503
    finally:
        event.remove(Session, "before_commit", fail)
    with connect() as db:
        assert db.execute(
            "SELECT count(*) FROM public.work_confirmation_requests WHERE workspace_id=%s",
            (case["workspace"],),
        ).fetchone() == (0,)
    assert send(case, "confirm", body).status_code == 202


def test_new_session_cannot_reuse_review_or_inspect_old_status(confirmation_case):
    from conftest import SYNTHETIC_PASSWORD

    case = confirmation_case
    command, body = queue(case)
    with connect() as db:
        slug = db.execute("SELECT slug FROM users WHERE id=%s", (case["actor"],)).fetchone()[0]
    login = case["client"].post(
        "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
    )
    case["headers"] = {"X-CSRF-Token": login.json()["csrf_token"]}
    assert send(case, "confirm", body).status_code == 409
    response = case["client"].post(
        f"/api/v1/work/workspaces/{case['workspace']}/confirmations/{command}/status",
        json={},
        headers=case["headers"],
    )
    assert response.status_code == 404


def test_expired_request_is_denied_without_consumption(confirmation_case, monkeypatch):
    from datetime import timedelta

    case = confirmation_case
    command, _ = queue(case)
    now = worker.work_drafts._now
    monkeypatch.setattr(worker.work_drafts, "_now", lambda db: now(db) + timedelta(minutes=6))
    assert execute(command)["state"] == "denied"
    assert state(case, command) == ("denied", "draft", 1, 0)


def test_request_without_committed_enqueue_evidence_cannot_apply(confirmation_case):
    case = confirmation_case
    reviewed = send(case, "review", request(case)).json()
    with connect() as db:
        command = db.execute(
            "INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) SELECT workspace_id,record_id,id,revision,actor_id,session_id,%s,expires_at FROM work.draft_reviews WHERE workspace_id=%s AND id=%s RETURNING id",
            (uuid4(), case["workspace"], UUID(reviewed["review_preparation_id"])),
        ).fetchone()[0]
    assert execute(command)["state"] == "denied"
    assert state(case, command) == ("denied", "draft", 1, 0)


def test_worker_waits_for_revocation_then_uses_fresh_grant(confirmation_case):
    from threading import Event

    from test_work_authority_postgres import wait_for_advisory

    from app.work_authority import REGISTRY_KEY

    case = confirmation_case
    command, _ = queue(case)
    ready = Event()
    pid = []

    def blocked():
        with connect() as db, db.transaction():
            pid.append(db.info.backend_pid)
            ready.set()
            return worker.execute(db, command)

    with connect() as holder, ThreadPoolExecutor(max_workers=1) as pool:
        holder.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
        future = pool.submit(blocked)
        assert ready.wait(2)
        wait_for_advisory(case["maker"].kw["bind"], pid[0])
        holder.execute(
            "DELETE FROM public.work_access_grants WHERE workspace_id=%s AND user_id=%s",
            (case["workspace"], case["actor"]),
        )
        holder.commit()
        assert future.result(timeout=5)["state"] == "denied"
    assert state(case, command) == ("denied", "draft", 1, 0)


@pytest.mark.parametrize("terminal", ["retire", "forget"])
def test_party_retirement_after_queue_denies_confirmation_without_consumption(
    confirmation_case, terminal
):
    from datetime import UTC, datetime, timedelta

    from app import work_lifecycle, work_parties

    case = confirmation_case
    with connect() as db, db.transaction():
        party = work_parties.create(
            db,
            case["workspace"],
            case["policy"],
            "synthetic:confirmation-owner",
            datetime.now(UTC) + timedelta(hours=1),
        )
        case["item"] = work_drafts.create(
            db,
            case["workspace"],
            case["actor"],
            case["policy"],
            work_lifecycle.Draft(
                kind="action",
                marker="synthetic:party-confirmation",
                owner_id=party.id,
                source_ids=(case["source"],),
                retain_until=datetime.now(UTC) + timedelta(hours=1),
            ),
        )
    command, _ = queue(case)
    with connect() as db, db.transaction():
        work_parties.transition(db, case["workspace"], party.id, 1, terminal)
    result = execute(command)
    assert result == {"state": "denied", "applied_revision": None}
    assert state(case, command) == ("denied", "draft", 1, 0)
