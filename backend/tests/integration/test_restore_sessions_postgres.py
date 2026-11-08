"""All-scope restored sign-out, bounded replay, real identity fencing and atomicity."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from conftest import RUNTIME_PASSWORD, SYNTHETIC_PASSWORD
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from work_storage_helpers import connect

from app import identity, work_drafts
from app import restore_sessions as recovery
from app.config import settings
from app.manage import provision, set_scope
from app.models import User

pytestmark = pytest.mark.integration


def session(db, user, *, expired=False, revoked=False, identifier=None):
    identifier = identifier or UUID(int=uuid4().int & ((1 << 64) - 1))
    token = "synthetic-restored-session-" + uuid4().hex * 2
    db.execute(
        "INSERT INTO public.auth_sessions(id,user_id,token_hash,csrf_hash,created_at,last_seen_at,expires_at,revoked_at) VALUES(%s,%s,%s,%s,clock_timestamp()-interval '2 hours',clock_timestamp(),clock_timestamp()+%s::interval,CASE WHEN %s THEN clock_timestamp()-interval '1 hour' ELSE NULL END)",
        (
            identifier,
            user,
            identity.digest(token),
            identity.digest(uuid4().hex),
            "-1 hour" if expired else "1 hour",
            revoked,
        ),
    )
    return identifier, token


@pytest.fixture
def case(scenario, runtime_engine):
    client, headers, _, admin, user = scenario
    with admin.begin() as db:
        operator = db.get(User, user)
        set_scope(db, operator, "technical_admin", True)
        slug = operator.slug
        other = provision(
            db,
            "synthetic-" + uuid4().hex,
            "Synthetic unrelated",
            SYNTHETIC_PASSWORD,
            {"finance_private"},
        )
        foreign = other.id
    with connect() as db:
        active, token = session(db, foreign)
        expired, _ = session(db, foreign, expired=True)
        revoked, _ = session(db, user, revoked=True)
    return {
        "operator": user,
        "slug": slug,
        "client": client,
        "headers": headers,
        "token": token,
        "active": active,
        "expired": expired,
        "revoked": revoked,
        "runtime": sessionmaker(bind=runtime_engine, expire_on_commit=False),
    }


def request(case, **changes):
    return recovery.Request(
        **({"restored_database": settings.postgres_db, "operator_id": case["operator"]} | changes)
    )


def run(case, **changes):
    with connect() as db, db.transaction():
        return recovery.reconcile(db, request(case, **changes))


def apply(case, plan, **changes):
    return run(
        case,
        limit=plan["limit"],
        issued_at=datetime.fromisoformat(plan["issued_at"]),
        reviewed_hash=plan["reviewed_hash"],
        decision="revoke_restored_sessions",
        **changes,
    )


def drain(case):
    for _ in range(30):
        plan = run(case)
        if not plan["items"]:
            return
        result = apply(case, plan)
        if result["session_set_clear_at_commit"]:
            return
    raise AssertionError("Synthetic session batch did not converge")


def snapshot(case):
    with connect() as db:
        return (
            db.execute("SELECT * FROM public.auth_sessions ORDER BY id").fetchall(),
            db.execute(
                "SELECT count(*) FROM public.audit_events WHERE event_type='admin.restored_sessions_revoked' AND metadata_json::jsonb->>'operator_id'=%s",
                (str(case["operator"]),),
            ).fetchone()[0],
        )


def preserved():
    tables = (
        "users",
        "user_scopes",
        "auth_credentials",
        "approvals",
        "durable_jobs",
        "job_outbox",
        "memory_records",
        "work_workspaces",
        "work_access_grants",
    )
    with connect() as db:
        return {
            table: db.execute(
                sql.SQL("SELECT * FROM public.{} ORDER BY 1,2").format(sql.Identifier(table))
            ).fetchall()
            for table in tables
        }


def test_global_non_work_and_expired_signout_preserves_credentials_and_later_login(case):
    with case["runtime"].begin() as db:
        assert identity.resolve(db, case["token"]) is not None
    before = preserved()
    with connect() as db:
        revoked_before = db.execute(
            "SELECT revoked_at FROM public.auth_sessions WHERE id=%s", (case["revoked"],)
        ).fetchone()[0]
        assert (
            db.execute(
                "SELECT count(*) FROM public.work_access_grants WHERE user_id=ANY(%s)",
                (
                    [
                        case["operator"],
                        db.execute(
                            "SELECT user_id FROM public.auth_sessions WHERE id=%s",
                            (case["active"],),
                        ).fetchone()[0],
                    ],
                ),
            ).fetchone()[0]
            == 0
        )
    plan = run(case)
    encoded = json.dumps(plan)
    for hidden in ("token_hash", "csrf_hash", "password_hash", case["token"], case["slug"]):
        assert hidden not in encoded
    assert run(case, issued_at=datetime.fromisoformat(plan["issued_at"])) == plan
    drain(case)
    assert preserved() == before
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM public.auth_sessions WHERE revoked_at IS NULL"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT revoked_at FROM public.auth_sessions WHERE id=%s", (case["expired"],)
            ).fetchone()[0]
            is not None
        )
        assert (
            db.execute(
                "SELECT revoked_at FROM public.auth_sessions WHERE id=%s", (case["revoked"],)
            ).fetchone()[0]
            == revoked_before
        )
        metadata = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE event_type='admin.restored_sessions_revoked' AND metadata_json::jsonb->>'operator_id'=%s ORDER BY occurred_at DESC LIMIT 1",
            (str(case["operator"]),),
        ).fetchone()[0]
        assert (
            metadata["session_set_clear_at_commit"]
            and not metadata["recovery_complete"]
            and not metadata["api_activated"]
        )
    with case["runtime"].begin() as db:
        assert identity.resolve(db, case["token"]) is None
    assert case["client"].get("/api/v1/auth/me").status_code == 401
    with pytest.raises(ValueError, match="No unrevoked"):
        apply(case, run(case))
    response = case["client"].post(
        "/api/v1/auth/login", json={"slug": case["slug"], "password": SYNTHETIC_PASSWORD}
    )
    assert response.status_code == 200
    assert case["client"].get("/api/v1/auth/me").status_code == 200


def test_bounded_batch_replay_never_advances_to_next(case):
    plan = run(case, limit=1)
    assert len(plan["items"]) == 1 and plan["has_more"]
    result = apply(case, plan)
    assert result["remaining_unrevoked"] and not result["session_set_clear_at_commit"]
    before = snapshot(case)
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    assert snapshot(case) == before
    next_plan = run(case, limit=1)
    assert next_plan["items"][0]["id"] != plan["items"][0]["id"]
    apply(case, next_plan)
    drain(case)


@pytest.mark.parametrize(
    "fault",
    [
        "target",
        "operator",
        "inactive",
        "scope",
        "runtime",
        "assumed",
        "isolation",
        "idle",
        "future",
        "old",
    ],
)
def test_invalid_target_authority_role_time_is_atomic(case, fault):
    changes = {}
    if fault == "target":
        changes["restored_database"] = "butler_test_wrong"
    if fault == "operator":
        changes["operator_id"] = uuid4()
    if fault == "inactive":
        with connect() as db:
            db.execute("UPDATE public.users SET is_active=false WHERE id=%s", (case["operator"],))
    if fault == "scope":
        with connect() as db:
            db.execute(
                "DELETE FROM public.user_scopes WHERE user_id=%s AND scope_id=(SELECT id FROM public.scopes WHERE key='technical_admin')",
                (case["operator"],),
            )
    if fault in {"future", "old"}:
        changes["issued_at"] = datetime.now(UTC) + timedelta(minutes=1 if fault == "future" else -6)
    before = snapshot(case)
    if fault in {"runtime", "assumed", "isolation", "idle"}:
        with (
            pytest.raises((ValueError, psycopg.Error)),
            connect(
                "butler_runtime" if fault == "runtime" else None,
                RUNTIME_PASSWORD if fault == "runtime" else None,
            ) as db,
        ):
            if fault != "idle":
                db.execute("BEGIN")
            if fault == "assumed":
                db.execute("SET LOCAL ROLE butler_runtime")
            if fault == "isolation":
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            recovery.reconcile(db, request(case))
    else:
        with pytest.raises(ValueError):
            run(case, **changes)
    assert snapshot(case) == before


@pytest.mark.parametrize("change", ["seen", "revoked", "new_first", "limit"])
def test_changed_batch_review_cannot_revoke_anything(case, change):
    plan = run(case, limit=1)
    if change != "limit":
        with connect() as db:
            if change == "seen":
                db.execute(
                    "UPDATE public.auth_sessions SET last_seen_at=clock_timestamp() WHERE id=%s",
                    (UUID(plan["items"][0]["id"]),),
                )
            elif change == "revoked":
                db.execute(
                    "UPDATE public.auth_sessions SET revoked_at=clock_timestamp() WHERE id=%s",
                    (UUID(plan["items"][0]["id"]),),
                )
            else:
                session(db, case["operator"], identifier=UUID(int=1))
    before = snapshot(case)
    with pytest.raises(ValueError, match="Plan changed"):
        if change == "limit":
            run(
                case,
                limit=2,
                issued_at=datetime.fromisoformat(plan["issued_at"]),
                reviewed_hash=plan["reviewed_hash"],
                decision="revoke_restored_sessions",
            )
        else:
            apply(case, plan)
    assert snapshot(case) == before


def test_audit_failure_and_final_expiry_roll_back_batch(case, monkeypatch):
    plan = run(case)
    before = snapshot(case)
    name = "synthetic_sessions_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "ALTER TABLE public.audit_events ADD CONSTRAINT {} CHECK(event_type<>'admin.restored_sessions_revoked') NOT VALID"
            ).format(sql.Identifier(name))
        )
    try:
        with pytest.raises(psycopg.Error):
            apply(case, plan)
        assert snapshot(case) == before
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
    assert snapshot(case) == before


def test_busy_resolver_fails_fast_without_changes(case):
    before = snapshot(case)
    with case["runtime"].begin() as db:
        assert identity.resolve(db, case["token"]) is not None
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(run, case)
            with pytest.raises(psycopg.errors.LockNotAvailable):
                future.result(timeout=4)
    assert snapshot(case) == before
    drain(case)


def test_cleanup_blocks_concurrent_resolver_then_denies_old_token(case):
    # Ensure our copied token is part of this reviewed batch.
    drain(case)
    with connect() as db:
        identifier, token = session(db, case["operator"])
    plan = run(case)
    assert [row["id"] for row in plan["items"]] == [str(identifier)]
    with connect() as owner, owner.transaction():
        recovery.reconcile(
            owner,
            request(
                case,
                issued_at=datetime.fromisoformat(plan["issued_at"]),
                reviewed_hash=plan["reviewed_hash"],
                decision="revoke_restored_sessions",
            ),
        )

        def resolve():
            with case["runtime"].begin() as db:
                db.execute(text("SET LOCAL lock_timeout='200ms'"))
                return identity.resolve(db, token)

        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(resolve)
            with pytest.raises(DBAPIError):
                future.result(timeout=4)
    with case["runtime"].begin() as db:
        assert identity.resolve(db, token) is None


def test_concurrent_cleaners_do_not_double_apply(case):
    plan = run(case, limit=1)

    def cleaner():
        try:
            apply(case, plan)
            return "applied"
        except (ValueError, psycopg.errors.LockNotAvailable):
            return "rejected"

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(cleaner), pool.submit(cleaner)]
        assert sorted(f.result(timeout=5) for f in futures) == ["applied", "rejected"]


def test_max_batch_and_actual_cli(case):
    with connect() as db:
        for _ in range(101):
            session(db, case["operator"])
    base = [
        sys.executable,
        "-m",
        "app.restore_sessions",
        "--environment",
        "test",
        "--restored-database",
        settings.postgres_db,
        "--operator",
        str(case["operator"]),
    ]
    plan = json.loads(subprocess.check_output(base, text=True))
    assert len(plan["items"]) == 100 and plan["has_more"]
    args = [
        *base,
        "--issued-at",
        plan["issued_at"],
        "--reviewed-hash",
        plan["reviewed_hash"],
        "--decision",
        "revoke_restored_sessions",
    ]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert len(receipt["revoked_sessions"]) == 100 and receipt["remaining_unrevoked"]
    replay = subprocess.run(args, capture_output=True, text=True, check=False)
    assert replay.returncode != 0 and not replay.stdout
    drain(case)
