"""Disposable copied non-Work sessions and reviewed global restored sign-out."""

import json
import subprocess
import sys
from uuid import UUID

import psycopg
from app import identity
from app.config import settings
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
phase = sys.argv[1]
assert phase in {"seed", "check", "container"}
actor = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
users = [
    UUID("f1000000-1111-4111-8111-111111111111"),
    UUID("f2000000-1111-4111-8111-111111111111"),
]
sessions = {n: UUID(f"f3000000-1111-4111-8111-11111111111{n}") for n in range(1, 5)}
url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)


def token(n):
    return "synthetic-global-restored-session-" + str(n) + "-" + "a" * 48


if phase in {"seed", "container"}:
    with psycopg.connect(url) as db:
        for n, user in enumerate(users):
            db.execute(
                "INSERT INTO public.users(id,slug,display_name,is_active,created_at,updated_at) VALUES(%s,%s,'Synthetic non-Work restore',true,clock_timestamp(),clock_timestamp())",
                (user, f"synthetic-global-session-{n}"),
            )
            db.execute(
                "INSERT INTO public.auth_credentials(user_id,password_hash,changed_at) VALUES(%s,%s,clock_timestamp())",
                (
                    user,
                    identity.password_hash(
                        "synthetic-session-recovery-password-only-0123456789"
                    ),
                ),
            )
            db.execute(
                "INSERT INTO public.user_scopes(user_id,scope_id,created_at) SELECT %s,id,clock_timestamp() FROM public.scopes WHERE key=%s",
                (user, "household_shared" if n == 0 else "finance_private"),
            )
        for n in range(1, 5):
            db.execute(
                "INSERT INTO public.auth_sessions(id,user_id,token_hash,csrf_hash,created_at,last_seen_at,expires_at,revoked_at) VALUES(%s,%s,%s,%s,clock_timestamp()-interval '2 hours',clock_timestamp(),clock_timestamp()+%s::interval,CASE WHEN %s THEN clock_timestamp()-interval '1 hour' ELSE NULL END)",
                (
                    sessions[n],
                    users[1] if n in {2, 4} else users[0],
                    identity.digest(token(n)),
                    identity.digest("synthetic-csrf-" + str(n)),
                    "-1 hour" if n == 3 else "1 hour",
                    n == 4,
                ),
            )
        # Force more than one reviewed 100-row batch even on a fresh container database.
        for n in range(1, 102):
            identifier = UUID(f"f4000000-1111-4111-8111-{n:012x}")
            db.execute(
                "INSERT INTO public.auth_sessions(id,user_id,token_hash,csrf_hash,created_at,last_seen_at,expires_at) VALUES(%s,%s,%s,%s,clock_timestamp(),clock_timestamp(),clock_timestamp()+interval '1 hour')",
                (
                    identifier,
                    users[0],
                    identity.digest(
                        "synthetic-extra-session-" + str(n) + "-" + "e" * 48
                    ),
                    identity.digest("synthetic-extra-csrf-" + str(n)),
                ),
            )


def unchanged(db):
    tables = [
        ("public", name)
        for name in (
            "users",
            "auth_credentials",
            "user_scopes",
            "work_workspaces",
            "work_access_grants",
            "approvals",
            "durable_jobs",
            "job_outbox",
            "memory_records",
        )
    ] + [("work", "drafts"), ("work", "parties")]
    return {
        (schema, table): db.execute(
            sql.SQL("SELECT * FROM {}.{} ORDER BY 1,2").format(
                sql.Identifier(schema), sql.Identifier(table)
            )
        ).fetchall()
        for schema, table in tables
    }


def command(*args, success=True):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.restore_sessions",
            "--environment",
            "test",
            "--restored-database",
            settings.postgres_db,
            "--operator",
            str(actor),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == success, "Synthetic restored-session CLI failed"
    if success:
        return json.loads(result.stdout)
    assert not result.stdout and "inspect metadata/receipt" in result.stderr


if phase != "seed":
    engine = create_engine(settings.database_url)
    with Session(engine) as db, db.begin():
        assert identity.resolve(db, token(1)) is not None
        assert identity.resolve(db, token(2)) is not None
    with psycopg.connect(url) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM public.work_access_grants WHERE user_id=ANY(%s)",
                (users,),
            ).fetchone()[0]
            == 0
        )
        before = unchanged(db)
        revoked_before = db.execute(
            "SELECT revoked_at FROM public.auth_sessions WHERE id=%s", (sessions[4],)
        ).fetchone()[0]
    batches = 0
    for _ in range(50):
        plan = command()
        assert plan["items"] and len(plan["items"]) <= 100
        if batches == 0:
            assert len(plan["items"]) == 100 and plan["has_more"]
        encoded = json.dumps(plan)
        assert (
            "token_hash" not in encoded
            and "csrf_hash" not in encoded
            and "password_hash" not in encoded
            and token(1) not in encoded
        )
        args = (
            "--issued-at",
            plan["issued_at"],
            "--reviewed-hash",
            plan["reviewed_hash"],
            "--decision",
            "revoke_restored_sessions",
        )
        result = command(*args)
        batches += 1
        assert not result["api_activated"] and not result["recovery_complete"]
        command(*args, success=False)  # Must not advance into the next current batch.
        with psycopg.connect(url) as db:
            assert (
                db.execute(
                    "SELECT metadata_json FROM public.audit_events WHERE id=%s",
                    (result["receipt_id"],),
                ).fetchone()[0]
                == result
            )
        if result["session_set_clear_at_commit"]:
            assert not result["remaining_unrevoked"]
            break
    else:
        raise AssertionError("Synthetic session quarantine did not converge")
    assert batches >= 2
    with psycopg.connect(url) as db:
        assert unchanged(db) == before
        assert (
            db.execute(
                "SELECT count(*) FROM public.auth_sessions WHERE revoked_at IS NULL"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT revoked_at FROM public.auth_sessions WHERE id=%s",
                (sessions[3],),
            ).fetchone()[0]
            is not None
        )
        assert (
            db.execute(
                "SELECT revoked_at FROM public.auth_sessions WHERE id=%s",
                (sessions[4],),
            ).fetchone()[0]
            == revoked_before
        )
    with Session(engine) as db, db.begin():
        assert identity.resolve(db, token(1)) is None
        assert identity.resolve(db, token(2)) is None
    engine.dispose()
    empty = command()
    assert not empty["items"] and not empty["has_more"]
    command(
        "--issued-at",
        empty["issued_at"],
        "--reviewed-hash",
        empty["reviewed_hash"],
        "--decision",
        "revoke_restored_sessions",
        success=False,
    )
print(
    "Synthetic non-Work restored sessions seeded; no credentials/tokens displayed"
    if phase == "seed"
    else "Synthetic global restored-session batches/non-Work token denial/credential preservation verified; no credentials/tokens displayed"
)
