"""Independent manual task agenda with sealed revisions and scope locking.

Revision ID: 0020_manual_tasks
Revises: 0019_discovery_digest_checks
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0020_manual_tasks"
down_revision = "0019_discovery_digest_checks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manual_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope_key", sa.String(96), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160)),
        sa.Column("details", sa.String(4000)),
        sa.Column("source_reference", sa.String(512)),
        sa.Column("status", sa.String(16)),
        sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_manual_task_revision"),
        sa.CheckConstraint(
            "scope_key IN ('household_shared','member_a_private','member_b_private')",
            name="ck_manual_task_scope",
        ),
        sa.CheckConstraint("state IN ('active','forgotten')", name="ck_manual_task_state"),
        sa.CheckConstraint(
            "assignee_id IS NULL OR assignee_id=owner_id", name="ck_manual_task_assignee"
        ),
        sa.CheckConstraint(
            "(state='active' AND title IS NOT NULL AND length(trim(title)) BETWEEN 1 AND 160 AND details IS NOT NULL AND source_reference IS NOT NULL AND length(trim(source_reference)) BETWEEN 1 AND 512 AND status IN ('open','done','cancelled') AND status IS NOT NULL AND ((status='open' AND completed_at IS NULL AND cancelled_at IS NULL) OR (status='done' AND completed_at IS NOT NULL AND cancelled_at IS NULL) OR (status='cancelled' AND cancelled_at IS NOT NULL AND completed_at IS NULL))) OR (state='forgotten' AND title IS NULL AND details IS NULL AND source_reference IS NULL AND status IS NULL AND due_at IS NULL AND assignee_id IS NULL AND completed_at IS NULL AND cancelled_at IS NULL)",
            name="ck_manual_task_content",
        ),
    )
    op.create_index("ix_manual_task_scope_owner", "manual_tasks", ["scope_key", "owner_id", "id"])
    op.create_table(
        "manual_task_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("manual_tasks.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(none_as_null=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "revision", name="uq_manual_task_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_manual_task_history_revision"),
        sa.CheckConstraint(
            "operation IN ('created','corrected','completed','cancelled','reopened','forgotten')",
            name="ck_manual_task_operation",
        ),
    )
    op.execute("""
      CREATE FUNCTION public.butler_lock_task_scope(p_actor uuid, p_scope text)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        IF p_scope NOT IN ('household_shared','member_a_private','member_b_private') THEN RETURN false; END IF;
        PERFORM g.user_id FROM public.user_scopes g JOIN public.scopes s ON s.id=g.scope_id
          WHERE g.user_id=p_actor AND s.key=p_scope FOR SHARE OF g;
        RETURN FOUND;
      END; $$;
      REVOKE ALL ON FUNCTION public.butler_lock_task_scope(uuid,text) FROM PUBLIC;
      CREATE FUNCTION public.butler_seal_manual_task() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      BEGIN
        IF TG_OP IN ('DELETE','TRUNCATE') THEN
          RAISE EXCEPTION 'Manual task deletion is sealed' USING ERRCODE='23514';
        END IF;
        IF TG_OP='INSERT' THEN
          IF NEW.revision<>1 OR NEW.state<>'active' OR NEW.status<>'open'
            OR NEW.created_at<>NEW.updated_at THEN
            RAISE EXCEPTION 'Manual task must start open' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END IF;
        IF ROW(NEW.id,NEW.owner_id,NEW.scope_key,NEW.created_at)
          IS DISTINCT FROM ROW(OLD.id,OLD.owner_id,OLD.scope_key,OLD.created_at)
          OR OLD.state='forgotten' OR NEW.revision<>OLD.revision+1
          OR NEW.updated_at<OLD.updated_at THEN
          RAISE EXCEPTION 'Manual task identity or revision is sealed' USING ERRCODE='23514';
        END IF;
        IF NEW.state='active' THEN
          IF NEW.status IS DISTINCT FROM OLD.status THEN
            IF NOT ((OLD.status='open' AND NEW.status IN ('done','cancelled'))
              OR (OLD.status IN ('done','cancelled') AND NEW.status='open'))
              OR ROW(NEW.title,NEW.details,NEW.source_reference,NEW.due_at,NEW.assignee_id)
                IS DISTINCT FROM ROW(OLD.title,OLD.details,OLD.source_reference,OLD.due_at,OLD.assignee_id)
              OR (NEW.status='done' AND NEW.completed_at IS DISTINCT FROM NEW.updated_at)
              OR (NEW.status='cancelled' AND NEW.cancelled_at IS DISTINCT FROM NEW.updated_at) THEN
              RAISE EXCEPTION 'Manual task transition is invalid' USING ERRCODE='23514';
            END IF;
          ELSIF ROW(NEW.completed_at,NEW.cancelled_at) IS DISTINCT FROM ROW(OLD.completed_at,OLD.cancelled_at)
            OR ROW(NEW.title,NEW.details,NEW.source_reference,NEW.due_at,NEW.assignee_id)
              IS NOT DISTINCT FROM ROW(OLD.title,OLD.details,OLD.source_reference,OLD.due_at,OLD.assignee_id) THEN
            RAISE EXCEPTION 'Manual task correction is invalid' USING ERRCODE='23514';
          END IF;
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER butler_manual_task_guard BEFORE INSERT OR UPDATE OR DELETE ON public.manual_tasks
        FOR EACH ROW EXECUTE FUNCTION public.butler_seal_manual_task();
      CREATE TRIGGER butler_manual_task_truncate_guard BEFORE TRUNCATE ON public.manual_tasks
        FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_manual_task();
      CREATE FUNCTION public.butler_seal_manual_task_history() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      DECLARE parent public.manual_tasks;
      BEGIN
        IF TG_OP='INSERT' THEN
          SELECT * INTO parent FROM public.manual_tasks WHERE id=NEW.task_id;
          IF parent.id IS NULL OR NEW.actor_id<>parent.owner_id OR NEW.revision<>parent.revision
            OR NEW.created_at<>parent.updated_at
            OR ((parent.state='forgotten') IS DISTINCT FROM (NEW.snapshot IS NULL))
            OR ((NEW.operation='forgotten') IS DISTINCT FROM (parent.state='forgotten'))
            OR (NEW.revision=1 AND NEW.operation<>'created')
            OR (NEW.revision>1 AND NEW.operation='created') THEN
            RAISE EXCEPTION 'Manual task history does not match parent' USING ERRCODE='23514';
          END IF;
          IF parent.state='active' AND (
            NEW.snapshot->>'id' IS DISTINCT FROM parent.id::text
            OR (NEW.snapshot->>'revision')::integer IS DISTINCT FROM parent.revision
            OR NEW.snapshot->>'owner_id' IS DISTINCT FROM parent.owner_id::text
            OR NEW.snapshot->>'scope' IS DISTINCT FROM parent.scope_key
            OR NEW.snapshot->>'state' IS DISTINCT FROM parent.state
            OR NEW.snapshot->>'title' IS DISTINCT FROM parent.title
            OR NEW.snapshot->>'details' IS DISTINCT FROM parent.details
            OR NEW.snapshot->>'source_reference' IS DISTINCT FROM parent.source_reference
            OR NEW.snapshot->>'status' IS DISTINCT FROM parent.status
            OR NEW.snapshot->>'assignee_id' IS DISTINCT FROM parent.assignee_id::text
            OR (NEW.snapshot->>'due_at')::timestamptz IS DISTINCT FROM parent.due_at
            OR (NEW.snapshot->>'completed_at')::timestamptz IS DISTINCT FROM parent.completed_at
            OR (NEW.snapshot->>'cancelled_at')::timestamptz IS DISTINCT FROM parent.cancelled_at
            OR (NEW.snapshot->>'created_at')::timestamptz IS DISTINCT FROM parent.created_at
            OR (NEW.snapshot->>'updated_at')::timestamptz IS DISTINCT FROM parent.updated_at
            OR (NEW.operation='completed' AND parent.status<>'done')
            OR (NEW.operation='cancelled' AND parent.status<>'cancelled')
            OR (NEW.operation='reopened' AND parent.status<>'open')) THEN
            RAISE EXCEPTION 'Manual task snapshot does not match parent' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END IF;
        IF TG_OP='UPDATE' THEN
          IF ROW(NEW.id,NEW.task_id,NEW.revision,NEW.actor_id,NEW.operation,NEW.created_at)
            IS NOT DISTINCT FROM ROW(OLD.id,OLD.task_id,OLD.revision,OLD.actor_id,OLD.operation,OLD.created_at)
            AND NEW.snapshot IS NULL AND EXISTS(SELECT 1 FROM public.manual_tasks WHERE id=OLD.task_id AND state='forgotten') THEN
            RETURN NEW;
          END IF;
        END IF;
        RAISE EXCEPTION 'Manual task history is sealed' USING ERRCODE='23514';
      END; $$;
      CREATE TRIGGER butler_manual_task_history_guard BEFORE INSERT OR UPDATE OR DELETE ON public.manual_task_revisions
        FOR EACH ROW EXECUTE FUNCTION public.butler_seal_manual_task_history();
      CREATE TRIGGER butler_manual_task_history_truncate_guard BEFORE TRUNCATE ON public.manual_task_revisions
        FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_manual_task_history();
    """)


def downgrade():
    op.drop_table("manual_task_revisions")
    op.execute("DROP FUNCTION public.butler_seal_manual_task_history()")
    op.drop_table("manual_tasks")
    op.execute("DROP FUNCTION public.butler_seal_manual_task()")
    op.execute("DROP FUNCTION public.butler_lock_task_scope(uuid,text)")
