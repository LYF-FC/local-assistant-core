"""Private synthetic work read-attempt audit, not a delivery receipt.

Revision ID: 0009_work_read_audit
Revises: 0008_work_authority
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_work_read_audit"
down_revision = "0008_work_authority"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE TABLE work.read_attempts (
        workspace_id uuid NOT NULL REFERENCES public.work_workspaces(id),
        id uuid NOT NULL DEFAULT gen_random_uuid(),
        requested_by uuid NOT NULL,
        session_id uuid NOT NULL,
        event_type text NOT NULL CHECK (event_type IN ('validation.read_prepared','validation.read_denied')),
        record_count smallint NOT NULL CHECK (record_count BETWEEN 0 AND 25),
        record_ids jsonb NOT NULL CHECK (jsonb_typeof(record_ids)='array' AND jsonb_array_length(record_ids)=record_count),
        reason_code text NULL,
        occurred_at timestamptz NOT NULL DEFAULT statement_timestamp(),
        PRIMARY KEY (workspace_id,id),
        CHECK ((event_type='validation.read_prepared' AND reason_code IS NULL) OR
               (event_type='validation.read_denied' AND reason_code IS NOT NULL AND reason_code='authority_expired' AND record_count=0))
      );
      CREATE INDEX ix_work_read_attempts ON work.read_attempts (workspace_id,occurred_at,id);
      ALTER TABLE work.read_attempts ENABLE ROW LEVEL SECURITY;
      ALTER TABLE work.read_attempts FORCE ROW LEVEL SECURITY;
      CREATE POLICY workspace_access ON work.read_attempts
        USING (workspace_id IN (SELECT id FROM work.active_workspace))
        WITH CHECK (workspace_id IN (SELECT id FROM work.active_workspace));
      CREATE TRIGGER work_no_mutation BEFORE UPDATE OR DELETE ON work.read_attempts
        FOR EACH ROW EXECUTE FUNCTION work.reject_mutation();
      CREATE TRIGGER work_no_truncate BEFORE TRUNCATE ON work.read_attempts
        FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation();
      REVOKE ALL ON work.read_attempts FROM PUBLIC;
    """)
    owner = op.get_bind().scalar(sa.text("SELECT current_user"))
    quoted = op.get_bind().dialect.identifier_preparer.quote(owner)
    op.execute(
        f"CREATE POLICY operator_access ON work.read_attempts TO {quoted} USING (true) WITH CHECK (true)"
    )


def downgrade():
    op.execute("DROP TABLE work.read_attempts")
