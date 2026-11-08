"""Actual registry/session quarantine boundaries, atomicity and exact reviewed plans."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import psycopg
import pytest
from conftest import SYNTHETIC_PASSWORD
from psycopg import sql
from work_storage_helpers import PASSWORD, connect

from app import work_drafts, work_restore
from app.config import settings
from app.manage import set_scope
from app.models import User
from app.work_manage import administer

pytestmark = pytest.mark.integration


@pytest.fixture
def case(review_case):
    with review_case["maker"].begin() as db:
        set_scope(db, db.get(User, review_case["actor"]), "technical_admin", True)
    return review_case


def run(case, **changes):
    values = {
        "workspace_id": case["workspace"],
        "operator_id": case["actor"],
        "restored_database": settings.postgres_db,
    }
    values.update(changes)
    with connect() as db, db.transaction():
        return work_restore.reconcile(db, work_restore.Request(**values))


def apply(case, plan):
    return run(
        case,
        decision="quarantine_restored_workspace",
        issued_at=datetime.fromisoformat(plan["issued_at"]),
        reviewed_hash=plan["reviewed_hash"],
    )


def snapshot(case):
    with connect() as db:
        return (
            db.execute(
                "SELECT is_active FROM public.work_workspaces WHERE id=%s", (case["workspace"],)
            ).fetchone()[0],
            db.execute(
                "SELECT count(*) FROM public.work_access_grants WHERE workspace_id=%s",
                (case["workspace"],),
            ).fetchone()[0],
            db.execute(
                "SELECT count(*) FROM public.auth_sessions WHERE user_id=%s AND revoked_at IS NULL",
                (case["actor"],),
            ).fetchone()[0],
            db.execute(
                "SELECT count(*) FROM public.audit_events WHERE entity_id=%s AND event_type='admin.work_restore_quarantined'",
                (str(case["workspace"]),),
            ).fetchone()[0],
        )


def session(db, user):
    identifier = uuid4()
    db.execute(
        "INSERT INTO public.auth_sessions(id,user_id,token_hash,csrf_hash,created_at,last_seen_at,expires_at) VALUES(%s,%s,%s,%s,clock_timestamp(),clock_timestamp(),clock_timestamp()+interval '1 hour')",
        (identifier, user, uuid4().hex * 2, uuid4().hex * 2),
    )
    return identifier


def test_exact_quarantine_cross_scope_signout_and_unrelated_preservation(case):
    foreign = case["storage"]["b"]
    with case["maker"].begin() as db:
        administer(db, "grant", foreign["slug"], db.get(User, case["actor"]).slug)
    with connect() as db:
        session(db, case["actor"])
        other = uuid4()
        db.execute(
            "INSERT INTO public.users(id,slug,display_name,is_active,created_at,updated_at) VALUES(%s,%s,'Synthetic unrelated',true,clock_timestamp(),clock_timestamp())",
            (other, "synthetic-" + uuid4().hex),
        )
        unrelated = session(db, other)
        before = db.execute(
            "SELECT snapshot FROM work.drafts WHERE id=%s", (case["item"].id,)
        ).fetchone()[0]
    plan = run(case)
    assert (
        len(plan["grantees"]) == 1 and len(plan["sessions"]) == 2 and plan["cross_scope_sign_out"]
    )
    assert run(case, issued_at=datetime.fromisoformat(plan["issued_at"])) == plan
    assert snapshot(case) == (True, 1, 2, 0)
    for secret in ("token_hash", "csrf_hash", case["slug"], "review-note", str(case["source"])):
        assert secret not in json.dumps(plan)
    result = apply(case, plan)
    assert result["workspace_enabled"] is False and result["recovery_complete"] is False
    assert result["previous_workspace_enabled"] is True
    assert snapshot(case) == (False, 0, 0, 1)
    assert case["client"].get("/api/v1/work/workspaces").status_code == 401
    with connect() as db:
        assert (
            db.execute(
                "SELECT snapshot FROM work.drafts WHERE id=%s", (case["item"].id,)
            ).fetchone()[0]
            == before
        )
        assert (
            db.execute(
                "SELECT is_active FROM public.work_workspaces WHERE id=%s", (foreign["workspace"],)
            ).fetchone()[0]
            is True
        )
        assert (
            db.execute(
                "SELECT count(*) FROM public.work_access_grants WHERE workspace_id=%s AND user_id=%s",
                (foreign["workspace"], case["actor"]),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT revoked_at FROM public.auth_sessions WHERE id=%s", (unrelated,)
            ).fetchone()[0]
            is None
        )
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s", (result["receipt_id"],)
            ).fetchone()[0]
            == result
        )
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    with case["maker"]() as db:
        slug = db.get(User, case["actor"]).slug
    assert (
        case["client"]
        .post("/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD})
        .status_code
        == 200
    )
    remaining = case["client"].get("/api/v1/work/workspaces").json()["items"]
    assert [row["id"] for row in remaining] == [str(foreign["workspace"])]
    empty = run(case)
    with pytest.raises(ValueError, match="already quarantined"):
        apply(case, empty)


@pytest.mark.parametrize(
    "fault",
    [
        "target",
        "missing",
        "non_synthetic",
        "operator",
        "inactive",
        "isolation",
        "assumed",
        "login",
        "idle",
        "future",
        "old",
    ],
)
def test_fail_closed_identity_target_time_and_role(case, fault):
    changes = {}
    if fault == "target":
        changes["restored_database"] = "butler_test_wrong_restore"
    if fault == "missing":
        changes["workspace_id"] = uuid4()
    if fault in {"future", "old"}:
        changes["issued_at"] = datetime.now(UTC) + timedelta(minutes=1 if fault == "future" else -6)
    if fault == "operator":
        with case["maker"].begin() as db:
            set_scope(db, db.get(User, case["actor"]), "technical_admin", False)
    if fault in {"inactive", "non_synthetic"}:
        with connect() as db:
            if fault == "inactive":
                db.execute("UPDATE public.users SET is_active=false WHERE id=%s", (case["actor"],))
            else:
                db.execute(
                    "UPDATE public.work_workspaces SET slug=%s WHERE id=%s",
                    ("ordinary-" + uuid4().hex, case["workspace"]),
                )
    before = snapshot(case)
    if fault == "idle":
        with pytest.raises(ValueError), connect() as db:
            work_restore.reconcile(
                db,
                work_restore.Request(
                    workspace_id=case["workspace"],
                    operator_id=case["actor"],
                    restored_database=settings.postgres_db,
                ),
            )
    elif fault in {"isolation", "assumed", "login"}:
        with (
            pytest.raises((ValueError, psycopg.Error)),
            connect(
                case["login"] if fault == "login" else None, PASSWORD if fault == "login" else None
            ) as db,
            db.transaction(),
        ):
            if fault == "isolation":
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            if fault == "assumed":
                db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(case["role"])))
            work_restore.reconcile(
                db,
                work_restore.Request(
                    workspace_id=case["workspace"],
                    operator_id=case["actor"],
                    restored_database=settings.postgres_db,
                ),
            )
    else:
        with pytest.raises((ValueError, psycopg.Error)):
            run(case, **changes)
    assert snapshot(case) == before


@pytest.mark.parametrize("change", ["new_session", "seen", "grant"])
def test_changed_review_rejects_every_mutation(case, change):
    plan = run(case)
    with connect() as db:
        if change == "new_session":
            session(db, case["actor"])
        elif change == "seen":
            db.execute(
                "UPDATE public.auth_sessions SET last_seen_at=clock_timestamp() WHERE user_id=%s",
                (case["actor"],),
            )
        else:
            db.execute(
                "DELETE FROM public.work_access_grants WHERE workspace_id=%s", (case["workspace"],)
            )
    before = snapshot(case)
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    assert snapshot(case) == before


@pytest.mark.parametrize("bound", ["grantees", "sessions"])
def test_caps_do_not_silently_truncate(case, bound):
    with connect() as db:
        for _ in range(25 if bound == "grantees" else 100):
            user = case["actor"]
            if bound == "grantees":
                user = uuid4()
                db.execute(
                    "INSERT INTO public.users(id,slug,display_name,is_active,created_at,updated_at) VALUES(%s,%s,'Synthetic cap',true,clock_timestamp(),clock_timestamp())",
                    (user, "synthetic-" + uuid4().hex),
                )
                db.execute(
                    "INSERT INTO public.work_access_grants(user_id,workspace_id,capability,created_at) VALUES(%s,%s,'work_private',clock_timestamp())",
                    (user, case["workspace"]),
                )
            else:
                session(db, user)
    before = snapshot(case)
    with pytest.raises(ValueError, match="Too many"):
        run(case)
    assert snapshot(case) == before


def test_audit_failure_rolls_back_disable_grants_and_sessions(case):
    plan = run(case)
    before = snapshot(case)
    name = "synthetic_quarantine_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE public.audit_events ADD CONSTRAINT {} CHECK(event_type<>'admin.work_restore_quarantined') NOT VALID"
            ).format(sql.Identifier(name))
        )
    try:
        with pytest.raises(psycopg.Error):
            apply(case, plan)
        assert snapshot(case) == before
        assert run(case, issued_at=datetime.fromisoformat(plan["issued_at"])) == plan
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE public.audit_events DROP CONSTRAINT {}").format(
                    sql.Identifier(name)
                )
            )


def test_expiry_before_commit_rolls_back(case, monkeypatch):
    plan = run(case)
    before = snapshot(case)
    original = work_drafts._now
    calls = 0

    def late(db):
        nonlocal calls
        calls += 1
        return original(db) + timedelta(minutes=6) if calls >= 3 else original(db)

    monkeypatch.setattr(work_drafts, "_now", late)
    with pytest.raises(ValueError, match="current server"):
        apply(case, plan)
    assert snapshot(case) == before


def test_concurrent_apply_is_once_and_registry_wait_is_bounded(case):
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
    start = Event()

    def cleaner():
        assert start.wait(4)
        try:
            apply(case, plan)
            return "applied"
        except ValueError:
            return "stale"

    with ThreadPoolExecutor(2) as pool:
        first, second = pool.submit(cleaner), pool.submit(cleaner)
        start.set()
        assert sorted([first.result(timeout=8), second.result(timeout=8)]) == ["applied", "stale"]
    assert snapshot(case) == (False, 0, 0, 1)


def test_active_workspace_without_grants_can_be_quarantined(case):
    foreign = dict(case, workspace=case["storage"]["b"]["workspace"])
    plan = run(foreign)
    assert plan["workspace_enabled"] and not plan["grantees"] and not plan["sessions"]
    result = apply(foreign, plan)
    assert result["removed_grantees"] == [] and result["revoked_sessions"] == []
    assert snapshot(case) == (True, 1, 1, 0)
