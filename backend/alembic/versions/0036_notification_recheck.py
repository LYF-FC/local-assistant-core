"""Allow an inconclusive reconciliation lookup to keep a notification delivery ``unknown``.

The worker (``notification_worker.reconcile``) answers a lookup that cannot be resolved by writing
``unknown`` -> ``unknown`` (reason ``ambiguous_outcome``, later ``next_attempt_at``). That is the
safe response: never resend, never fail. The guard from 0032 refused the transition, so on
PostgreSQL the write raised and rolled back; the row stayed ``unknown`` but its recheck time and
history were never advanced. The process-restart evidence for Gate 5 surfaced the defect (the
in-process unit tests run without the trigger). The filing guard (0034) already allows the same
transition.

Only the transition rule changes. Every other guard condition, the trigger and the sealed history
are untouched. Downgrade restores the 0032 function body verbatim.

Revision ID: 0036_notification_recheck
Revises: 0035_calendar_provider_sync
"""

from alembic import op

revision = "0036_notification_recheck"
down_revision = "0035_calendar_provider_sync"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE OR REPLACE FUNCTION public.butler_seal_notification() RETURNS trigger
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
    OR (OLD.state='unknown' AND NEW.state IN ('unknown','pending','delivered','failed','cancelled'))) THEN
    RAISE EXCEPTION 'Invalid notification transition' USING ERRCODE='23514';
  END IF;
  IF NEW.state='delivered' AND (NEW.reason IS NOT NULL OR NEW.resolved_at IS DISTINCT FROM NEW.updated_at)
    OR NEW.state IN ('failed','cancelled') AND (NEW.reason IS NULL OR NEW.resolved_at IS DISTINCT FROM NEW.updated_at) THEN
    RAISE EXCEPTION 'Invalid notification timing' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
"""

DOWNGRADE = """
CREATE OR REPLACE FUNCTION public.butler_seal_notification() RETURNS trigger
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
"""


def upgrade():
    op.execute(UPGRADE)


def downgrade():
    op.execute(DOWNGRADE)
