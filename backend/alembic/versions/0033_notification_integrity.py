"""Notification integrity corrections: full history snapshot validation and a paused reason.

Revision ID: 0033_notification_integrity
Revises: 0032_notification_delivery
"""

from alembic import op

revision = "0033_notification_integrity"
down_revision = "0032_notification_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
ALTER TABLE public.notification_deliveries DROP CONSTRAINT ck_notification_reason;
ALTER TABLE public.notification_deliveries ADD CONSTRAINT ck_notification_reason
 CHECK (reason IS NULL OR reason IN ('quiet_hours','daily_limit','paused','transient_error','rejected','attempts_exhausted','ambiguous_outcome','reconciled_absent','owner_unavailable','scope_unavailable','reminder_closed'));
CREATE OR REPLACE FUNCTION public.butler_seal_notification_event() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE parent public.notification_deliveries;
BEGIN
  IF TG_OP<>'INSERT' THEN
    RAISE EXCEPTION 'Notification history is sealed' USING ERRCODE='23514';
  END IF;
  SELECT * INTO parent FROM public.notification_deliveries WHERE id=NEW.delivery_id;
  IF parent.id IS NULL OR NEW.owner_id<>parent.owner_id OR NEW.revision<>parent.revision
    OR NEW.recorded_at<>parent.updated_at
    OR NEW.revision=1 AND NEW.operation<>'enqueued'
    OR NEW.revision>1 AND NEW.operation='enqueued'
    OR NOT (NEW.snapshot ?& ARRAY['id','reminder_id','owner_id','scope','channel','state','revision','cycle','attempts','next_attempt_at','resolved_at','reason','created_at','updated_at'])
    OR NEW.snapshot - ARRAY['id','reminder_id','owner_id','scope','channel','state','revision','cycle','attempts','next_attempt_at','resolved_at','reason','created_at','updated_at'] <> '{}'::jsonb
    OR jsonb_typeof(NEW.snapshot->'id') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'reminder_id') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'owner_id') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'scope') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'channel') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'state') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'revision') IS DISTINCT FROM 'number'
    OR jsonb_typeof(NEW.snapshot->'cycle') IS DISTINCT FROM 'number'
    OR jsonb_typeof(NEW.snapshot->'attempts') IS DISTINCT FROM 'number'
    OR jsonb_typeof(NEW.snapshot->'reason') NOT IN ('string','null')
    OR jsonb_typeof(NEW.snapshot->'next_attempt_at') NOT IN ('string','null')
    OR jsonb_typeof(NEW.snapshot->'resolved_at') NOT IN ('string','null')
    OR jsonb_typeof(NEW.snapshot->'created_at') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'updated_at') IS DISTINCT FROM 'string'
    OR NEW.snapshot->>'id' IS DISTINCT FROM parent.id::text
    OR NEW.snapshot->>'reminder_id' IS DISTINCT FROM parent.reminder_id::text
    OR NEW.snapshot->>'owner_id' IS DISTINCT FROM parent.owner_id::text
    OR NEW.snapshot->>'scope' IS DISTINCT FROM parent.scope_key
    OR NEW.snapshot->>'channel' IS DISTINCT FROM parent.channel
    OR NEW.snapshot->>'state' IS DISTINCT FROM parent.state
    OR (NEW.snapshot->>'revision')::int IS DISTINCT FROM parent.revision
    OR (NEW.snapshot->>'cycle')::int IS DISTINCT FROM parent.cycle
    OR (NEW.snapshot->>'attempts')::int IS DISTINCT FROM parent.attempts
    OR NEW.snapshot->>'reason' IS DISTINCT FROM parent.reason
    OR (NEW.snapshot->>'next_attempt_at')::timestamptz IS DISTINCT FROM parent.next_attempt_at
    OR (NEW.snapshot->>'resolved_at')::timestamptz IS DISTINCT FROM parent.resolved_at
    OR (NEW.snapshot->>'created_at')::timestamptz IS DISTINCT FROM parent.created_at
    OR (NEW.snapshot->>'updated_at')::timestamptz IS DISTINCT FROM parent.updated_at THEN
    RAISE EXCEPTION 'Notification history mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
""")


def downgrade():
    # A paused reason cannot exist under the older constraint. Clear it on current rows with the
    # seal temporarily off; sealed history snapshots keep recording what happened.
    op.execute("""
ALTER TABLE public.notification_deliveries DISABLE TRIGGER butler_notification_guard;
UPDATE public.notification_deliveries SET reason=NULL WHERE reason='paused';
ALTER TABLE public.notification_deliveries ENABLE TRIGGER butler_notification_guard;
ALTER TABLE public.notification_deliveries DROP CONSTRAINT ck_notification_reason;
ALTER TABLE public.notification_deliveries ADD CONSTRAINT ck_notification_reason
 CHECK (reason IS NULL OR reason IN ('quiet_hours','daily_limit','transient_error','rejected','attempts_exhausted','ambiguous_outcome','reconciled_absent','owner_unavailable','scope_unavailable','reminder_closed'));
CREATE OR REPLACE FUNCTION public.butler_seal_notification_event() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE parent public.notification_deliveries;
BEGIN
  IF TG_OP<>'INSERT' THEN
    RAISE EXCEPTION 'Notification history is sealed' USING ERRCODE='23514';
  END IF;
  SELECT * INTO parent FROM public.notification_deliveries WHERE id=NEW.delivery_id;
  IF parent.id IS NULL OR NEW.owner_id<>parent.owner_id OR NEW.revision<>parent.revision
    OR NEW.recorded_at<>parent.updated_at
    OR NEW.revision=1 AND NEW.operation<>'enqueued'
    OR NEW.revision>1 AND NEW.operation='enqueued'
    OR NEW.snapshot->>'id' IS DISTINCT FROM parent.id::text
    OR NEW.snapshot->>'reminder_id' IS DISTINCT FROM parent.reminder_id::text
    OR NEW.snapshot->>'owner_id' IS DISTINCT FROM parent.owner_id::text
    OR NEW.snapshot->>'scope' IS DISTINCT FROM parent.scope_key
    OR NEW.snapshot->>'state' IS DISTINCT FROM parent.state
    OR (NEW.snapshot->>'revision')::int IS DISTINCT FROM parent.revision
    OR (NEW.snapshot->>'cycle')::int IS DISTINCT FROM parent.cycle
    OR (NEW.snapshot->>'attempts')::int IS DISTINCT FROM parent.attempts
    OR NEW.snapshot->>'reason' IS DISTINCT FROM parent.reason
    OR NEW.snapshot - ARRAY['id','reminder_id','owner_id','scope','channel','state','revision','cycle','attempts','next_attempt_at','resolved_at','reason','created_at','updated_at'] <> '{}'::jsonb THEN
    RAISE EXCEPTION 'Notification history mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
""")
