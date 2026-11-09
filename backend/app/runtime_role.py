"""Privileged development/test role setup. Never run from the web API."""

import os

import psycopg
from psycopg import sql

from app.config import settings

ROLE = "butler_runtime"


def configure(connection, password: str) -> None:
    if len(password) < 24 or "CHANGE_ME" in password.upper():
        raise ValueError("A distinct generated runtime password is required")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user, current_database()")
        owner, database = cursor.fetchone()
        if owner == ROLE:
            raise ValueError("Use the privileged migration connection")
        # This public namespace is a fresh-installation schema. Reject older or
        # unrelated databases before altering role credentials or privileges.
        expected_scopes = {
            "member_a_private",
            "member_b_private",
            "parents_child",
            "member_business",
        }
        cursor.execute(
            "SELECT key FROM public.scopes WHERE key = ANY(%s)", (list(expected_scopes),)
        )
        if {row[0] for row in cursor.fetchall()} != expected_scopes:
            raise ValueError(
                "Public snapshot requires a fresh generic-scope database; no role changes made"
            )
        cursor.execute("SELECT oid FROM pg_roles WHERE rolname = %s", (ROLE,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("SELECT 1 FROM pg_auth_members WHERE member = %s LIMIT 1", existing)
            if cursor.fetchone():
                raise ValueError("Runtime role has unreviewed memberships")
            cursor.execute(
                "SELECT 1 FROM pg_class WHERE relowner=%s UNION ALL SELECT 1 FROM pg_namespace WHERE nspowner=%s UNION ALL SELECT 1 FROM pg_database WHERE datdba=%s UNION ALL SELECT 1 FROM pg_proc WHERE proowner=%s LIMIT 1",
                existing * 4,
            )
            if cursor.fetchone():
                raise ValueError("Runtime role owns database objects")
        else:
            cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(ROLE)))
        cursor.execute("SET LOCAL password_encryption = 'scram-sha-256'")
        cursor.execute(
            sql.SQL(
                "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}"
            ).format(sql.Identifier(ROLE), sql.Literal(password))
        )
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {}").format(
                sql.Identifier(ROLE)
            )
        )
        # Reset column grants as well; table-level REVOKE does not erase them.
        cursor.execute(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public'"
        )
        columns_by_table = {}
        for table, column in cursor.fetchall():
            columns_by_table.setdefault(table, []).append(column)
        for table, columns in columns_by_table.items():
            cursor.execute(
                sql.SQL("REVOKE ALL PRIVILEGES ({}) ON TABLE public.{} FROM {}").format(
                    sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                    sql.Identifier(table),
                    sql.Identifier(ROLE),
                )
            )
        cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA public FROM {}").format(sql.Identifier(ROLE))
        )
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(
                sql.Identifier(database), sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL("REVOKE CREATE, TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(database)
            )
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database), sql.Identifier(ROLE)
            )
        )
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ROLE)))
        for table in (
            "users",
            "scopes",
            "user_scopes",
            "auth_credentials",
            "work_workspaces",
            "work_access_grants",
        ):
            cursor.execute(
                sql.SQL("GRANT SELECT ON TABLE public.{} TO {}").format(
                    sql.Identifier(table), sql.Identifier(ROLE)
                )
            )
        # PostgreSQL row locks require UPDATE on at least one column. Keep
        # account identity, active status and scope administration read-only.
        cursor.execute(
            sql.SQL("GRANT UPDATE (updated_at) ON public.users TO {}").format(sql.Identifier(ROLE))
        )
        cursor.execute(
            sql.SQL(
                "GRANT UPDATE (password_hash, changed_at) ON public.auth_credentials TO {}"
            ).format(sql.Identifier(ROLE))
        )
        for table in (
            "auth_sessions",
            "auth_rate_windows",
            "approvals",
            "durable_jobs",
            "job_outbox",
            "memory_records",
            "manual_tasks",
            "calendar_sources",
            "document_records",
            "task_reminders",
            "reminder_preferences",
        ):
            cursor.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE ON TABLE public.{} TO {}").format(
                    sql.Identifier(table), sql.Identifier(ROLE)
                )
            )
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT ON public.memory_revisions TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL("GRANT UPDATE (snapshot) ON public.memory_revisions TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT ON public.task_reminder_events TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT ON public.calendar_revisions TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL("GRANT UPDATE (snapshot) ON public.calendar_revisions TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT ON public.manual_task_revisions TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL("GRANT UPDATE (snapshot) ON public.manual_task_revisions TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT ON public.document_archive_bindings TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT ON public.document_versions TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL(
                "GRANT UPDATE (snapshot, original_bytes) ON public.document_versions TO {}"
            ).format(sql.Identifier(ROLE))
        )
        cursor.execute(
            sql.SQL("GRANT INSERT ON public.audit_events TO {}").format(sql.Identifier(ROLE))
        )
        cursor.execute(
            sql.SQL("GRANT SELECT ON public.work_confirmation_requests TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        cursor.execute(
            sql.SQL(
                "GRANT INSERT(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) ON public.work_confirmation_requests TO {}"
            ).format(sql.Identifier(ROLE))
        )
        # Verify only a bound digest receipt/deadline and lock the chosen private membership.
        # Runtime retains no SELECT on audit_events and no UPDATE on user_scopes.
        for function in (
            "butler_lock_discovery_scope(uuid,text)",
            "butler_lock_task_scope(uuid,text)",
            "butler_discovery_review_deadline(uuid,uuid,uuid,text,text,integer)",
        ):
            cursor.execute(
                sql.SQL("GRANT EXECUTE ON FUNCTION public.{} TO {}").format(
                    sql.SQL(function), sql.Identifier(ROLE)
                )
            )
        cursor.execute(
            sql.SQL("ALTER ROLE {} SET search_path TO pg_catalog, public").format(
                sql.Identifier(ROLE)
            )
        )


def main() -> None:
    if settings.env not in {"development", "test"}:
        raise RuntimeError("Role setup is development/test only")
    if settings.env == "test" and not settings.postgres_db.startswith("butler_test"):
        raise RuntimeError("Tests require a disposable butler_test database")
    password = os.environ.get("BUTLER_RUNTIME_PASSWORD", "")
    if password == settings.postgres_password.get_secret_value():
        raise ValueError("Runtime and migration credentials must differ")
    try:
        with psycopg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password.get_secret_value(),
            connect_timeout=5,
        ) as connection:
            configure(connection, password)
    except psycopg.Error:
        # Do not print DDL, role passwords, connection details or raw driver errors.
        raise RuntimeError(
            "Runtime role setup failed; review privileged database configuration"
        ) from None
    print("Restricted runtime role configured; no secrets displayed")


if __name__ == "__main__":
    main()
