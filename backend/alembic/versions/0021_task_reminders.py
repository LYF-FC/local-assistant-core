"""Private deterministic reminder scheduling, metadata journal and preferences.

Revision ID: 0021_task_reminders
Revises: 0020_manual_tasks
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0021_task_reminders"
down_revision = "0020_manual_tasks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_reminders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("manual_tasks.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope_key", sa.String(96), nullable=False),
        *[
            sa.Column(k, sa.Integer(), nullable=False)
            for k in ("revision", "cycle", "policy_revision", "task_revision")
        ],
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", name="uq_task_reminder_task"),
        sa.CheckConstraint(
            "revision>=1 AND cycle>=1 AND policy_revision>=0 AND task_revision>=1",
            name="ck_reminder_versions",
        ),
        sa.CheckConstraint(
            "scope_key IN ('household_shared','member_a_private','member_b_private')",
            name="ck_reminder_scope",
        ),
        sa.CheckConstraint(
            "state IN ('scheduled','delivered','acknowledged','cancelled')",
            name="ck_reminder_state",
        ),
        sa.CheckConstraint(
            "(state='scheduled' AND next_attempt_at IS NOT NULL AND next_attempt_at>=scheduled_at AND delivered_at IS NULL) OR (state IN ('delivered','acknowledged') AND next_attempt_at IS NULL AND delivered_at IS NOT NULL) OR (state='cancelled' AND next_attempt_at IS NULL)",
            name="ck_reminder_delivery",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ('quiet_hours','daily_limit','owner_unavailable','scope_unavailable','task_closed','task_forgotten','cancelled_by_owner')",
            name="ck_reminder_reason",
        ),
    )
    op.create_index("ix_reminder_due", "task_reminders", ["state", "next_attempt_at", "id"])
    op.create_index("ix_reminder_owner_scope", "task_reminders", ["owner_id", "scope_key", "id"])
    op.create_table(
        "task_reminder_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reminder_id", sa.Uuid(), sa.ForeignKey("task_reminders.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("reminder_id", "revision", name="uq_reminder_event_revision"),
        sa.CheckConstraint("revision>=1", name="ck_reminder_event_revision"),
        sa.CheckConstraint(
            "operation IN ('scheduled','rescheduled','delivered','deferred','acknowledged','cancelled')",
            name="ck_reminder_event_operation",
        ),
    )
    op.create_index(
        "ix_reminder_deliveries", "task_reminder_events", ["owner_id", "operation", "recorded_at"]
    )
    op.create_table(
        "reminder_preferences",
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        *[
            sa.Column(k, sa.Integer(), nullable=False)
            for k in ("quiet_start", "quiet_end", "daily_limit")
        ],
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision>=1 AND daily_limit BETWEEN 1 AND 20 AND quiet_start BETWEEN 0 AND 1439 AND quiet_end BETWEEN 0 AND 1439",
            name="ck_reminder_preferences",
        ),
    )
    op.execute("""
      CREATE FUNCTION public.butler_seal_reminder() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      BEGIN
        IF TG_OP IN ('DELETE','TRUNCATE') THEN
          RAISE EXCEPTION 'Reminder deletion is sealed' USING ERRCODE='23514';
        END IF;
        IF TG_TABLE_NAME='reminder_preferences' THEN
          IF TG_OP='INSERT' THEN
            IF NEW.revision<>1 OR NEW.created_at<>NEW.updated_at THEN
              RAISE EXCEPTION 'Invalid preference version' USING ERRCODE='23514';
            END IF;
          ELSIF NEW.owner_id<>OLD.owner_id OR NEW.created_at<>OLD.created_at
            OR NEW.revision<>OLD.revision+1 OR NEW.updated_at<OLD.updated_at THEN
            RAISE EXCEPTION 'Preference identity is sealed' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END IF;
        IF NOT EXISTS(SELECT 1 FROM public.manual_tasks t WHERE t.id=NEW.task_id AND t.owner_id=NEW.owner_id AND t.scope_key=NEW.scope_key) THEN
          RAISE EXCEPTION 'Reminder task identity mismatch' USING ERRCODE='23514';
        END IF;
        IF TG_OP='INSERT' THEN
          IF NEW.revision<>1 OR NEW.cycle<>1 OR NEW.state<>'scheduled' OR NEW.created_at<>NEW.updated_at
            OR NEW.scheduled_at<=NEW.created_at OR NEW.next_attempt_at<>NEW.scheduled_at OR NEW.reason IS NOT NULL THEN
            RAISE EXCEPTION 'Reminder must start scheduled' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END IF;
        IF ROW(NEW.id,NEW.owner_id,NEW.task_id,NEW.scope_key,NEW.created_at)
          IS DISTINCT FROM ROW(OLD.id,OLD.owner_id,OLD.task_id,OLD.scope_key,OLD.created_at)
          OR NEW.revision<>OLD.revision+1 OR NEW.updated_at<OLD.updated_at THEN
          RAISE EXCEPTION 'Reminder identity or revision is sealed' USING ERRCODE='23514';
        END IF;
        IF NEW.state='scheduled' AND NEW.cycle=OLD.cycle+1 THEN
          IF NEW.scheduled_at<=NEW.updated_at OR NEW.next_attempt_at<>NEW.scheduled_at OR NEW.reason IS NOT NULL THEN
            RAISE EXCEPTION 'Invalid reminder reschedule' USING ERRCODE='23514';
          END IF;
        ELSE
          IF NEW.cycle<>OLD.cycle OR NEW.scheduled_at<>OLD.scheduled_at
            OR NOT ((OLD.state='scheduled' AND NEW.state IN ('scheduled','delivered','cancelled'))
              OR (OLD.state='delivered' AND NEW.state IN ('acknowledged','cancelled'))) THEN
            RAISE EXCEPTION 'Invalid reminder transition' USING ERRCODE='23514';
          END IF;
          IF NEW.state='delivered' AND (NEW.delivered_at IS DISTINCT FROM NEW.updated_at OR NEW.updated_at<NEW.scheduled_at OR NEW.reason IS NOT NULL)
            OR NEW.state='scheduled' AND (NEW.next_attempt_at<=NEW.updated_at OR (NEW.reason IS NULL OR NEW.reason NOT IN ('quiet_hours','daily_limit')))
            OR NEW.state='acknowledged' AND (NEW.delivered_at IS DISTINCT FROM OLD.delivered_at OR NEW.reason IS NOT NULL)
            OR NEW.state='cancelled' AND (NEW.delivered_at IS DISTINCT FROM OLD.delivered_at OR NEW.reason IS NULL) THEN
            RAISE EXCEPTION 'Invalid reminder timing' USING ERRCODE='23514';
          END IF;
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER butler_reminder_guard BEFORE INSERT OR UPDATE OR DELETE ON public.task_reminders
        FOR EACH ROW EXECUTE FUNCTION public.butler_seal_reminder();
      CREATE TRIGGER butler_reminder_truncate BEFORE TRUNCATE ON public.task_reminders
        FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_reminder();
      CREATE TRIGGER butler_reminder_preferences_guard BEFORE INSERT OR UPDATE OR DELETE ON public.reminder_preferences
        FOR EACH ROW EXECUTE FUNCTION public.butler_seal_reminder();
      CREATE TRIGGER butler_reminder_preferences_truncate BEFORE TRUNCATE ON public.reminder_preferences
        FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_reminder();
      CREATE FUNCTION public.butler_seal_reminder_event() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      DECLARE parent public.task_reminders;
      BEGIN
        IF TG_OP<>'INSERT' THEN
          RAISE EXCEPTION 'Reminder history is sealed' USING ERRCODE='23514';
        END IF;
        SELECT * INTO parent FROM public.task_reminders WHERE id=NEW.reminder_id;
        IF parent.id IS NULL OR NEW.owner_id<>parent.owner_id OR NEW.revision<>parent.revision
          OR NEW.actor_id IS NOT NULL AND NEW.actor_id<>parent.owner_id OR NEW.recorded_at<>parent.updated_at
          OR NEW.actor_id IS NULL AND NEW.operation NOT IN ('deferred','delivered','cancelled')
          OR NEW.revision=1 AND NEW.operation<>'scheduled'
          OR NEW.revision>1 AND NEW.operation='scheduled'
          OR NEW.snapshot->>'id' IS DISTINCT FROM parent.id::text
          OR NEW.snapshot->>'task_id' IS DISTINCT FROM parent.task_id::text
          OR NEW.snapshot->>'owner_id' IS DISTINCT FROM parent.owner_id::text
          OR NEW.snapshot->>'scope' IS DISTINCT FROM parent.scope_key
          OR NEW.snapshot->>'state' IS DISTINCT FROM parent.state
          OR (NEW.snapshot->>'revision')::int IS DISTINCT FROM parent.revision
          OR (NEW.snapshot->>'cycle')::int IS DISTINCT FROM parent.cycle
          OR (NEW.snapshot->>'task_revision')::int IS DISTINCT FROM parent.task_revision
          OR (NEW.snapshot->>'policy_revision')::int IS DISTINCT FROM parent.policy_revision
          OR (NEW.snapshot->>'scheduled_at')::timestamptz IS DISTINCT FROM parent.scheduled_at
          OR (NEW.snapshot->>'next_attempt_at')::timestamptz IS DISTINCT FROM parent.next_attempt_at
          OR (NEW.snapshot->>'delivered_at')::timestamptz IS DISTINCT FROM parent.delivered_at
          OR (NEW.snapshot->>'created_at')::timestamptz IS DISTINCT FROM parent.created_at
          OR (NEW.snapshot->>'updated_at')::timestamptz IS DISTINCT FROM parent.updated_at
          OR NEW.snapshot->>'reason' IS DISTINCT FROM parent.reason
          OR NEW.snapshot - ARRAY['id','task_id','owner_id','scope','state','revision','cycle','task_revision','policy_revision','scheduled_at','next_attempt_at','delivered_at','created_at','updated_at','reason'] <> '{}'::jsonb
          OR (NEW.operation IN ('scheduled','rescheduled','deferred') AND parent.state<>'scheduled')
          OR (NEW.operation='delivered' AND parent.state<>'delivered')
          OR (NEW.operation='acknowledged' AND parent.state<>'acknowledged')
          OR (NEW.operation='cancelled' AND parent.state<>'cancelled') THEN
          RAISE EXCEPTION 'Reminder history mismatch' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER butler_reminder_event_guard BEFORE INSERT OR UPDATE OR DELETE ON public.task_reminder_events
        FOR EACH ROW EXECUTE FUNCTION public.butler_seal_reminder_event();
      CREATE TRIGGER butler_reminder_event_truncate BEFORE TRUNCATE ON public.task_reminder_events
        FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_reminder_event();
    """)


def downgrade():
    op.drop_table("task_reminder_events")
    op.execute("DROP FUNCTION public.butler_seal_reminder_event()")
    op.drop_table("reminder_preferences")
    op.drop_table("task_reminders")
    op.execute("DROP FUNCTION public.butler_seal_reminder()")
