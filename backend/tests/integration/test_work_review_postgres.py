"""Actual current-session review through a restricted workspace login."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from time import monotonic
from uuid import uuid4

import psycopg
import pytest
from conftest import client_for
from psycopg import sql
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from test_work_authority_postgres import wait_for_advisory
from work_storage_helpers import connect

from app import identity, work_drafts, work_lifecycle
from app.models import AuthSession, User
from app.work_manage import administer

pytestmark = pytest.mark.integration


def send(case, action="preview", body=None, workspace=None, record=None, client=None):
    return (client or case["client"]).post(
        f"/api/v1/work/workspaces/{workspace or case['workspace']}/drafts/{record or case['item'].id}/{action}",
        json=body or {},
        headers=case["headers"],
    )


def request(case, **changes):
    preview = send(case)
    assert preview.status_code == 200
    value = {
        "expected_revision": preview.json()["revision"],
        "reviewed_hash": preview.json()["payload_hash"],
        "request_id": str(uuid4()),
        "decision": "approve",
    }
    value.update(changes)
    return value


def rows(case):
    with connect() as db:
        return db.execute(
            "SELECT id,record_id,revision,actor_id,session_id,request_id,payload_hash FROM work.draft_reviews WHERE workspace_id=%s ORDER BY prepared_at,id",
            (case["workspace"],),
        ).fetchall()


def test_current_preview_explicit_review_replay_and_no_business_confirmation(review_case):
    case = review_case
    value = request(case)
    response = send(case, "review", value)
    assert response.status_code == 200 and response.json()["confirmation_applied"] is False
    receipt = response.json()["review_preparation_id"]
    assert response.json()["execution_allowed"] is False
    replay = send(case, "review", value)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["review_preparation_id"] == receipt
    assert len(rows(case)) == 1 and rows(case)[0][3] == case["actor"]
    with connect() as db:
        assert db.execute(
            "SELECT state,revision FROM work.drafts WHERE id=%s", (case["item"].id,)
        ).fetchone() == ("draft", 1)
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_audit WHERE record_id=%s AND event_type='draft.review_prepared'",
                (case["item"].id,),
            ).fetchone()[0]
            == 1
        )
    with case["storage"]["session"]() as db:
        assert db.execute("SELECT current_user").fetchone() == (case["role"],)


@pytest.mark.parametrize("fault", ["stale", "hash", "source", "workspace", "grant", "record"])
def test_stale_or_unavailable_review_never_prepares_a_receipt(review_case, fault):
    case = review_case
    value = request(case)
    if fault == "stale":
        value["expected_revision"] = 2
    elif fault == "hash":
        value["reviewed_hash"] = "0" * 64
    elif fault == "source":
        with connect() as db:
            db.execute(
                "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
                (case["workspace"],),
            )
    elif fault == "workspace":
        with case["maker"].begin() as db:
            administer(db, "disable", case["slug"])
    elif fault == "grant":
        with case["maker"].begin() as db:
            administer(db, "revoke", case["slug"], db.get(User, case["actor"]).slug)
    response = send(case, "review", value, record=uuid4() if fault == "record" else None)
    assert response.status_code == (409 if fault in {"stale", "hash"} else 404)
    assert rows(case) == []


def test_changed_revision_invalidates_prior_preview_and_request_reuse(review_case):
    case = review_case
    value = request(case)
    assert send(case, "review", value).status_code == 200
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
                marker="synthetic:changed-review",
                source_ids=(case["source"],),
                retain_until=case["item"].retain_until,
            ),
        )
    assert send(case, "review", value).status_code == 409
    newer = request(case, request_id=value["request_id"])
    assert send(case, "review", newer).status_code == 409
    assert len(rows(case)) == 1
    with case["storage"]["session"]() as db:
        assert db.execute("SELECT payload_hash FROM work.draft_reviews").fetchall() == []


def test_forget_atomically_scrubs_review_hash_but_keeps_minimal_metadata(review_case):
    case = review_case
    value = request(case)
    assert send(case, "review", value).status_code == 200
    with connect() as db, db.transaction():
        work_drafts.transition(db, case["workspace"], case["actor"], case["item"].id, 1, "forget")
    assert len(rows(case)) == 1 and rows(case)[0][-1] is None
    assert send(case, "preview").status_code == 404
    assert send(case, "review", value).status_code == 404


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE work.drafts SET id=id",
        "UPDATE work.draft_reviews SET payload_hash=payload_hash",
        "DELETE FROM work.draft_reviews",
        "TRUNCATE work.draft_reviews",
        "UPDATE work.drafts SET state='confirmed'",
    ],
)
def test_review_role_cannot_apply_lifecycle_or_mutate_review_history(review_case, statement):
    case = review_case
    assert send(case, "review", request(case)).status_code == 200
    with pytest.raises(psycopg.Error), case["storage"]["session"]() as db:
        db.execute(statement)


def test_review_audit_failure_rolls_back_preparation(review_case):
    case = review_case
    value = request(case)
    name = "synthetic_review_failure_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE work.draft_audit ADD CONSTRAINT {} CHECK(event_type<>'draft.review_prepared') NOT VALID"
            ).format(sql.Identifier(name))
        )
    try:
        response = send(case, "review", value)
        assert response.status_code == 503 and rows(case) == []
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE work.draft_audit DROP CONSTRAINT {}").format(
                    sql.Identifier(name)
                )
            )


def test_identity_commit_failure_can_leave_prepared_review_without_response_receipt(review_case):
    case = review_case
    value = request(case)
    from sqlalchemy.orm import Session

    def fail(session):
        if session.bind is not None and session.bind.url.username == "butler_runtime":
            raise SQLAlchemyError("synthetic identity commit failure")

    event.listen(Session, "before_commit", fail)
    try:
        response = send(case, "review", value)
        assert response.status_code == 503 and "review_preparation_id" not in response.json()
    finally:
        event.remove(Session, "before_commit", fail)
    assert len(rows(case)) == 1


def test_session_expiry_during_work_commit_never_releases_review_receipt(review_case, monkeypatch):
    case = review_case
    value = request(case)
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
        response = send(case, "review", value)
        assert response.status_code == 401 and "review_preparation_id" not in response.json()
    finally:
        event.remove(case["engine"], "commit", expire)
    assert len(rows(case)) == 1


def test_forget_review_hash_failure_rolls_back_the_whole_draft_transaction(review_case):
    case = review_case
    value = request(case)
    assert send(case, "review", value).status_code == 200
    name = "synthetic_hash_failure_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE work.draft_reviews ADD CONSTRAINT {} CHECK(payload_hash IS NOT NULL) NOT VALID"
            ).format(sql.Identifier(name))
        )
    try:
        with pytest.raises(psycopg.Error), connect() as db, db.transaction():
            work_drafts.transition(
                db, case["workspace"], case["actor"], case["item"].id, 1, "forget"
            )
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE work.draft_reviews DROP CONSTRAINT {}").format(
                    sql.Identifier(name)
                )
            )
    assert rows(case)[0][-1] == value["reviewed_hash"]
    with connect() as db:
        assert db.execute(
            "SELECT state,revision FROM work.drafts WHERE id=%s", (case["item"].id,)
        ).fetchone() == ("draft", 1)
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_tombstones WHERE record_id=%s", (case["item"].id,)
            ).fetchone()[0]
            == 0
        )


def test_reused_request_is_bound_to_the_current_session(review_case):
    from conftest import SYNTHETIC_PASSWORD

    case = review_case
    value = request(case)
    first = send(case, "review", value)
    with case["maker"]() as db:
        slug = db.get(User, case["actor"]).slug
    signed_in = case["client"].post(
        "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
    )
    assert signed_in.status_code == 200
    case["headers"] = {"X-CSRF-Token": signed_in.json()["csrf_token"]}
    second = send(case, "review", value)
    assert second.status_code == 200 and second.json()["replayed"] is False
    assert second.json()["review_preparation_id"] != first.json()["review_preparation_id"]
    assert len(rows(case)) == 2 and rows(case)[0][4] != rows(case)[1][4]


def test_expired_preparation_cannot_be_renewed_by_same_request(review_case, monkeypatch):
    case = review_case
    value = request(case)
    assert send(case, "review", value).status_code == 200
    # A current-session clock past the server receipt expiry rejects replay without
    # mutating immutable server expiry. SQL expiry remains checked independently.
    monkeypatch.setattr(identity, "now_utc", lambda: datetime.now(UTC) + timedelta(minutes=6))
    response = send(case, "review", value)
    assert response.status_code == 409 and "review_preparation_id" not in response.json()
    assert len(rows(case)) == 1


def test_revoked_source_hides_prepared_hash_from_scoped_database_reader(review_case):
    case = review_case
    assert send(case, "review", request(case)).status_code == 200
    with connect() as db:
        db.execute(
            "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
            (case["workspace"],),
        )
    with case["storage"]["session"]() as db:
        assert db.execute("SELECT payload_hash FROM work.draft_reviews").fetchall() == []


def test_concurrent_same_session_request_creates_one_preparation(review_case):
    case = review_case
    value = request(case)
    start = Barrier(2)

    def acknowledge():
        start.wait(timeout=5)
        return send(case, "review", value)

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(acknowledge), pool.submit(acknowledge)
        results = [a.result(timeout=15), b.result(timeout=15)]
    assert all(response.status_code == 200 for response in results)
    assert results[0].json()["review_preparation_id"] == results[1].json()["review_preparation_id"]
    assert sorted(response.json()["replayed"] for response in results) == [False, True]
    assert len(rows(case)) == 1


def test_owner_correction_waits_for_preparation_row_lock_then_invalidates_old_review(
    review_case, postgres_engine
):
    case = review_case
    value = request(case)
    ready, release, writer_ready = Event(), Event(), Event()
    pid = []

    def hold(connection):
        ready.set()
        assert release.wait(8)

    def correct():
        with connect() as db, db.transaction():
            pid.append(db.execute("SELECT pg_backend_pid()").fetchone()[0])
            writer_ready.set()
            work_drafts.transition(
                db,
                case["workspace"],
                case["actor"],
                case["item"].id,
                1,
                "correct",
                work_lifecycle.Draft(
                    kind="decision",
                    marker="synthetic:after-review",
                    source_ids=(case["source"],),
                    retain_until=case["item"].retain_until,
                ),
            )

    event.listen(case["engine"], "commit", hold)
    try:
        with ThreadPoolExecutor(2) as pool:
            pending = pool.submit(send, case, "review", value)
            assert ready.wait(5)
            writer = pool.submit(correct)
            try:
                assert writer_ready.wait(5)
                deadline = monotonic() + 1.5
                while monotonic() < deadline:
                    with postgres_engine.connect() as db:
                        wait = db.execute(
                            text(
                                "SELECT wait_event_type,wait_event FROM pg_stat_activity WHERE pid=:pid"
                            ),
                            {"pid": pid[0]},
                        ).one()
                    if wait[0] == "Lock" and wait[1] in {"transactionid", "tuple"}:
                        break
                    Event().wait(0.01)
                else:
                    pytest.fail("Expected actual current-draft row-lock wait")
            finally:
                release.set()
            assert pending.result(timeout=10).status_code == 200
            writer.result(timeout=10)
    finally:
        release.set()
        event.remove(case["engine"], "commit", hold)
    assert send(case, "review", value).status_code == 409


def test_review_retains_workspace_authority_through_work_and_identity_commits(
    review_case, runtime_engine, postgres_engine
):
    case = review_case
    value = request(case)
    work_ready, release_work, identity_ready, release_identity, writer_ready = (
        Event() for _ in range(5)
    )
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    pid = []

    def hold_work(connection):
        work_ready.set()
        assert release_work.wait(8)

    def hold_identity(session):
        identity_ready.set()
        assert release_identity.wait(8)

    def revoke():
        with connect() as db:
            pid.append(db.execute("SELECT pg_backend_pid()").fetchone()[0])
            writer_ready.set()
            db.execute(
                "DELETE FROM work_access_grants WHERE workspace_id=%s AND user_id=%s",
                (case["workspace"], case["actor"]),
            )

    event.listen(case["engine"], "commit", hold_work)
    event.listen(maker, "before_commit", hold_identity)
    try:
        with client_for(maker) as client:
            client.cookies.update(case["client"].cookies)
            with ThreadPoolExecutor(2) as pool:
                pending = pool.submit(send, case, "review", value, client=client)
                assert work_ready.wait(5)
                writer = pool.submit(revoke)
                try:
                    assert writer_ready.wait(5)
                    wait_for_advisory(postgres_engine, pid[0])
                    release_work.set()
                    assert identity_ready.wait(5)
                    wait_for_advisory(postgres_engine, pid[0])
                finally:
                    release_work.set()
                    release_identity.set()
                assert pending.result(timeout=10).status_code == 200
                writer.result(timeout=10)
            assert send(case, "review", value, client=client).status_code == 404
    finally:
        release_work.set()
        release_identity.set()
        event.remove(case["engine"], "commit", hold_work)
        event.remove(maker, "before_commit", hold_identity)
