"""Serialize work registry mutations against transaction-bound access checks.

Revision ID: 0008_work_authority
Revises: 0007_work_storage
"""

from alembic import op

revision = "0008_work_authority"
down_revision = "0007_work_storage"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE FUNCTION public.butler_work_registry_barrier() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      BEGIN
        IF TG_OP='TRUNCATE' THEN
          RAISE EXCEPTION 'Work registry truncate is not supported' USING ERRCODE='23514';
        END IF;
        PERFORM pg_catalog.pg_advisory_xact_lock(1508310,1);
        RETURN NULL;
      END; $$;
      REVOKE ALL ON FUNCTION public.butler_work_registry_barrier() FROM PUBLIC;
    """)
    for table in ("work_workspaces", "work_access_grants"):
        op.execute(f"""
          CREATE TRIGGER work_registry_barrier BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE
          ON public.{table} FOR EACH STATEMENT
          EXECUTE FUNCTION public.butler_work_registry_barrier();
        """)


def downgrade():
    for table in ("work_workspaces", "work_access_grants"):
        op.execute(f"DROP TRIGGER work_registry_barrier ON public.{table}")
    op.execute("DROP FUNCTION public.butler_work_registry_barrier()")
