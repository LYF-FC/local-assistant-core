"""Quarantined workspace storage probes; no content API or login credentials.

Revision ID: 0007_work_storage
Revises: 0006_work_access
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_work_storage"
down_revision = "0006_work_access"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA work")
    op.execute("REVOKE ALL ON SCHEMA work FROM PUBLIC")
    op.execute("""
    CREATE VIEW work.active_workspace WITH (security_barrier=true) AS
      SELECT w.id FROM public.work_workspaces AS w
      WHERE w.is_active AND current_user::text =
        'butler_work_' || (SELECT oid::text FROM pg_catalog.pg_database
                         WHERE datname=pg_catalog.current_database()) || '_' ||
        pg_catalog.replace(w.id::text,'-','');
    CREATE TABLE work.validation_records (
      workspace_id uuid NOT NULL REFERENCES public.work_workspaces(id),
      id uuid NOT NULL,
      marker text NOT NULL CHECK (octet_length(marker) BETWEEN 11 AND 256
                                 AND marker ~ '^synthetic:[a-zA-Z0-9 _.-]+$'),
      created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
      PRIMARY KEY (workspace_id,id)
    );
    CREATE TABLE work.validation_audit (
      workspace_id uuid NOT NULL,
      id uuid NOT NULL DEFAULT gen_random_uuid(),
      record_id uuid NOT NULL,
      initiator_role text NOT NULL,
      event_type text NOT NULL CHECK (event_type='validation.created'),
      occurred_at timestamptz NOT NULL DEFAULT statement_timestamp(),
      PRIMARY KEY (workspace_id,id),
      FOREIGN KEY (workspace_id,record_id) REFERENCES work.validation_records(workspace_id,id)
    );
    CREATE FUNCTION work.append_validation_audit() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,work AS $$
    BEGIN
      INSERT INTO work.validation_audit (workspace_id,record_id,initiator_role,event_type)
      VALUES (NEW.workspace_id,NEW.id,
        CASE WHEN pg_catalog.current_setting('role')='none' THEN session_user::text
             ELSE pg_catalog.current_setting('role') END, 'validation.created');
      RETURN NEW;
    END; $$;
    CREATE TRIGGER work_validation_insert AFTER INSERT ON work.validation_records
      FOR EACH ROW EXECUTE FUNCTION work.append_validation_audit();
    CREATE FUNCTION work.reject_mutation() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
    BEGIN
      RAISE EXCEPTION 'Work validation history is append-only' USING ERRCODE='23514';
    END; $$;
    """)
    owner = op.get_bind().scalar(sa.text("SELECT current_user"))
    quoted_owner = op.get_bind().dialect.identifier_preparer.quote(owner)
    for table in ("validation_records", "validation_audit"):
        op.execute(f"ALTER TABLE work.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE work.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
          CREATE POLICY workspace_access ON work.{table}
          USING (workspace_id IN (SELECT id FROM work.active_workspace))
          WITH CHECK (workspace_id IN (SELECT id FROM work.active_workspace))
        """)
        # Trusted migration/recovery operator remains explicitly privileged.
        op.execute(f"""
          CREATE POLICY operator_access ON work.{table} TO {quoted_owner}
          USING (true) WITH CHECK (true)
        """)
        op.execute(f"""
          CREATE TRIGGER work_no_mutation BEFORE UPDATE OR DELETE ON work.{table}
            FOR EACH ROW EXECUTE FUNCTION work.reject_mutation();
          CREATE TRIGGER work_no_truncate BEFORE TRUNCATE ON work.{table}
            FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation();
        """)
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA work FROM PUBLIC")
    op.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA work FROM PUBLIC")


def downgrade():
    # Only objects owned by this migration; cluster-global NOLOGIN roles remain.
    op.execute("DROP TABLE work.validation_audit")
    op.execute("DROP TABLE work.validation_records")
    op.execute("DROP VIEW work.active_workspace")
    op.execute("DROP FUNCTION work.append_validation_audit()")
    op.execute("DROP FUNCTION work.reject_mutation()")
    op.execute("DROP SCHEMA work")
