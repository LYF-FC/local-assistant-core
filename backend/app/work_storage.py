"""Trusted synthetic work storage role provisioning; never called by the API.

Roles cannot log in and no user grant or application connection is created.
"""

import argparse
from uuid import UUID

import psycopg
from psycopg import sql

from app.config import settings


def role_name(database_oid: int, workspace_id: UUID) -> str:
    if type(database_oid) is not int or not 1 <= database_oid <= 4294967295:
        raise ValueError("Invalid database identity")
    if not isinstance(workspace_id, UUID):
        raise TypeError("Invalid workspace identity")
    return f"butler_work_{database_oid}_{workspace_id.hex}"


def provision(connection, workspace_slug: str) -> str:
    import re

    if not re.fullmatch(r"synthetic-[a-z0-9][a-z0-9_-]{0,53}", workspace_slug):
        raise ValueError("Use a synthetic workspace slug")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM public.work_workspaces WHERE slug=%s AND is_active FOR UPDATE",
            (workspace_slug,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError("Active synthetic workspace required")
        workspace_id = row[0]
        cursor.execute(
            "SELECT oid,datname FROM pg_catalog.pg_database WHERE datname=current_database()"
        )
        database_oid, database_name = cursor.fetchone()
        name = role_name(database_oid, workspace_id)
        role = sql.Identifier(name)
        cursor.execute(
            "SELECT oid,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
            "FROM pg_catalog.pg_roles WHERE rolname=%s",
            (name,),
        )
        existing = cursor.fetchone()
        if existing:
            if any(existing[1:]):
                raise ValueError("Existing work role has unreviewed elevated or login attributes")
            cursor.execute(
                "SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=%s LIMIT 1",
                (existing[0],),
            )
            if cursor.fetchone():
                raise ValueError("Existing work role has unreviewed memberships")
            cursor.execute(
                "SELECT 1 FROM pg_catalog.pg_class WHERE relowner=%s "
                "UNION ALL SELECT 1 FROM pg_catalog.pg_namespace WHERE nspowner=%s "
                "UNION ALL SELECT 1 FROM pg_catalog.pg_database WHERE datdba=%s "
                "UNION ALL SELECT 1 FROM pg_catalog.pg_proc WHERE proowner=%s LIMIT 1",
                (existing[0],) * 4,
            )
            if cursor.fetchone():
                raise ValueError("Existing work role owns database objects")
        else:
            cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(role))
        cursor.execute(
            sql.SQL(
                "ALTER ROLE {} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
            ).format(role)
        )
        cursor.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(sql.Identifier(database_name), role)
        )
        cursor.execute(
            "SELECT has_database_privilege(%s,%s,'CREATE,TEMPORARY'), has_schema_privilege(%s,'public','CREATE')",
            (name, database_name, name),
        )
        database_ddl, _ = cursor.fetchone()
        if database_ddl:
            raise ValueError(
                "Reviewed platform role setup must revoke PUBLIC database creation/temp privileges"
            )
        # Reset explicit table/column/function/schema grants on the two known namespaces.
        for schema in ("public", "work"):
            cursor.execute(
                sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}").format(
                    sql.Identifier(schema), role
                )
            )
            cursor.execute(
                "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=%s",
                (schema,),
            )
            for table, column in cursor.fetchall():
                cursor.execute(
                    sql.SQL("REVOKE ALL ({}) ON {}.{} FROM {}").format(
                        sql.Identifier(column), sql.Identifier(schema), sql.Identifier(table), role
                    )
                )
            cursor.execute(
                sql.SQL("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {} FROM {}").format(
                    sql.Identifier(schema), role
                )
            )
            cursor.execute(
                sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(sql.Identifier(schema), role)
            )
        cursor.execute("SELECT has_schema_privilege(%s,'public','CREATE')", (name,))
        if cursor.fetchone()[0]:
            raise ValueError("Reviewed platform role setup must revoke PUBLIC schema creation")
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA work TO {}").format(role))
        cursor.execute(
            sql.SQL(
                "GRANT SELECT ON work.active_workspace, work.validation_records, work.validation_audit, work.read_attempts TO {}"
            ).format(role)
        )
        cursor.execute(
            sql.SQL(
                "GRANT INSERT (workspace_id,id,marker) ON work.validation_records TO {}"
            ).format(role)
        )
        cursor.execute(
            sql.SQL(
                "GRANT INSERT (workspace_id,requested_by,session_id,event_type,record_count,record_ids,reason_code) ON work.read_attempts TO {}"
            ).format(role)
        )
        cursor.execute(sql.SQL("ALTER ROLE {} SET search_path TO pg_catalog,work").format(role))
        cursor.execute(
            "INSERT INTO public.audit_events "
            "(id,occurred_at,environment,initiator_type,initiator_id,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) "
            "VALUES (gen_random_uuid(),statement_timestamp(),%s,'local_admin','trusted_host_operator','technical_admin',"
            "'admin.work_storage_provisioned','work_access_registry',%s,'success','{}','{}')",
            (settings.env, str(workspace_id)),
        )
    return name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    if settings.env != args.environment:
        parser.error("Environment does not match the configured development/test target")
    if settings.env == "test" and not settings.postgres_db.startswith("butler_test"):
        parser.error("Storage validation requires a disposable butler_test database")
    try:
        with psycopg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password.get_secret_value(),
            connect_timeout=5,
        ) as connection:
            provision(connection, args.workspace)
    except psycopg.Error:
        raise RuntimeError(
            "Work storage provisioning failed; no login or content API enabled"
        ) from None
    print(
        "Synthetic workspace storage role provisioned; NOLOGIN, no user grant or content ingestion"
    )


if __name__ == "__main__":
    main()
