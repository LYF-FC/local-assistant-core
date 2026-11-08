"""Trusted, quarantined synthetic login lifecycle; never called by the API."""

import argparse
import getpass
import re
import sys
import warnings
from uuid import UUID

import psycopg
from psycopg import sql

from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_storage import role_name


def login_name(database_oid: int, workspace_id: UUID) -> str:
    return role_name(database_oid, workspace_id).replace("butler_work_", "butler_wlogin_", 1)


def validate_password(password: str) -> None:
    if (
        not isinstance(password, str)
        or not 32 <= len(password) <= 256
        or not all(33 <= ord(c) <= 126 for c in password)
        or "CHANGE_ME" in password.upper()
        or password == settings.postgres_password.get_secret_value()
    ):
        raise ValueError("Use a distinct generated 32–256 character printable ASCII secret")


def validate_target(environment: str) -> None:
    if environment not in {"development", "test"} or settings.env != environment:
        raise ValueError("Explicit matching development/test environment required")
    if environment == "test" and not settings.postgres_db.startswith("butler_test"):
        raise ValueError("Tests require a disposable butler_test database")


def check_role(cursor, name: str, *, login: bool, expected_membership: str | None) -> None:
    cursor.execute(
        "SELECT oid,rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolconfig FROM pg_roles WHERE rolname=%s",
        (name,),
    )
    row = cursor.fetchone()
    if row is None or tuple(row[1:8]) != (login, False, False, False, False, False, False):
        raise ValueError("Unreviewed role profile")
    oid = row[0]
    if any(s.replace(" ", "") != "search_path=pg_catalog,work" for s in (row[8] or [])):
        raise ValueError("Unreviewed role settings")
    cursor.execute(
        "SELECT 1 FROM pg_class WHERE relowner=%s UNION ALL SELECT 1 FROM pg_namespace WHERE nspowner=%s UNION ALL SELECT 1 FROM pg_database WHERE datdba=%s UNION ALL SELECT 1 FROM pg_proc WHERE proowner=%s UNION ALL SELECT 1 FROM pg_db_role_setting WHERE setrole=%s AND setdatabase<>0 LIMIT 1",
        (oid,) * 5,
    )
    if cursor.fetchone():
        raise ValueError("Unreviewed ownership or database role settings")
    cursor.execute(
        "SELECT r.rolname,m.admin_option,m.inherit_option,m.set_option FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid WHERE m.member=%s",
        (oid,),
    )
    expected = [(expected_membership, False, False, True)] if expected_membership else []
    if cursor.fetchall() != expected:
        raise ValueError("Unreviewed role memberships")
    cursor.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m') AND (has_table_privilege(%s,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(%s,c.oid,'SELECT,INSERT,UPDATE,REFERENCES'))) OR has_database_privilege(%s,current_database(),'CREATE,TEMPORARY') OR has_schema_privilege(%s,'public','CREATE') OR has_schema_privilege(%s,'work','CREATE')",
        (name,) * 5,
    )
    if cursor.fetchone()[0]:
        raise ValueError("Unreviewed family or DDL privileges")
    if name.startswith("butler_wlogin_"):
        # A managed login has no direct object grants; only its one SET membership.
        cursor.execute(
            "SELECT 1 FROM (SELECT relacl AS acl FROM pg_class UNION ALL SELECT attacl FROM pg_attribute UNION ALL SELECT nspacl FROM pg_namespace UNION ALL SELECT proacl FROM pg_proc UNION ALL SELECT datacl FROM pg_database UNION ALL SELECT defaclacl FROM pg_default_acl) a CROSS JOIN LATERAL aclexplode(a.acl) p WHERE p.grantee=%s LIMIT 1",
            (oid,),
        )
        if cursor.fetchone():
            raise ValueError("Unreviewed direct grants")


def administer(connection, action: str, workspace_slug: str, password: str | None = None) -> None:
    """Caller owns commit/rollback. No secret, DSN, role or verifier is returned."""
    validate_target(settings.env)
    if action not in {"bootstrap", "rotate", "revoke"}:
        raise ValueError("Unknown credential action")
    if not re.fullmatch(r"synthetic-[a-z0-9][a-z0-9_-]{0,53}", workspace_slug):
        raise ValueError("Use a synthetic workspace slug")
    if action != "revoke":
        validate_password(password)
    elif password is not None:
        raise ValueError("Revoke takes no secret")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT session_user=current_user,rolsuper,current_setting('transaction_isolation') FROM pg_roles WHERE rolname=current_user"
        )
        if cursor.fetchone() != (True, True, "read committed"):
            raise ValueError("Clean privileged READ COMMITTED connection required")
        cursor.execute("SET LOCAL lock_timeout='2s'")
        cursor.execute("SET LOCAL statement_timeout='5s'")
        cursor.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
        cursor.execute(
            "SELECT id,is_active FROM public.work_workspaces WHERE slug=%s FOR UPDATE",
            (workspace_slug,),
        )
        workspace = cursor.fetchone()
        if workspace is None or workspace[1]:
            raise ValueError("Disabled synthetic workspace required; stop consumers first")
        workspace_id = workspace[0]
        cursor.execute("SELECT oid FROM pg_database WHERE datname=current_database()")
        database_oid = cursor.fetchone()[0]
        role = role_name(database_oid, workspace_id)
        login = login_name(database_oid, workspace_id)
        check_role(cursor, role, login=False, expected_membership=None)
        cursor.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname=%s", (login,))
        existing = cursor.fetchone()
        if action == "bootstrap":
            if existing is not None:
                raise ValueError("Reserved login already exists; review before reissue")
        else:
            if existing is None or (action == "rotate" and not existing[0]):
                raise ValueError("Current managed login required")
            check_role(
                cursor,
                login,
                login=existing[0],
                expected_membership=role if existing[0] else None,
            )
        cursor.execute("SELECT 1 FROM pg_stat_activity WHERE usename=%s LIMIT 1", (login,))
        if cursor.fetchone():
            raise ValueError("Drain all managed login sessions before changing credentials")
        principal = sql.Identifier(login)
        if action == "bootstrap":
            cursor.execute(
                sql.SQL(
                    "CREATE ROLE {} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                ).format(principal)
            )
        if action == "revoke":
            cursor.execute(sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(principal))
            if existing[0]:
                cursor.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(role), principal))
        else:
            # libpq derives the verifier locally. Raw secret never enters DDL/SQL logs.
            verifier = connection.pgconn.encrypt_password(
                password.encode("ascii"), login.encode("ascii"), b"scram-sha-256"
            ).decode("ascii")
            # Verifiers remain sensitive. Suppress ordinary statement/error logging
            # for this trusted transaction; host extensions/tracing remain trusted.
            cursor.execute("SET LOCAL log_statement='none'")
            cursor.execute("SET LOCAL log_min_duration_statement=-1")
            cursor.execute("SET LOCAL log_min_duration_sample=-1")
            cursor.execute("SET LOCAL log_min_error_statement='panic'")
            cursor.execute("SELECT (clock_timestamp()+interval '24 hours')::text")
            expiry = cursor.fetchone()[0]
            cursor.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {} VALID UNTIL {}").format(
                    principal, sql.Literal(verifier), sql.Literal(expiry)
                )
            )
            if action == "bootstrap":
                cursor.execute(
                    sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                        sql.Identifier(role), principal
                    )
                )
                cursor.execute(
                    sql.SQL("ALTER ROLE {} SET search_path TO pg_catalog,work").format(principal)
                )
            check_role(cursor, login, login=True, expected_membership=role)
        cursor.execute(
            "INSERT INTO public.audit_events (id,occurred_at,environment,initiator_type,initiator_id,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES (gen_random_uuid(),statement_timestamp(),%s,'local_admin','trusted_host_operator','technical_admin',%s,'work_access_registry',%s,'success','{}','{}')",
            (settings.env, "admin.work_credential_" + action, str(workspace_id)),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("action", choices=["bootstrap", "rotate", "revoke"])
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        password = None
        if args.action != "revoke":
            if not sys.stdin.isatty():
                raise ValueError("Hidden local TTY password entry required")
            with warnings.catch_warnings():
                # Refuse getpass's visible-input fallback if echo cannot be disabled.
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Generated workspace secret: ")
                confirmation = getpass.getpass("Confirm workspace secret: ")
            validate_password(password)
            if password != confirmation:
                raise ValueError("Secret confirmation differs")
        with psycopg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password.get_secret_value(),
            connect_timeout=5,
        ) as connection:
            administer(connection, args.action, args.workspace, password)
    except (psycopg.Error, ValueError, EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        # Driver exceptions may contain statement text/verifiers: never print them.
        parser.exit(
            1,
            "Credential operation failed; review disabled workspace, drained sessions and role configuration locally. No adapter activated.\n",
        )
    print("Synthetic credential operation committed; workspace and adapter remain disabled")


if __name__ == "__main__":
    main()
