"""Synthetic current/copied role inventory and actual maintenance CLI revocation."""

import json
import subprocess
import sys
from uuid import UUID

import psycopg
from psycopg import sql

from app.config import settings
from app.work_credentials import login_name
from app.work_storage import role_name

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)
workspace = UUID("fa000000-1111-4111-8111-111111111111")
operator = UUID("fb000000-1111-4111-8111-111111111111")
secret = "synthetic-credential-recovery-only-0123456789"
with psycopg.connect(url) as db:
    db.execute(
        "INSERT INTO public.users(id,slug,display_name,is_active,created_at,updated_at) VALUES(%s,'synthetic-credential-recovery','Synthetic',true,now(),now())",
        (operator,),
    )
    db.execute(
        "INSERT INTO public.user_scopes(user_id,scope_id,created_at) SELECT %s,id,now() FROM public.scopes WHERE key='technical_admin'",
        (operator,),
    )
    db.execute(
        "INSERT INTO public.work_workspaces(id,slug,is_active,created_at) VALUES(%s,'synthetic-credential-recovery',false,now())",
        (workspace,),
    )
    current = db.execute("SELECT oid FROM pg_database WHERE datname=current_database()").fetchone()[
        0
    ]
    orphan = 4100000001
    assert not db.execute("SELECT 1 FROM pg_database WHERE oid=%s", (orphan,)).fetchone()
    names = []
    for namespace in (current, orphan):
        role, login = role_name(namespace, workspace), login_name(namespace, workspace)
        for name in (role, login):
            db.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(name)))
        db.execute(
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(login), sql.Literal(secret)
            )
        )
        db.execute(
            sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                sql.Identifier(role), sql.Identifier(login)
            )
        )
        names.extend([login, role])


def cli(*args, success=True):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.restore_credentials",
            "--environment",
            "test",
            "--restored-database",
            settings.postgres_db,
            "--operator",
            str(operator),
            "--workspace",
            str(workspace),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (result.returncode == 0) == success, result.stderr
    assert (
        secret not in result.stdout + result.stderr and "SCRAM" not in result.stdout + result.stderr
    )
    return json.loads(result.stdout) if success else None


def login_succeeds(name):
    with psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=name,
        password=secret,
        connect_timeout=3,
    ) as db:
        assert db.execute("SELECT session_user").fetchone() == (name,)


try:
    inventory = cli()
    assert len(inventory["inventory"]) == 2 and not inventory["selected_profiles_verified"]
    selection = [
        value
        for namespace in sorted([current, orphan])
        for value in ("--namespace-oid", str(namespace))
    ]
    for namespace in (current, orphan):
        login_succeeds(login_name(namespace, workspace))
    plan = cli(*selection)
    apply = [
        *selection,
        "--issued-at",
        plan["issued_at"],
        "--reviewed-hash",
        plan["reviewed_hash"],
        "--decision",
        "revoke_restored_credentials",
    ]
    receipt = cli(*apply)
    assert (
        receipt["post_commit_inspection_required"]
        and not receipt["recovery_complete"]
        and not receipt["activation_authorized"]
    )
    cli(*apply, success=False)
    after = cli(*selection)
    assert all(
        not item["login"]["can_login"] and item["connections"] == 0 for item in after["inventory"]
    )
    for namespace in (current, orphan):
        try:
            login_succeeds(login_name(namespace, workspace))
        except psycopg.OperationalError:
            pass
        else:
            raise AssertionError("Revoked synthetic credential connected")
    with psycopg.connect(url) as db:
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s",
                (receipt["receipt_id"],),
            ).fetchone()[0]
            == receipt
        )
        assert db.execute(
            "SELECT is_active FROM public.work_workspaces WHERE id=%s", (workspace,)
        ).fetchone() == (False,)
    print(
        "Current/orphan Work credential inventory, exact CLI revocation, replay denial and TCP refusal verified"
    )
finally:
    with psycopg.connect(url) as db:
        for name in names:
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))
