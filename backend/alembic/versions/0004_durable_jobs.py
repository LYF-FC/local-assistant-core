"""Durable local jobs and transactional delivery outbox.

Revision ID: 0004_durable_jobs
Revises: 0003_audit_approvals
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_durable_jobs"
down_revision = "0003_audit_approvals"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "durable_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "approval_id", sa.Uuid(), sa.ForeignKey("approvals.id"), nullable=False, unique=True
        ),
        sa.Column("requested_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope_key", sa.String(96), nullable=False),
        sa.Column("action_type", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("requested_by", "idempotency_hash", name="uq_job_request_key"),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','dead_letter')", name="ck_job_status"
        ),
    )
    op.create_table(
        "job_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("durable_jobs.id"), nullable=False, unique=True
        ),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_hash", sa.String(64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('pending','leased','done','dead_letter')", name="ck_outbox_state"
        ),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 3", name="ck_outbox_attempts"),
        sa.CheckConstraint(
            "(state = 'leased' AND lease_hash IS NOT NULL AND lease_until IS NOT NULL) OR (state <> 'leased' AND lease_hash IS NULL AND lease_until IS NULL)",
            name="ck_outbox_lease",
        ),
    )
    op.create_index("ix_outbox_ready", "job_outbox", ["state", "available_at", "lease_until"])
    op.execute("""
    CREATE FUNCTION public.butler_seal_job() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
    BEGIN
      IF ROW(NEW.id, NEW.approval_id, NEW.requested_by, NEW.scope_key, NEW.action_type,
             NEW.payload_hash, NEW.idempotency_hash, NEW.created_at)
         IS DISTINCT FROM ROW(OLD.id, OLD.approval_id, OLD.requested_by, OLD.scope_key,
             OLD.action_type, OLD.payload_hash, OLD.idempotency_hash, OLD.created_at) THEN
        RAISE EXCEPTION 'Job context is sealed' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER butler_job_context_guard BEFORE UPDATE ON public.durable_jobs
      FOR EACH ROW EXECUTE FUNCTION public.butler_seal_job();
    """)


def downgrade():
    op.execute("DROP TRIGGER butler_job_context_guard ON public.durable_jobs")
    op.execute("DROP FUNCTION public.butler_seal_job()")
    op.drop_table("job_outbox")
    op.drop_table("durable_jobs")
