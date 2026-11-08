"""Discard pending inputs while preserving retained records and completed outcomes."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb
from work_storage_helpers import PASSWORD, connect

from app import work_capture_worker, work_confirmation_worker, work_drafts
from app import work_restore_requests as cleanup
from app.config import settings
from app.manage import set_scope
from app.models import User

pytestmark = pytest.mark.integration


def seed(db, case, *, count=1):
    session = db.execute(
        "SELECT id FROM public.auth_sessions WHERE user_id=%s ORDER BY id LIMIT 1", (case["actor"],)
    ).fetchone()[0]
    payload = {
        "policy_id": str(case["policy"]),
        "draft": {
            "kind": "decision",
            "marker": "synthetic:restored-unsaved",
            "source_ids": [str(case["source"])],
            "retain_until": (work_drafts._now(db) + timedelta(hours=1)).isoformat(),
        },
    }
    for intent in ("capture_draft", "correct_note", "forget_note"):
        for _ in range(count):
            db.execute(
                "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,intent,target_record_id,expected_revision,payload,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp()+interval '4 minutes')",
                (
                    case["workspace"],
                    case["actor"],
                    session,
                    uuid4(),
                    intent,
                    case["item"].id if intent != "capture_draft" else None,
                    1 if intent != "capture_draft" else None,
                    Jsonb({"forget": True} if intent == "forget_note" else payload),
                ),
            )
    review = db.execute(
        "INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash) SELECT workspace_id,id,revision,%s,%s,%s,'confirm_note',encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') FROM work.drafts WHERE workspace_id=%s AND id=%s RETURNING id,expires_at",
        (case["actor"], session, uuid4(), case["workspace"], case["item"].id),
    ).fetchone()
    confirmation = db.execute(
        "INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) VALUES(%s,%s,%s,1,%s,%s,%s,%s) RETURNING id",
        (case["workspace"], case["item"].id, review[0], case["actor"], session, uuid4(), review[1]),
    ).fetchone()[0]
    return review[0], confirmation


@pytest.fixture
def case(review_case):
    with review_case["maker"].begin() as db:
        set_scope(db, db.get(User, review_case["actor"]), "technical_admin", True)
    with connect() as db:
        seed(db, review_case)
        finished = db.execute(
            "SELECT id FROM work.capture_intents WHERE workspace_id=%s AND intent='capture_draft'",
            (review_case["workspace"],),
        ).fetchone()[0]
        work_capture_worker._finish(
            db, {"id": finished, "workspace_id": review_case["workspace"]}, reason="expired"
        )
        # Add another capture so pending mixed set still includes an unbound capture.
        db.execute(
            "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,payload,expires_at) SELECT workspace_id,actor_id,session_id,%s,payload,clock_timestamp()+interval '4 minutes' FROM work.capture_intents WHERE workspace_id=%s AND intent='correct_note' LIMIT 1",
            (uuid4(), review_case["workspace"]),
        )
    return review_case


def quarantine(case):
    with connect() as db:
        db.execute(
            "UPDATE public.work_workspaces SET is_active=false WHERE id=%s", (case["workspace"],)
        )
        db.execute(
            "DELETE FROM public.work_access_grants WHERE workspace_id=%s", (case["workspace"],)
        )


def run(case, **changes):
    values = {
        "workspace_id": case["workspace"],
        "operator_id": case["actor"],
        "restored_database": settings.postgres_db,
    }
    values.update(changes)
    with connect() as db, db.transaction():
        return cleanup.reconcile(db, cleanup.Request(**values))


def apply(case, plan):
    return run(
        case,
        decision="discard_restored_requests",
        issued_at=datetime.fromisoformat(plan["issued_at"]),
        reviewed_hash=plan["reviewed_hash"],
    )


def state(case):
    with connect() as db:
        return tuple(
            db.execute(query, (case["workspace"],)).fetchone()[0]
            for query in (
                "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND state='pending'",
                "SELECT count(*) FROM public.work_confirmation_requests WHERE workspace_id=%s AND state='pending'",
                "SELECT count(*) FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NOT NULL",
                "SELECT count(*) FROM public.audit_events WHERE entity_id=%s::text AND event_type='admin.work_restore_requests_discarded'",
            )
        )


def test_mixed_cleanup_no_payload_disclosure_preserves_notes_and_completed(case):
    quarantine(case)
    with connect() as db:
        notes = db.execute("SELECT * FROM work.drafts ORDER BY workspace_id,id").fetchall()
        completed = db.execute(
            "SELECT * FROM work.capture_intents WHERE workspace_id=%s AND state<>'pending'",
            (case["workspace"],),
        ).fetchall()
    plan = run(case)
    assert len(plan["items"]) == 5 and state(case) == (3, 1, 1, 0)
    assert run(case, issued_at=datetime.fromisoformat(plan["issued_at"])) == plan
    for secret in (
        "payload_hash",
        "snapshot",
        "synthetic:restored-unsaved",
        "synthetic:review-note",
    ):
        assert secret not in json.dumps(plan)
    result = apply(case, plan)
    assert state(case) == (0, 0, 0, 1) and not result["recovery_complete"]
    with connect() as db:
        assert db.execute("SELECT * FROM work.drafts ORDER BY workspace_id,id").fetchall() == notes
        assert (
            db.execute(
                "SELECT * FROM work.capture_intents WHERE workspace_id=%s AND reason_code='expired'",
                (case["workspace"],),
            ).fetchall()
            == completed
        )
        assert (
            db.execute(
                "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND (payload IS NOT NULL OR payload_hash IS NOT NULL)",
                (case["workspace"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s", (result["receipt_id"],)
            ).fetchone()[0]
            == result
        )
        for item in plan["items"]:
            if item["kind"] == "capture" and item["intent"] == "capture_draft":
                assert work_capture_worker.execute(db, UUID(item["id"]))["state"] == "denied"
            elif item["kind"] == "confirmation":
                assert work_confirmation_worker.execute(db, UUID(item["id"]))["state"] == "denied"
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    with pytest.raises(ValueError, match="No pending"):
        apply(case, run(case))


@pytest.mark.parametrize(
    "fault",
    ["active", "grant", "target", "operator", "old", "future", "login", "assumed", "isolation"],
)
def test_unsafe_context_rejected_without_effects(case, fault):
    if fault != "active":
        with connect() as db:
            db.execute(
                "UPDATE public.work_workspaces SET is_active=false WHERE id=%s",
                (case["workspace"],),
            )
            if fault != "grant":
                db.execute(
                    "DELETE FROM public.work_access_grants WHERE workspace_id=%s",
                    (case["workspace"],),
                )
    before = state(case)
    changes = {}
    if fault == "target":
        changes["restored_database"] = "butler_test_wrong"
    if fault == "operator":
        changes["operator_id"] = uuid4()
    if fault in {"old", "future"}:
        changes["issued_at"] = datetime.now(UTC) + timedelta(minutes=-6 if fault == "old" else 1)
    if fault in {"login", "assumed", "isolation"}:
        with (
            pytest.raises((ValueError, psycopg.Error)),
            connect(
                case["login"] if fault == "login" else None, PASSWORD if fault == "login" else None
            ) as db,
            db.transaction(),
        ):
            if fault == "assumed":
                db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(case["role"])))
            if fault == "isolation":
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cleanup.reconcile(
                db,
                cleanup.Request(
                    workspace_id=case["workspace"],
                    operator_id=case["actor"],
                    restored_database=settings.postgres_db,
                ),
            )
    else:
        with pytest.raises(ValueError):
            run(case, **changes)
    assert state(case) == before


@pytest.mark.parametrize("fault", ["mode", "active", "grant", "assumed", "isolation", "immutable"])
def test_review_guard_rejects_unsafe_hash_redaction(case, fault):
    if fault not in {"active", "grant"}:
        quarantine(case)
    elif fault == "grant":
        with connect() as db:
            db.execute(
                "UPDATE public.work_workspaces SET is_active=false WHERE id=%s",
                (case["workspace"],),
            )
    before = state(case)
    with pytest.raises((ValueError, psycopg.Error)), connect() as db, db.transaction():
        if fault != "mode":
            db.execute("SET LOCAL butler.restore_requests='reviewed'")
        if fault == "assumed":
            db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(case["role"])))
        if fault == "isolation":
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        if fault == "assumed":
            db.execute("SELECT work.restore_requests_allowed(%s)", (case["workspace"],))
        db.execute(
            "UPDATE work.draft_reviews SET payload_hash=NULL"
            + (",revision=revision+1" if fault == "immutable" else "")
            + " WHERE workspace_id=%s",
            (case["workspace"],),
        )
    assert state(case) == before


@pytest.mark.parametrize("change", ["terminal", "review"])
def test_changed_plan_rejected(case, change):
    quarantine(case)
    plan = run(case)
    with connect() as db:
        if change == "terminal":
            row = db.execute(
                "SELECT id FROM work.capture_intents WHERE workspace_id=%s AND state='pending' LIMIT 1",
                (case["workspace"],),
            ).fetchone()
            work_capture_worker._finish(
                db, {"id": row[0], "workspace_id": case["workspace"]}, reason="stale"
            )
        else:
            db.execute("SET LOCAL butler.restore_requests='reviewed'")
            db.execute(
                "UPDATE work.draft_reviews SET payload_hash=NULL WHERE workspace_id=%s",
                (case["workspace"],),
            )
    before = state(case)
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    assert state(case) == before


def test_audit_failure_and_final_expiry_rollback_every_effect(case, monkeypatch):
    quarantine(case)
    plan = run(case)
    before = state(case)
    name = "synthetic_restore_requests_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE public.audit_events ADD CONSTRAINT {} CHECK(event_type<>'admin.work_restore_requests_discarded') NOT VALID"
            ).format(sql.Identifier(name))
        )
    try:
        with pytest.raises(psycopg.Error):
            apply(case, plan)
        assert state(case) == before
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE public.audit_events DROP CONSTRAINT {}").format(
                    sql.Identifier(name)
                )
            )
    original = work_drafts._now
    calls = 0

    def late(db):
        nonlocal calls
        calls += 1
        return original(db) + timedelta(minutes=6) if calls >= 2 else original(db)

    monkeypatch.setattr(work_drafts, "_now", late)
    with pytest.raises(ValueError, match="current server"):
        apply(case, plan)
    assert state(case) == before


def test_combined_cap_has_no_partial_cleanup(case):
    # Each table stays under 100; combined set must still reject.
    with connect() as db:
        seed(db, case, count=32)
    quarantine(case)
    before = state(case)
    with pytest.raises(ValueError, match="Too many"):
        run(case)
    assert state(case) == before


def test_concurrent_once_and_registry_timeout(case):
    quarantine(case)
    plan = run(case)
    ready, release = Event(), Event()

    def reader():
        with connect() as db:
            db.execute("SELECT pg_advisory_xact_lock_shared(1508310,1)")
            ready.set()
            assert release.wait(8)

    with ThreadPoolExecutor(1) as pool:
        held = pool.submit(reader)
        assert ready.wait(4)
        try:
            with pytest.raises(psycopg.errors.LockNotAvailable):
                apply(case, plan)
        finally:
            release.set()
        held.result(timeout=5)

    def cleaner():
        try:
            apply(case, plan)
            return "applied"
        except ValueError:
            return "stale"

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(cleaner), pool.submit(cleaner)]
        assert sorted(f.result(timeout=8) for f in futures) == ["applied", "stale"]
    assert state(case) == (0, 0, 0, 1)


def test_actual_cli_and_downgrade_receipt_refusal(case):
    quarantine(case)
    base = [
        sys.executable,
        "-m",
        "app.work_restore_requests",
        "--environment",
        "test",
        "--restored-database",
        settings.postgres_db,
        "--workspace",
        str(case["workspace"]),
        "--operator",
        str(case["actor"]),
    ]
    plan = json.loads(subprocess.check_output(base, text=True))
    result = subprocess.run(
        [
            *base,
            "--issued-at",
            plan["issued_at"],
            "--reviewed-hash",
            plan["reviewed_hash"],
            "--decision",
            "discard_restored_requests",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)["outcomes"]) == 5
    downgraded = subprocess.run(
        ["alembic", "downgrade", "0017_work_suppression"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert downgraded.returncode != 0 and "cleanup evidence exists" in downgraded.stderr
    assert state(case) == (0, 0, 0, 1)


def test_expired_review_without_cleanup_mode_is_not_an_implicit_permission(case):
    with connect() as db:
        review = db.execute(
            "INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash,prepared_at,expires_at) SELECT workspace_id,id,revision,%s,%s,%s,'confirm_note',encode(sha256(convert_to(snapshot::text,'UTF8')),'hex'),clock_timestamp()-interval '2 minutes',clock_timestamp()-interval '1 minute' FROM work.drafts WHERE workspace_id=%s AND id=%s RETURNING id",
            (case["actor"], uuid4(), uuid4(), case["workspace"], case["item"].id),
        ).fetchone()[0]
    quarantine(case)
    with pytest.raises(psycopg.Error), connect() as db:
        db.execute(
            "UPDATE work.draft_reviews SET payload_hash=NULL WHERE workspace_id=%s AND id=%s",
            (case["workspace"], review),
        )
    assert state(case) == (3, 1, 2, 0)


def test_completed_confirmation_is_preserved_during_review_hash_cleanup(case):
    with connect() as db:
        confirmation = db.execute(
            "SELECT id FROM public.work_confirmation_requests WHERE workspace_id=%s",
            (case["workspace"],),
        ).fetchone()[0]
        work_confirmation_worker._finish(
            db, {"id": confirmation, "workspace_id": case["workspace"]}, reason="stale"
        )
        completed = db.execute(
            "SELECT * FROM public.work_confirmation_requests WHERE id=%s", (confirmation,)
        ).fetchone()
    quarantine(case)
    apply(case, run(case))
    with connect() as db:
        assert (
            db.execute(
                "SELECT * FROM public.work_confirmation_requests WHERE id=%s", (confirmation,)
            ).fetchone()
            == completed
        )
    assert state(case) == (0, 0, 0, 1)
