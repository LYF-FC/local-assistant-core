"""Synthetic-channel notification delivery state and sealed metadata history.

Revision ID: 0032_notification_delivery
Revises: 0031_financial_capture
"""

from alembic import op

revision = "0032_notification_delivery"
down_revision = "0031_financial_capture"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE public.notification_deliveries (
 id uuid PRIMARY KEY,
 reminder_id uuid NOT NULL REFERENCES public.task_reminders(id),
 owner_id uuid NOT NULL REFERENCES public.users(id),
 scope_key varchar(96) NOT NULL,
 cycle integer NOT NULL,
 channel varchar(16) NOT NULL,
 recipient_ref varchar(64) NOT NULL,
 revision integer NOT NULL,
 state varchar(16) NOT NULL,
 attempts integer NOT NULL,
 next_attempt_at timestamptz,
 attempt_started_at timestamptz,
 resolved_at timestamptz,
 reason varchar(24),
 created_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL,
 CONSTRAINT uq_notification_dedup UNIQUE (reminder_id, cycle),
 CONSTRAINT ck_notification_versions CHECK (revision>=1 AND cycle>=1 AND attempts BETWEEN 0 AND 3),
 CONSTRAINT ck_notification_scope CHECK (scope_key IN ('household_shared','member_a_private','member_b_private')),
 CONSTRAINT ck_notification_channel CHECK (channel IN ('synthetic')),
 CONSTRAINT ck_notification_state CHECK (state IN ('pending','delivered','failed','unknown','cancelled')),
 CONSTRAINT ck_notification_timing CHECK (
  (state='pending' AND next_attempt_at IS NOT NULL AND resolved_at IS NULL)
  OR (state='unknown' AND next_attempt_at IS NOT NULL AND attempt_started_at IS NULL AND resolved_at IS NULL)
  OR (state IN ('delivered','failed','cancelled') AND next_attempt_at IS NULL AND attempt_started_at IS NULL AND resolved_at IS NOT NULL)),
 CONSTRAINT ck_notification_reason CHECK (reason IS NULL OR reason IN ('quiet_hours','daily_limit','transient_error','rejected','attempts_exhausted','ambiguous_outcome','reconciled_absent','owner_unavailable','scope_unavailable','reminder_closed'))
);
CREATE INDEX ix_notification_due ON public.notification_deliveries (state, next_attempt_at, id);
CREATE INDEX ix_notification_owner_scope ON public.notification_deliveries (owner_id, scope_key, id);
CREATE TABLE public.notification_delivery_events (
 id uuid PRIMARY KEY,
 delivery_id uuid NOT NULL REFERENCES public.notification_deliveries(id),
 owner_id uuid NOT NULL REFERENCES public.users(id),
 revision integer NOT NULL,
 operation varchar(16) NOT NULL,
 recorded_at timestamptz NOT NULL,
 snapshot jsonb NOT NULL,
 CONSTRAINT uq_notification_event_revision UNIQUE (delivery_id, revision),
 CONSTRAINT ck_notification_event_revision CHECK (revision>=1),
 CONSTRAINT ck_notification_event_operation CHECK (operation IN ('enqueued','attempted','delivered','retry_scheduled','deferred','failed','unknown','reconciled','cancelled'))
);
CREATE INDEX ix_notification_deliveries_day ON public.notification_delivery_events (owner_id, operation, recorded_at);

CREATE FUNCTION public.butler_seal_notification() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
  IF TG_OP IN ('DELETE','TRUNCATE') THEN
    RAISE EXCEPTION 'Notification deletion is sealed' USING ERRCODE='23514';
  END IF;
  IF TG_OP='INSERT' THEN
    IF NOT EXISTS(SELECT 1 FROM public.task_reminders r
        WHERE r.id=NEW.reminder_id AND r.owner_id=NEW.owner_id AND r.scope_key=NEW.scope_key
          AND r.cycle=NEW.cycle AND r.state='delivered') THEN
      RAISE EXCEPTION 'Notification reminder identity mismatch' USING ERRCODE='23514';
    END IF;
    IF NEW.revision<>1 OR NEW.state<>'pending' OR NEW.attempts<>0 OR NEW.reason IS NOT NULL
      OR NEW.attempt_started_at IS NOT NULL OR NEW.created_at<>NEW.updated_at THEN
      RAISE EXCEPTION 'Notification must start pending' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.reminder_id,NEW.owner_id,NEW.scope_key,NEW.cycle,NEW.channel,NEW.recipient_ref,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id,OLD.reminder_id,OLD.owner_id,OLD.scope_key,OLD.cycle,OLD.channel,OLD.recipient_ref,OLD.created_at)
    OR NEW.revision<>OLD.revision+1 OR NEW.updated_at<OLD.updated_at
    OR NEW.attempts<OLD.attempts OR NEW.attempts>OLD.attempts+1 THEN
    RAISE EXCEPTION 'Notification identity or revision is sealed' USING ERRCODE='23514';
  END IF;
  IF NOT ((OLD.state='pending' AND NEW.state IN ('pending','delivered','failed','unknown','cancelled'))
    OR (OLD.state='unknown' AND NEW.state IN ('pending','delivered','failed','cancelled'))) THEN
    RAISE EXCEPTION 'Invalid notification transition' USING ERRCODE='23514';
  END IF;
  IF NEW.state='delivered' AND (NEW.reason IS NOT NULL OR NEW.resolved_at IS DISTINCT FROM NEW.updated_at)
    OR NEW.state IN ('failed','cancelled') AND (NEW.reason IS NULL OR NEW.resolved_at IS DISTINCT FROM NEW.updated_at) THEN
    RAISE EXCEPTION 'Invalid notification timing' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER butler_notification_guard BEFORE INSERT OR UPDATE OR DELETE ON public.notification_deliveries
  FOR EACH ROW EXECUTE FUNCTION public.butler_seal_notification();
CREATE TRIGGER butler_notification_truncate BEFORE TRUNCATE ON public.notification_deliveries
  FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_notification();

CREATE FUNCTION public.butler_seal_notification_event() RETURNS trigger
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
CREATE TRIGGER butler_notification_event_guard BEFORE INSERT OR UPDATE OR DELETE ON public.notification_delivery_events
  FOR EACH ROW EXECUTE FUNCTION public.butler_seal_notification_event();
CREATE TRIGGER butler_notification_event_truncate BEFORE TRUNCATE ON public.notification_delivery_events
  FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_notification_event();
""")


def downgrade():
    op.execute("""
DROP TABLE public.notification_delivery_events;
DROP FUNCTION public.butler_seal_notification_event();
DROP TABLE public.notification_deliveries;
DROP FUNCTION public.butler_seal_notification();
""")
