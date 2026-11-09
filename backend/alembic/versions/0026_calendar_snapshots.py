"""Bounded calendar snapshots and sealed history."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0026_calendar_snapshots"
down_revision = "0025_pdf_ocr"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "calendar_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope_key", sa.String(96), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(none_as_null=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision BETWEEN 1 AND 101", name="ck_calendar_revision"),
        sa.CheckConstraint(
            "scope_key IN ('household_shared','member_a_private','member_b_private')",
            name="ck_calendar_scope",
        ),
        sa.CheckConstraint(
            "(state='active' AND data IS NOT NULL) OR (state='forgotten' AND data IS NULL)",
            name="ck_calendar_content",
        ),
    )
    op.create_index("ix_calendar_scope_owner", "calendar_sources", ["scope_key", "owner_id", "id"])
    op.create_table(
        "calendar_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("calendar_sources.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(none_as_null=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "revision", name="uq_calendar_revision"),
        sa.CheckConstraint("revision BETWEEN 1 AND 101", name="ck_calendar_history_revision"),
    )
    op.execute("""
    CREATE FUNCTION public.butler_seal_calendar() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog AS $$
    BEGIN
      IF TG_OP IN ('DELETE','TRUNCATE') THEN
        RAISE EXCEPTION 'Calendar deletion is sealed' USING ERRCODE='23514';
      END IF;
      IF NEW.state='active' AND (jsonb_typeof(NEW.data) IS DISTINCT FROM 'object'
        OR octet_length(NEW.data::text)>70000
        OR NEW.data->>'status' IS NULL
        OR NEW.data->>'status' NOT IN ('setup_required','ready','offline','failed')
        OR length(trim(NEW.data->>'label')) NOT BETWEEN 1 AND 160
        OR NEW.data->>'label' IS NULL) THEN
        RAISE EXCEPTION 'Invalid calendar content' USING ERRCODE='23514';
      END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.revision<>1 OR NEW.state<>'active' OR NEW.created_at<>NEW.updated_at
          OR NEW.data->>'status'<>'setup_required' OR NEW.data->>'window' IS NOT NULL THEN
          RAISE EXCEPTION 'Calendar must start unconfigured' USING ERRCODE='23514';
        END IF;
      ELSIF ROW(NEW.id,NEW.owner_id,NEW.scope_key,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.id,OLD.owner_id,OLD.scope_key,OLD.created_at)
        OR OLD.state='forgotten' OR NEW.revision<>OLD.revision+1
        OR NEW.updated_at<OLD.updated_at OR NEW.data IS NOT DISTINCT FROM OLD.data
        OR (NEW.state='active' AND (NEW.revision>100 OR NEW.data->>'label' IS DISTINCT FROM OLD.data->>'label')) THEN
        RAISE EXCEPTION 'Calendar identity or revision is sealed' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END; $$;
    CREATE TRIGGER butler_calendar_guard BEFORE INSERT OR UPDATE OR DELETE ON public.calendar_sources
      FOR EACH ROW EXECUTE FUNCTION public.butler_seal_calendar();
    CREATE TRIGGER butler_calendar_truncate BEFORE TRUNCATE ON public.calendar_sources
      FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_calendar();
    CREATE FUNCTION public.butler_seal_calendar_history() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog AS $$
    DECLARE parent public.calendar_sources;
    BEGIN
      IF TG_OP='INSERT' THEN
        SELECT * INTO parent FROM public.calendar_sources WHERE id=NEW.source_id;
        IF parent.id IS NULL OR NEW.actor_id<>parent.owner_id OR NEW.revision<>parent.revision
          OR NEW.created_at<>parent.updated_at OR NEW.snapshot IS DISTINCT FROM parent.data THEN
          RAISE EXCEPTION 'Calendar history differs from parent' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      ELSIF TG_OP='UPDATE' THEN
        IF ROW(NEW.id,NEW.source_id,NEW.revision,NEW.actor_id,NEW.created_at)
          IS NOT DISTINCT FROM ROW(OLD.id,OLD.source_id,OLD.revision,OLD.actor_id,OLD.created_at)
          AND NEW.snapshot IS NULL AND EXISTS(SELECT 1 FROM public.calendar_sources WHERE id=OLD.source_id AND state='forgotten') THEN
          RETURN NEW;
        END IF;
      END IF;
      RAISE EXCEPTION 'Calendar history is sealed' USING ERRCODE='23514';
    END; $$;
    CREATE TRIGGER butler_calendar_history_guard BEFORE INSERT OR UPDATE OR DELETE ON public.calendar_revisions
      FOR EACH ROW EXECUTE FUNCTION public.butler_seal_calendar_history();
    CREATE TRIGGER butler_calendar_history_truncate BEFORE TRUNCATE ON public.calendar_revisions
      FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_calendar_history();
    """)


def downgrade():
    op.drop_table("calendar_revisions")
    op.execute("DROP FUNCTION public.butler_seal_calendar_history()")
    op.drop_table("calendar_sources")
    op.execute("DROP FUNCTION public.butler_seal_calendar()")
