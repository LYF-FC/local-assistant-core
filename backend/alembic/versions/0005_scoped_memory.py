"""Explicit scoped memory and scrub-capable historical snapshots.

Revision ID: 0005_scoped_memory
Revises: 0004_durable_jobs
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_scoped_memory"
down_revision = "0004_durable_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memory_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope_key", sa.String(96), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=True),
        sa.Column("content", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=True),
        sa.Column("source_reference", sa.String(512), nullable=True),
        sa.Column("assessment", sa.String(16), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_memory_revision"),
        sa.CheckConstraint(
            "kind IN ('profile','preference','experience','procedure','context')",
            name="ck_memory_kind",
        ),
        sa.CheckConstraint("state IN ('active','forgotten')", name="ck_memory_state"),
        sa.CheckConstraint(
            "(state='active' AND title IS NOT NULL AND content IS NOT NULL AND source_type IS NOT NULL AND source_reference IS NOT NULL AND assessment IS NOT NULL AND assessment IN ('confirmed','tentative')) OR (state='forgotten' AND title IS NULL AND content IS NULL AND source_type IS NULL AND source_reference IS NULL AND assessment IS NULL AND expires_at IS NULL)",
            name="ck_memory_content",
        ),
        sa.CheckConstraint(
            "state='forgotten' OR kind<>'context' OR expires_at IS NOT NULL",
            name="ck_memory_context_expiry",
        ),
    )
    op.create_index("ix_memory_scope_owner_id", "memory_records", ["scope_key", "owner_id", "id"])
    op.create_table(
        "memory_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("memory_id", sa.Uuid(), sa.ForeignKey("memory_records.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("memory_id", "revision", name="uq_memory_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_memory_history_revision"),
    )
    op.create_index("ix_memory_history", "memory_revisions", ["memory_id", "revision"])
    op.execute("""
    CREATE FUNCTION public.butler_seal_memory() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
    BEGIN
      IF ROW(NEW.id,NEW.owner_id,NEW.scope_key,NEW.kind,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.id,OLD.owner_id,OLD.scope_key,OLD.kind,OLD.created_at)
        OR OLD.state='forgotten' OR NEW.revision<>OLD.revision+1 THEN
        RAISE EXCEPTION 'Memory context or revision is sealed' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER butler_memory_guard BEFORE UPDATE ON public.memory_records
      FOR EACH ROW EXECUTE FUNCTION public.butler_seal_memory();
    CREATE FUNCTION public.butler_seal_memory_history() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
    BEGIN
      IF TG_OP<>'UPDATE' THEN
        RAISE EXCEPTION 'Memory history is sealed' USING ERRCODE='23514';
      END IF;
      IF ROW(NEW.id,NEW.memory_id,NEW.revision,NEW.actor_id,NEW.created_at)
        IS NOT DISTINCT FROM ROW(OLD.id,OLD.memory_id,OLD.revision,OLD.actor_id,OLD.created_at)
        AND NEW.snapshot IS NULL
        AND EXISTS(SELECT 1 FROM public.memory_records WHERE id=OLD.memory_id AND state='forgotten') THEN
        RETURN NEW;
      END IF;
      RAISE EXCEPTION 'Memory history is sealed' USING ERRCODE='23514';
    END; $$;
    CREATE TRIGGER butler_memory_history_guard BEFORE UPDATE OR DELETE ON public.memory_revisions
      FOR EACH ROW EXECUTE FUNCTION public.butler_seal_memory_history();
    CREATE TRIGGER butler_memory_history_truncate_guard BEFORE TRUNCATE ON public.memory_revisions
      FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_memory_history();
    """)


def downgrade():
    op.execute("DROP TRIGGER butler_memory_history_truncate_guard ON public.memory_revisions")
    op.execute("DROP TRIGGER butler_memory_history_guard ON public.memory_revisions")
    op.execute("DROP FUNCTION public.butler_seal_memory_history()")
    op.execute("DROP TRIGGER butler_memory_guard ON public.memory_records")
    op.execute("DROP FUNCTION public.butler_seal_memory()")
    op.drop_table("memory_revisions")
    op.drop_table("memory_records")
