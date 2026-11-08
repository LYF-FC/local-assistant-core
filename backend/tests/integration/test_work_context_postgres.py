"""Confirmed context through a real restricted workspace login."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from psycopg import sql
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from work_storage_helpers import connect

from app import identity, work_context, work_drafts, work_lifecycle, work_read
from app.main import app
from app.models import AuthSession

pytestmark = pytest.mark.integration


@pytest.fixture
def context_case(review_case):
    case = review_case
    with connect() as db, db.transaction():
        case["confirmed"] = work_drafts.transition(
            db, case["workspace"], case["actor"], case["item"].id, 1, "confirm"
        )
    app.dependency_overrides[work_context.get_context_engines] = lambda: work_read.WorkspaceEngines(
        {case["workspace"]: case["engine"]}
    )
    try:
        yield case
    finally:
        app.dependency_overrides.pop(work_context.get_context_engines, None)


def send(case, selections=None, max_bytes=8192, workspace=None):
    return case["client"].post(
        f"/api/v1/work/workspaces/{workspace or case['workspace']}/context/preview",
        json={
            "selections": selections or [{"id": str(case["item"].id), "expected_revision": 2}],
            "max_bytes": max_bytes,
        },
        headers=case["headers"],
    )


def test_confirmed_context_order_exact_budget_and_metadata_only_audit(context_case):
    case = context_case
    with connect() as db, db.transaction():
        second = work_drafts.create(
            db,
            case["workspace"],
            case["actor"],
            case["policy"],
            work_lifecycle.Draft(
                kind="question",
                marker="synthetic:second-context",
                source_ids=(case["source"],),
                retain_until=datetime.now(UTC) + timedelta(minutes=30),
            ),
        )
        second = work_drafts.transition(
            db, case["workspace"], case["actor"], second.id, 1, "confirm"
        )
    choices = [{"id": str(i), "expected_revision": 2} for i in (second.id, case["item"].id)]
    response = send(case, choices)
    assert response.status_code == 200
    value = response.json()
    assert [item["id"] for item in value["items"]] == [item["id"] for item in choices]
    size = len(
        json.dumps(
            value["items"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    )
    assert value["items_bytes"] == size
    assert send(case, choices, size).status_code == 200
    denied = send(case, choices, size - 1)
    assert denied.status_code == 413 and "items" not in denied.json()
    assert value["reference_only"] and not value["model_invoked"] and not value["execution_allowed"]
    assert (
        0
        < (
            datetime.fromisoformat(value["valid_until"])
            - datetime.fromisoformat(value["generated_at"])
        ).total_seconds()
        <= 60
    )
    with connect() as db:
        audits = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE event_type='work.context_preview' AND entity_id=%s",
            (str(case["workspace"]),),
        ).fetchall()
        assert len(audits) == 2
        assert "synthetic:" not in json.dumps(audits)
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_audit WHERE record_id=%s AND event_type='draft.read_prepared'",
                (second.id,),
            ).fetchone()[0]
            == 2
        )


@pytest.mark.parametrize(
    "fault",
    ["stale", "missing", "mixed", "workspace", "source", "forgotten", "corrected", "expired"],
)
def test_whole_selection_denied_without_payload(context_case, fault, monkeypatch):
    case = context_case
    choices = [{"id": str(case["item"].id), "expected_revision": 2}]
    if fault == "stale":
        choices[0]["expected_revision"] = 1
    elif fault in {"missing", "mixed"}:
        if fault == "missing":
            choices = []
        choices.append({"id": str(uuid4()), "expected_revision": 2})
    elif fault == "source":
        with connect() as db:
            db.execute(
                "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
                (case["workspace"],),
            )
    elif fault in {"forgotten", "corrected"}:
        with connect() as db, db.transaction():
            work_drafts.transition(
                db,
                case["workspace"],
                case["actor"],
                case["item"].id,
                2,
                "forget" if fault == "forgotten" else "correct",
                None
                if fault == "forgotten"
                else work_lifecycle.Draft(
                    kind="decision",
                    marker="synthetic:corrected",
                    source_ids=(case["source"],),
                    retain_until=case["item"].retain_until,
                ),
            )
    elif fault == "expired":
        monkeypatch.setattr(
            identity, "now_utc", lambda: case["item"].retain_until + timedelta(seconds=1)
        )
    result = send(case, choices, workspace=uuid4() if fault == "workspace" else None)
    assert result.status_code == (409 if fault == "stale" else 401 if fault == "expired" else 404)
    assert "items" not in result.json()


def test_unconfirmed_notes_are_unavailable(review_case):
    case = review_case
    app.dependency_overrides[work_context.get_context_engines] = lambda: work_read.WorkspaceEngines(
        {case["workspace"]: case["engine"]}
    )
    try:
        assert send(case).status_code == 404
    finally:
        app.dependency_overrides.pop(work_context.get_context_engines, None)


@pytest.mark.parametrize("target", ["private", "identity"])
def test_audit_failure_suppresses_content(context_case, target):
    case = context_case
    if target == "identity":
        from sqlalchemy.orm import Session

        def fail(session):
            if session.bind is not None and session.bind.url.username == "butler_runtime":
                raise SQLAlchemyError("synthetic commit failure")

        event.listen(Session, "before_commit", fail)
        try:
            result = send(case)
        finally:
            event.remove(Session, "before_commit", fail)
    else:
        name = "synthetic_context_failure_" + uuid4().hex
        with connect() as db:
            db.execute(
                sql.SQL(
                    "ALTER TABLE work.draft_audit ADD CONSTRAINT {} CHECK(event_type<>'draft.read_prepared') NOT VALID"
                ).format(sql.Identifier(name))
            )
        try:
            result = send(case)
        finally:
            with connect() as db:
                db.execute(
                    sql.SQL("ALTER TABLE work.draft_audit DROP CONSTRAINT {}").format(
                        sql.Identifier(name)
                    )
                )
    assert result.status_code == 503 and "items" not in result.json()


def test_session_expiry_after_private_commit_suppresses_content(context_case, monkeypatch):
    case = context_case
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
        result = send(case)
        assert result.status_code == 401 and "items" not in result.json()
    finally:
        event.remove(case["engine"], "commit", expire)


@pytest.mark.parametrize("mutation", ["forget", "revoke", "source"])
def test_context_fences_concurrent_mutation(context_case, postgres_engine, mutation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from time import monotonic

    from sqlalchemy import text

    case = context_case
    ready, release, writer_ready = Event(), Event(), Event()
    pid = []

    def hold(connection):
        ready.set()
        assert release.wait(8)

    def mutate():
        with connect() as db, db.transaction():
            pid.append(db.execute("SELECT pg_backend_pid()").fetchone()[0])
            writer_ready.set()
            if mutation == "forget":
                work_drafts.transition(
                    db, case["workspace"], case["actor"], case["item"].id, 2, "forget"
                )
            elif mutation == "revoke":
                db.execute(
                    "DELETE FROM public.work_access_grants WHERE workspace_id=%s AND user_id=%s",
                    (case["workspace"], case["actor"]),
                )
            else:
                db.execute(
                    "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
                    (case["workspace"],),
                )

    event.listen(case["engine"], "commit", hold)
    try:
        with ThreadPoolExecutor(2) as pool:
            pending = pool.submit(send, case)
            assert ready.wait(5)
            writer = pool.submit(mutate)
            try:
                assert writer_ready.wait(5)
                deadline = monotonic() + 1.5
                while monotonic() < deadline:
                    with postgres_engine.connect() as db:
                        wait = db.execute(
                            text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"),
                            {"pid": pid[0]},
                        ).scalar()
                    if wait == "Lock":
                        break
                    Event().wait(0.01)
                else:
                    pytest.fail("Expected actual mutation lock wait")
            finally:
                release.set()
            assert pending.result(timeout=10).status_code == 200
            writer.result(timeout=10)
    finally:
        release.set()
        event.remove(case["engine"], "commit", hold)
    assert send(case).status_code == 404


def test_retention_expiry_after_private_commit_suppresses_context(context_case, monkeypatch):
    case = context_case
    # Keep the identity session current while moving only the note's server clock.
    from app import work_review

    original = work_review._clock
    calls = [0]

    def checked(authority):
        now = original(authority)
        calls[0] += 1
        return case["item"].retain_until + timedelta(seconds=1) if calls[0] >= 3 else now

    monkeypatch.setattr(work_review, "_clock", checked)
    result = send(case)
    assert result.status_code == 404 and "items" not in result.json()
