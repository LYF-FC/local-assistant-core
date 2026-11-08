"""Disposable-only restored session quarantine CLI sentinel; never operator data."""

import json
import subprocess
import sys
from uuid import UUID

import psycopg
from app import identity
from app.config import settings
from app.work_storage import role_name
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
phase = sys.argv[1]
assert phase in {"seed", "check", "container"}
workspace = UUID(
    "dadadada-dada-4ada-8ada-dadadadadada"
    if phase == "container"
    else "88888888-8888-4888-8888-888888888888"
)
actor = UUID(
    "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    if phase == "container"
    else "22222222-2222-4222-8222-222222222222"
)
session_id = UUID("fafafafa-fafa-4afa-8afa-fafafafafafa")
token = "synthetic-restored-session-only-" + "e" * 40
url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)
if phase in {"seed", "container"}:
    with psycopg.connect(url) as db:
        db.execute(
            "INSERT INTO public.user_scopes(user_id,scope_id,created_at) SELECT %s,id,clock_timestamp() FROM public.scopes WHERE key='technical_admin' ON CONFLICT DO NOTHING",
            (actor,),
        )
        if phase == "container":
            db.execute(
                "INSERT INTO public.work_access_grants(user_id,workspace_id,capability,created_at) VALUES(%s,%s,'work_private',clock_timestamp())",
                (actor, workspace),
            )
        db.execute(
            "INSERT INTO public.auth_sessions(id,user_id,token_hash,csrf_hash,created_at,last_seen_at,expires_at) VALUES(%s,%s,%s,%s,clock_timestamp(),clock_timestamp(),clock_timestamp()+interval '1 hour')",
            (
                session_id,
                actor,
                identity.digest(token),
                identity.digest("synthetic-csrf-only"),
            ),
        )
if phase != "seed":
    engine = create_engine(settings.database_url)
    with Session(engine) as db, db.begin():
        assert identity.resolve(db, token) is not None

    def command(*args, success=True):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.work_restore",
                "--environment",
                "test",
                "--restored-database",
                settings.postgres_db,
                "--workspace",
                str(workspace),
                "--operator",
                str(actor),
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert (result.returncode == 0) == success, (
            "Synthetic quarantine command failed"
        )
        if success:
            return json.loads(result.stdout)
        assert not result.stdout and "rolled back" in result.stderr

    with psycopg.connect(url) as db:
        before = db.execute(
            "SELECT id,snapshot FROM work.drafts WHERE workspace_id=%s ORDER BY id",
            (workspace,),
        ).fetchall()
    plan = command()
    assert plan["grantees"] == [str(actor)] and [
        item["id"] for item in plan["sessions"]
    ] == [str(session_id)]
    arguments = (
        "--issued-at",
        plan["issued_at"],
        "--reviewed-hash",
        plan["reviewed_hash"],
        "--decision",
        "quarantine_restored_workspace",
    )
    result = command(*arguments)
    assert result["workspace_enabled"] is False and result["recovery_complete"] is False
    command(*arguments, success=False)
    with psycopg.connect(url) as db:
        assert (
            db.execute(
                "SELECT is_active FROM public.work_workspaces WHERE id=%s", (workspace,)
            ).fetchone()[0]
            is False
        )
        assert (
            db.execute(
                "SELECT count(*) FROM public.work_access_grants WHERE workspace_id=%s",
                (workspace,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT revoked_at IS NOT NULL FROM public.auth_sessions WHERE id=%s",
                (session_id,),
            ).fetchone()[0]
            is True
        )
        assert (
            db.execute(
                "SELECT id,snapshot FROM work.drafts WHERE workspace_id=%s ORDER BY id",
                (workspace,),
            ).fetchall()
            == before
        )
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s",
                (result["receipt_id"],),
            ).fetchone()[0]
            == result
        )
    if phase == "check":
        with psycopg.connect(url) as db:
            oid = db.execute(
                "SELECT oid FROM pg_database WHERE datname=current_database()"
            ).fetchone()[0]
            db.execute(
                sql.SQL("SET LOCAL ROLE {}").format(
                    sql.Identifier(role_name(oid, workspace))
                )
            )
            assert (
                db.execute("SELECT count(*) FROM work.note_metadata").fetchone()[0] == 0
            )
            assert db.execute("SELECT count(*) FROM work.drafts").fetchone()[0] == 0
    with Session(engine) as db, db.begin():
        assert identity.resolve(db, token) is None
    engine.dispose()
print(
    "Synthetic restored-session fixture seeded; no credentials/content displayed"
    if phase == "seed"
    else "Synthetic restored-session quarantine CLI sentinel verified; no credentials/content displayed"
)
