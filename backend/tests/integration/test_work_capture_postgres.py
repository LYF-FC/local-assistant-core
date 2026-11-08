"""Real restricted-login capture preparation and atomic local draft creation."""

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
from work_storage_helpers import connect

from app import identity, work_capture, work_drafts, work_parties, work_read
from app import work_capture_worker as worker
from app.main import app
from app.models import User
from app.work_capture_storage import provision_captures
from app.work_manage import administer

pytestmark = pytest.mark.integration


@pytest.fixture
def capture_case(review_case):
    case = review_case
    with connect() as db:
        provision_captures(db, case["slug"])
    app.dependency_overrides[work_capture.get_capture_engines] = lambda: work_read.WorkspaceEngines(
        {case["workspace"]: case["engine"]}
    )
    try:
        yield case
    finally:
        app.dependency_overrides.pop(work_capture.get_capture_engines, None)


def body(case, **changes):
    value = {
        "request_id": str(uuid4()),
        "decision": "capture_draft",
        "policy_id": str(case["policy"]),
        "draft": {
            "kind": "action",
            "marker": "synthetic:authenticated-capture",
            "source_ids": [str(case["source"])],
            "owner_id": None,
            "due_at": None,
            "retain_until": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
    }
    value.update(changes)
    return value


def send(case, value=None, command=None, workspace=None):
    suffix = f"/{command}/status" if command else ""
    return case["client"].post(
        f"/api/v1/work/workspaces/{workspace or case['workspace']}/captures{suffix}",
        json={} if command else value or body(case),
        headers=case["headers"],
    )


def execute(command):
    with connect() as db, db.transaction():
        return worker.execute(db, UUID(str(command)))


def stored(case):
    with connect() as db:
        return db.execute(
            "SELECT id,state,payload,payload_hash,record_id FROM work.capture_intents WHERE workspace_id=%s ORDER BY prepared_at",
            (case["workspace"],),
        ).fetchall()


def notes(case):
    with connect() as db:
        return db.execute(
            "SELECT snapshot FROM work.drafts WHERE workspace_id=%s AND snapshot->>'marker'='synthetic:authenticated-capture'",
            (case["workspace"],),
        ).fetchall()


def test_capture_saves_once_with_explicit_unknown_owner_and_redacted_intent(capture_case):
    case = capture_case
    value = body(case)
    response = send(case, value)
    assert response.status_code == 202 and not response.json()["capture_applied"]
    command = response.json()["capture_preparation_id"]
    assert notes(case) == [] and len(stored(case)) == 1
    replay = send(case, value)
    assert replay.status_code == 202 and replay.json()["replayed"]
    assert replay.json()["capture_preparation_id"] == command
    applied = execute(command)
    assert applied["state"] == "applied" and applied["revision"] == 1
    assert execute(command) == applied
    assert stored(case)[0][1:4] == ("applied", None, None)
    current = notes(case)
    assert len(current) == 1 and current[0][0]["actor_id"] == str(case["actor"])
    assert current[0][0]["owner_id"] is None and current[0][0]["due_at"] is None
    status = send(case, command=command)
    assert status.status_code == 200 and status.json()["capture_applied"]
    assert status.json()["record_id"] == applied["record_id"]
    assert status.json()["confirmation_applied"] is False
    for secret in (value["draft"]["marker"], str(case["source"]), str(case["policy"])):
        assert secret not in response.text and secret not in status.text
    assert send(case, value).status_code == 409
    with connect() as db, db.transaction():
        work_drafts.transition(
            db, case["workspace"], case["actor"], UUID(applied["record_id"]), 1, "forget"
        )
    assert execute(command) == applied and stored(case)[0][2:4] == (None, None)


def test_explicit_party_owner_is_preserved(capture_case):
    case = capture_case
    with connect() as db, db.transaction():
        owner = work_parties.create(
            db,
            case["workspace"],
            case["policy"],
            "synthetic:capture-owner",
            datetime.now(UTC) + timedelta(hours=1),
        )
    value = body(case)
    value["draft"]["owner_id"] = str(owner.id)
    command = send(case, value).json()["capture_preparation_id"]
    execute(command)
    assert notes(case)[0][0]["owner_id"] == str(owner.id)


@pytest.mark.parametrize("fault", ["policy", "source", "owner", "retention", "workspace"])
def test_ineligible_capture_never_prepares_private_payload(capture_case, fault):
    case = capture_case
    value = body(case)
    if fault == "policy":
        value["policy_id"] = str(uuid4())
    elif fault == "source":
        value["draft"]["source_ids"] = [str(uuid4())]
    elif fault == "owner":
        value["draft"]["owner_id"] = str(uuid4())
    elif fault == "retention":
        value["draft"]["retain_until"] = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    response = send(case, value, workspace=uuid4() if fault == "workspace" else None)
    assert response.status_code == (409 if fault == "retention" else 404)
    assert stored(case) == [] and notes(case) == []


def test_nonce_conflict_and_cross_session_status_denied(capture_case):
    from conftest import SYNTHETIC_PASSWORD

    case = capture_case
    value = body(case)
    command = send(case, value).json()["capture_preparation_id"]
    value["draft"]["marker"] = "synthetic:changed-capture"
    assert send(case, value).status_code == 409
    with case["maker"]() as db:
        slug = db.get(User, case["actor"]).slug
    login = case["client"].post(
        "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
    )
    case["headers"] = {"X-CSRF-Token": login.json()["csrf_token"]}
    assert send(case, command=command).status_code == 404


@pytest.mark.parametrize("fault", ["source", "party", "grant", "session", "expired"])
def test_fresh_execution_denies_stale_intent_and_redacts_payload(capture_case, fault):
    case = capture_case
    value = body(case)
    with connect() as db, db.transaction():
        owner = work_parties.create(
            db,
            case["workspace"],
            case["policy"],
            "synthetic:revocable-owner",
            datetime.now(UTC) + timedelta(hours=1),
        )
    value["draft"]["owner_id"] = str(owner.id)
    if fault == "expired":
        value["draft"]["retain_until"] = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    command = send(case, value).json()["capture_preparation_id"]
    if fault == "source":
        with connect() as db:
            db.execute(
                "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
                (case["workspace"],),
            )
    elif fault == "party":
        with connect() as db, db.transaction():
            work_parties.transition(db, case["workspace"], owner.id, 1, "retire")
    elif fault == "grant":
        with case["maker"].begin() as db:
            administer(db, "revoke", case["slug"], db.get(User, case["actor"]).slug)
    elif fault == "session":
        with connect() as db:
            db.execute(
                "UPDATE public.auth_sessions SET revoked_at=clock_timestamp() WHERE id=(SELECT session_id FROM work.capture_intents WHERE id=%s)",
                (UUID(command),),
            )
    else:
        with connect() as db:
            db.execute("SELECT pg_sleep(1.1)")
    assert execute(command)["state"] == "denied"
    assert stored(case)[0][1:4] == ("denied", None, None) and notes(case) == []


def test_identity_commit_failure_leaves_only_orphan_preparation(capture_case):
    case = capture_case

    def fail(session):
        if session.bind is not None and session.bind.url.username == "butler_runtime":
            raise SQLAlchemyError("synthetic capture identity failure")

    event.listen(Session, "before_commit", fail)
    try:
        response = send(case)
    finally:
        event.remove(Session, "before_commit", fail)
    assert response.status_code == 503 and "capture_preparation_id" not in response.json()
    command = stored(case)[0][0]
    assert execute(command)["state"] == "denied" and notes(case) == []
    assert stored(case)[0][2:4] == (None, None)


@pytest.mark.parametrize("target", ["preparation", "draft", "outcome", "identity"])
def test_audit_failure_rolls_back_capture_or_application(capture_case, target):
    case = capture_case
    command = None if target == "preparation" else send(case).json()["capture_preparation_id"]
    table, event_type = {
        "preparation": ("work.capture_audit", "capture.prepared"),
        "draft": ("work.draft_audit", "draft.created"),
        "outcome": ("work.capture_audit", "capture.applied"),
        "identity": ("public.audit_events", "work.capture_finished"),
    }[target]
    name = "synthetic_capture_failure_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} CHECK(event_type<>{}) NOT VALID").format(
                sql.SQL(table), sql.Identifier(name), sql.Literal(event_type)
            )
        )
    try:
        if command is None:
            assert send(case).status_code == 503 and stored(case) == []
        else:
            with pytest.raises(psycopg.Error):
                execute(command)
            assert stored(case)[0][1] == "pending" and stored(case)[0][2] is not None
        assert notes(case) == []
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                    sql.SQL(table), sql.Identifier(name)
                )
            )


def test_duplicate_executor_is_one_atomic_draft(capture_case):
    case = capture_case
    command = send(case).json()["capture_preparation_id"]
    start = Barrier(2)

    def run():
        start.wait(timeout=5)
        return execute(command)

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(run), pool.submit(run)
        assert a.result(timeout=15) == b.result(timeout=15)
    assert len(notes(case)) == 1


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE work.capture_intents SET state='applied'",
        "DELETE FROM work.capture_intents",
        "TRUNCATE work.capture_intents CASCADE",
        "UPDATE work.capture_audit SET event_type=event_type",
        "INSERT INTO work.drafts SELECT * FROM work.drafts",
    ],
)
def test_capture_role_cannot_mutate_notes_or_outcome(capture_case, statement):
    send(capture_case)
    with pytest.raises(psycopg.Error), capture_case["storage"]["session"]() as db:
        db.execute(statement)


def test_direct_owner_sql_cannot_edit_intent_or_reactivate_terminal(capture_case):
    case = capture_case
    command = send(case).json()["capture_preparation_id"]
    for statement in (
        "UPDATE work.capture_intents SET request_id=gen_random_uuid()",
        "UPDATE work.capture_intents SET payload=payload||'{\"extra\":true}'::jsonb",
        "UPDATE work.capture_intents SET expires_at=expires_at+interval '1 minute'",
    ):
        with pytest.raises(psycopg.Error), connect() as db:
            db.execute(statement)
    execute(command)
    with pytest.raises(psycopg.Error), connect() as db:
        db.execute("UPDATE work.capture_intents SET state='pending'")


def test_expiry_after_private_commit_suppresses_handle(capture_case, monkeypatch):
    case = capture_case
    now = identity.now_utc()
    clock = [now]
    with case["maker"].begin() as db:
        from app.models import AuthSession

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
        response = send(case)
        assert response.status_code == 401 and "capture_preparation_id" not in response.json()
    finally:
        event.remove(case["engine"], "commit", expire)


def test_concurrent_nonce_replay_prepares_one_intent(capture_case):
    case = capture_case
    value = body(case)
    start = Barrier(2)

    def prepare():
        start.wait(timeout=5)
        return send(case, value)

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(prepare), pool.submit(prepare)
        results = [a.result(timeout=15), b.result(timeout=15)]
    assert all(result.status_code == 202 for result in results)
    assert (
        results[0].json()["capture_preparation_id"] == results[1].json()["capture_preparation_id"]
    )
    assert len(stored(case)) == 1


def test_private_payload_never_enters_identity_audit(capture_case):
    import json

    case = capture_case
    value = body(case)
    command = send(case, value).json()["capture_preparation_id"]
    execute(command)
    with connect() as db:
        metadata = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE entity_id=%s AND event_type IN ('work.capture_requested','work.capture_finished')",
            (str(case["workspace"]),),
        ).fetchall()
    encoded = json.dumps(metadata)
    assert len(metadata) == 2
    for secret in (
        value["draft"]["marker"],
        str(case["source"]),
        str(case["policy"]),
        "payload_hash",
        "draft",
    ):
        assert secret not in encoded


def test_capture_role_cannot_forge_applied_audit_or_owner_outcome(capture_case):
    case = capture_case
    command = send(case).json()["capture_preparation_id"]
    with pytest.raises(psycopg.Error), case["storage"]["session"]() as db:
        db.execute(
            "INSERT INTO work.capture_audit(workspace_id,capture_id,event_type) VALUES(%s,%s,'capture.applied')",
            (case["workspace"], UUID(command)),
        )
    with connect() as db:
        db.execute(
            sql.SQL("GRANT UPDATE ON work.capture_intents TO {}").format(
                sql.Identifier(case["role"])
            )
        )
    with pytest.raises(psycopg.Error), case["storage"]["session"]() as db:
        db.execute(
            "UPDATE work.capture_intents SET state='denied',payload=NULL,reason_code='stale',finished_at=clock_timestamp()"
        )


def test_owned_broad_engine_is_refused_before_capture(capture_case):
    from sqlalchemy.engine import make_url

    from app.config import settings

    case = capture_case
    engine = work_read.workspace_engine(make_url(settings.database_url))
    app.dependency_overrides[work_capture.get_capture_engines] = lambda: work_read.WorkspaceEngines(
        {case["workspace"]: engine}
    )
    try:
        response = send(case)
        assert response.status_code == 503 and stored(case) == []
    finally:
        engine.dispose()


def test_deferred_commit_failure_rolls_back_note_redaction_and_outcome(capture_case):
    case = capture_case
    command = send(case).json()["capture_preparation_id"]
    name = "synthetic_capture_commit_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "CREATE FUNCTION work.{}() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN RAISE EXCEPTION 'synthetic deferred capture failure' USING ERRCODE='23514'; END; $$"
            ).format(sql.Identifier(name))
        )
        db.execute(
            sql.SQL(
                "CREATE CONSTRAINT TRIGGER {} AFTER UPDATE ON work.capture_intents DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.state='applied') EXECUTE FUNCTION work.{}()"
            ).format(sql.Identifier(name), sql.Identifier(name))
        )
    try:
        with pytest.raises(psycopg.Error):
            execute(command)
        assert notes(case) == []
        row = stored(case)[0]
        assert row[1] == "pending" and row[2] is not None and row[3] is not None and row[4] is None
        with connect() as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM work.capture_audit WHERE capture_id=%s AND event_type='capture.applied'",
                    (UUID(command),),
                ).fetchone()[0]
                == 0
            )
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("DROP TRIGGER {} ON work.capture_intents").format(sql.Identifier(name))
            )
            db.execute(sql.SQL("DROP FUNCTION work.{}()").format(sql.Identifier(name)))


def test_post_write_expiry_rolls_back_the_entire_capture(capture_case, monkeypatch):
    case = capture_case
    command = send(case).json()["capture_preparation_id"]
    original = work_drafts._now

    def expire_on_application(db):
        applied = db.execute(
            "SELECT state,expires_at FROM work.capture_intents WHERE id=%s", (UUID(command),)
        ).fetchone()
        return applied[1] + timedelta(seconds=1) if applied[0] == "applied" else original(db)

    monkeypatch.setattr(work_drafts, "_now", expire_on_application)
    with pytest.raises(ValueError, match="expired during write"):
        execute(command)
    assert notes(case) == [] and stored(case)[0][1] == "pending" and stored(case)[0][2] is not None
