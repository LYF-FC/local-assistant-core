"""Single-claim, reconcile-before-retry synthetic-destination invoice filing state and sealed history.

Revision ID: 0034_invoice_filing_execution
Revises: 0033_notification_integrity
"""

from alembic import op

revision = "0034_invoice_filing_execution"
down_revision = "0033_notification_integrity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE public.filing_executions (
 id uuid PRIMARY KEY,
 document_id uuid NOT NULL REFERENCES public.document_records(id),
 owner_id uuid NOT NULL REFERENCES public.users(id),
 scope_key varchar(96) NOT NULL,
 plan_revision integer NOT NULL,
 source_revision integer NOT NULL,
 destination_key varchar(64),
 destination varchar(16) NOT NULL,
 revision integer NOT NULL,
 state varchar(16) NOT NULL,
 attempts integer NOT NULL,
 next_attempt_at timestamptz,
 attempt_started_at timestamptz,
 authorization_consumed_at timestamptz,
 scrubbed_at timestamptz,
 resolved_at timestamptz,
 reason varchar(24),
 created_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL,
 CONSTRAINT uq_filing_dedup UNIQUE (document_id, plan_revision),
 CONSTRAINT ck_filing_versions CHECK (revision>=1 AND plan_revision>=1 AND source_revision>=1 AND attempts BETWEEN 0 AND 3),
 CONSTRAINT ck_filing_scope CHECK (scope_key IN ('household_shared','member_a_private','member_b_private')),
 CONSTRAINT ck_filing_destination CHECK (destination IN ('synthetic')),
 CONSTRAINT ck_filing_key CHECK (destination_key IS NULL OR length(destination_key)=64),
 CONSTRAINT ck_filing_state CHECK (state IN ('pending','filed','failed','unknown','cancelled')),
 CONSTRAINT ck_filing_timing CHECK (
  (state='pending' AND next_attempt_at IS NOT NULL AND resolved_at IS NULL)
  OR (state='unknown' AND next_attempt_at IS NOT NULL AND attempt_started_at IS NULL AND resolved_at IS NULL)
  OR (state IN ('filed','failed','cancelled') AND next_attempt_at IS NULL AND attempt_started_at IS NULL AND resolved_at IS NOT NULL)),
 CONSTRAINT ck_filing_consumed CHECK ((attempts=0 AND authorization_consumed_at IS NULL) OR (attempts>0 AND authorization_consumed_at IS NOT NULL)),
 CONSTRAINT ck_filing_scrubbed CHECK (scrubbed_at IS NULL OR (destination_key IS NULL AND state IN ('filed','failed','cancelled'))),
 CONSTRAINT ck_filing_reason CHECK (reason IS NULL OR reason IN ('transient_error','collision','attempts_exhausted','ambiguous_outcome','reconciled_absent','cancelled_by_owner','plan_changed','source_changed','owner_unavailable','scope_unavailable'))
);
CREATE INDEX ix_filing_due ON public.filing_executions (state, next_attempt_at, id);
CREATE INDEX ix_filing_owner_scope ON public.filing_executions (owner_id, scope_key, id);
CREATE UNIQUE INDEX uq_filing_destination_active ON public.filing_executions (scope_key, destination_key)
 WHERE state IN ('pending','unknown','filed');
CREATE TABLE public.filing_execution_events (
 id uuid PRIMARY KEY,
 execution_id uuid NOT NULL REFERENCES public.filing_executions(id),
 owner_id uuid NOT NULL REFERENCES public.users(id),
 revision integer NOT NULL,
 operation varchar(16) NOT NULL,
 actor_id uuid REFERENCES public.users(id),
 recorded_at timestamptz NOT NULL,
 snapshot jsonb,
 CONSTRAINT uq_filing_event_revision UNIQUE (execution_id, revision),
 CONSTRAINT ck_filing_event_revision CHECK (revision>=1),
 CONSTRAINT ck_filing_event_operation CHECK (operation IN ('requested','attempted','filed','retry_scheduled','failed','unknown','reconciled','cancelled','scrubbed'))
);

CREATE FUNCTION public.butler_seal_filing() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
  IF TG_OP IN ('DELETE','TRUNCATE') THEN
    RAISE EXCEPTION 'Filing deletion is sealed' USING ERRCODE='23514';
  END IF;
  IF TG_OP='INSERT' THEN
    -- Only an approved, current, owner-reviewed plan for the same path, revision and source may be filed.
    IF NOT EXISTS(SELECT 1 FROM public.invoice_reviews r
        JOIN public.document_records d ON d.id=r.document_id
        WHERE r.document_id=NEW.document_id AND r.owner_id=NEW.owner_id AND r.scope_key=NEW.scope_key
          AND d.owner_id=NEW.owner_id AND d.scope_key=NEW.scope_key AND d.state='active'
          AND d.revision=NEW.source_revision
          AND r.state='reviewed' AND r.revision=NEW.plan_revision AND r.source_revision=NEW.source_revision
          AND r.data->'filing_plan'->>'state'='approved'
          AND encode(sha256(convert_to(NEW.scope_key||':'||lower(rtrim(regexp_replace(normalize(r.data->'filing_plan'->>'relative_path',NFC),'/+','/','g'),'/')),'UTF8')),'hex')=NEW.destination_key
          AND (r.data->'filing_plan'->>'approved_revision')::int=NEW.plan_revision) THEN
      RAISE EXCEPTION 'Filing requires a current approved plan' USING ERRCODE='23514';
    END IF;
    IF NEW.revision<>1 OR NEW.state<>'pending' OR NEW.attempts<>0 OR NEW.reason IS NOT NULL
      OR NEW.attempt_started_at IS NOT NULL OR NEW.created_at<>NEW.updated_at
      OR NEW.authorization_consumed_at IS NOT NULL OR NEW.scrubbed_at IS NOT NULL THEN
      RAISE EXCEPTION 'Filing must start pending' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.document_id,NEW.owner_id,NEW.scope_key,NEW.plan_revision,NEW.source_revision,NEW.destination,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id,OLD.document_id,OLD.owner_id,OLD.scope_key,OLD.plan_revision,OLD.source_revision,OLD.destination,OLD.created_at)
    OR NEW.revision<>OLD.revision+1 OR NEW.updated_at<OLD.updated_at
    OR NEW.attempts<OLD.attempts OR NEW.attempts>OLD.attempts+1 THEN
    RAISE EXCEPTION 'Filing identity or revision is sealed' USING ERRCODE='23514';
  END IF;
  IF NEW.destination_key IS DISTINCT FROM OLD.destination_key AND NOT (
      NEW.destination_key IS NULL AND OLD.destination_key IS NOT NULL AND (
        EXISTS(SELECT 1 FROM public.document_records d WHERE d.id=NEW.document_id AND d.state='forgotten')
        OR EXISTS(SELECT 1 FROM public.invoice_reviews r WHERE r.document_id=NEW.document_id AND r.state='forgotten'))) THEN
    RAISE EXCEPTION 'Filing destination is sealed' USING ERRCODE='23514';
  END IF;
  -- The authorization is consumed exactly once, by the same update that records the first attempt.
  IF OLD.attempts=0 AND NEW.attempts=1 THEN
    IF OLD.authorization_consumed_at IS NOT NULL OR NEW.authorization_consumed_at IS DISTINCT FROM NEW.updated_at THEN
      RAISE EXCEPTION 'Filing authorization is consumed by the first claim' USING ERRCODE='23514';
    END IF;
  ELSIF NEW.authorization_consumed_at IS DISTINCT FROM OLD.authorization_consumed_at THEN
    RAISE EXCEPTION 'Filing authorization is single-use' USING ERRCODE='23514';
  END IF;
  IF NEW.scrubbed_at IS DISTINCT FROM OLD.scrubbed_at AND NOT (
      OLD.scrubbed_at IS NULL AND NEW.scrubbed_at=NEW.updated_at AND OLD.state IN ('filed','failed','cancelled') AND (
        EXISTS(SELECT 1 FROM public.document_records d WHERE d.id=NEW.document_id AND d.state='forgotten')
        OR EXISTS(SELECT 1 FROM public.invoice_reviews r WHERE r.document_id=NEW.document_id AND r.state='forgotten'))) THEN
    RAISE EXCEPTION 'Filing scrub marker is sealed' USING ERRCODE='23514';
  END IF;
  IF OLD.state IN ('filed','failed','cancelled') THEN
    -- Terminal rows may only lose their opaque destination key or gain the scrub marker, once.
    IF NEW.state<>OLD.state OR NEW.destination_key IS NOT NULL
      OR NEW.attempts<>OLD.attempts OR NEW.reason IS DISTINCT FROM OLD.reason
      OR NEW.resolved_at IS DISTINCT FROM OLD.resolved_at
      OR NEW.next_attempt_at IS NOT NULL OR NEW.attempt_started_at IS NOT NULL
      OR (NEW.destination_key IS NOT DISTINCT FROM OLD.destination_key AND NEW.scrubbed_at IS NOT DISTINCT FROM OLD.scrubbed_at) THEN
      RAISE EXCEPTION 'Invalid filing transition' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF NOT ((OLD.state='pending' AND NEW.state IN ('pending','filed','failed','unknown','cancelled'))
    OR (OLD.state='unknown' AND NEW.state IN ('unknown','pending','filed','failed','cancelled'))) THEN
    RAISE EXCEPTION 'Invalid filing transition' USING ERRCODE='23514';
  END IF;
  -- An outcome can only follow a claim: never filed, failed or unknown for an unclaimed attempt.
  IF NEW.state IN ('filed','failed','unknown') AND (
      NEW.attempts=0 OR (OLD.state='pending' AND OLD.attempt_started_at IS NULL)) THEN
    RAISE EXCEPTION 'Invalid filing transition' USING ERRCODE='23514';
  END IF;
  IF NEW.state='filed' AND (NEW.reason IS NOT NULL OR NEW.resolved_at IS DISTINCT FROM NEW.updated_at)
    OR NEW.state IN ('failed','cancelled') AND (NEW.reason IS NULL OR NEW.resolved_at IS DISTINCT FROM NEW.updated_at) THEN
    RAISE EXCEPTION 'Invalid filing timing' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER butler_filing_guard BEFORE INSERT OR UPDATE OR DELETE ON public.filing_executions
  FOR EACH ROW EXECUTE FUNCTION public.butler_seal_filing();
CREATE TRIGGER butler_filing_truncate BEFORE TRUNCATE ON public.filing_executions
  FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_filing();

CREATE FUNCTION public.butler_seal_filing_event() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE parent public.filing_executions;
BEGIN
  IF TG_OP='UPDATE' THEN
    -- The only permitted change: null the snapshot of an execution whose source was forgotten.
    IF OLD.snapshot IS NOT NULL AND NEW.snapshot IS NULL
      AND ROW(NEW.id,NEW.execution_id,NEW.owner_id,NEW.revision,NEW.operation,NEW.actor_id,NEW.recorded_at)
        IS NOT DISTINCT FROM ROW(OLD.id,OLD.execution_id,OLD.owner_id,OLD.revision,OLD.operation,OLD.actor_id,OLD.recorded_at)
      AND EXISTS(SELECT 1 FROM public.filing_executions f WHERE f.id=NEW.execution_id AND (
        EXISTS(SELECT 1 FROM public.document_records d WHERE d.id=f.document_id AND d.state='forgotten')
        OR EXISTS(SELECT 1 FROM public.invoice_reviews r WHERE r.document_id=f.document_id AND r.state='forgotten'))) THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'Filing history is sealed' USING ERRCODE='23514';
  END IF;
  IF TG_OP<>'INSERT' THEN
    RAISE EXCEPTION 'Filing history is sealed' USING ERRCODE='23514';
  END IF;
  SELECT * INTO parent FROM public.filing_executions WHERE id=NEW.execution_id;
  IF parent.id IS NOT NULL AND NEW.operation='scrubbed' THEN
    IF NEW.snapshot IS NOT NULL OR parent.scrubbed_at IS DISTINCT FROM parent.updated_at THEN
      RAISE EXCEPTION 'Filing history mismatch' USING ERRCODE='23514';
    END IF;
    IF NEW.owner_id<>parent.owner_id OR NEW.revision<>parent.revision OR NEW.recorded_at<>parent.updated_at OR NEW.actor_id IS NOT NULL THEN
      RAISE EXCEPTION 'Filing history mismatch' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF parent.id IS NULL OR NEW.snapshot IS NULL OR parent.scrubbed_at IS NOT NULL OR NEW.owner_id<>parent.owner_id OR NEW.revision<>parent.revision
    OR NEW.recorded_at<>parent.updated_at
    OR NEW.actor_id IS NOT NULL AND (NEW.actor_id<>parent.owner_id OR NEW.operation NOT IN ('requested','cancelled'))
    OR NEW.operation='scrubbed' AND NEW.actor_id IS NOT NULL
    OR NEW.actor_id IS NULL AND NEW.operation='requested'
    OR NEW.revision=1 AND NEW.operation<>'requested'
    OR NEW.revision>1 AND NEW.operation='requested'
    OR NOT (NEW.snapshot ?& ARRAY['id','document_id','owner_id','scope','destination','state','revision','plan_revision','source_revision','attempts','next_attempt_at','resolved_at','reason','created_at','updated_at'])
    OR NEW.snapshot - ARRAY['id','document_id','owner_id','scope','destination','state','revision','plan_revision','source_revision','attempts','next_attempt_at','resolved_at','reason','created_at','updated_at'] <> '{}'::jsonb
    OR jsonb_typeof(NEW.snapshot->'id') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'document_id') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'owner_id') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'scope') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'destination') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'state') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'created_at') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'updated_at') IS DISTINCT FROM 'string'
    OR jsonb_typeof(NEW.snapshot->'revision') IS DISTINCT FROM 'number'
    OR jsonb_typeof(NEW.snapshot->'plan_revision') IS DISTINCT FROM 'number'
    OR jsonb_typeof(NEW.snapshot->'source_revision') IS DISTINCT FROM 'number'
    OR jsonb_typeof(NEW.snapshot->'attempts') IS DISTINCT FROM 'number'
    OR jsonb_typeof(NEW.snapshot->'reason') NOT IN ('string','null')
    OR jsonb_typeof(NEW.snapshot->'next_attempt_at') NOT IN ('string','null')
    OR jsonb_typeof(NEW.snapshot->'resolved_at') NOT IN ('string','null')
    OR NEW.snapshot->>'id' IS DISTINCT FROM parent.id::text
    OR NEW.snapshot->>'document_id' IS DISTINCT FROM parent.document_id::text
    OR NEW.snapshot->>'owner_id' IS DISTINCT FROM parent.owner_id::text
    OR NEW.snapshot->>'scope' IS DISTINCT FROM parent.scope_key
    OR NEW.snapshot->>'destination' IS DISTINCT FROM parent.destination
    OR NEW.snapshot->>'state' IS DISTINCT FROM parent.state
    OR NEW.snapshot->>'reason' IS DISTINCT FROM parent.reason
    OR (NEW.snapshot->>'revision')::int IS DISTINCT FROM parent.revision
    OR (NEW.snapshot->>'plan_revision')::int IS DISTINCT FROM parent.plan_revision
    OR (NEW.snapshot->>'source_revision')::int IS DISTINCT FROM parent.source_revision
    OR (NEW.snapshot->>'attempts')::int IS DISTINCT FROM parent.attempts
    OR (NEW.snapshot->>'next_attempt_at')::timestamptz IS DISTINCT FROM parent.next_attempt_at
    OR (NEW.snapshot->>'resolved_at')::timestamptz IS DISTINCT FROM parent.resolved_at
    OR (NEW.snapshot->>'created_at')::timestamptz IS DISTINCT FROM parent.created_at
    OR (NEW.snapshot->>'updated_at')::timestamptz IS DISTINCT FROM parent.updated_at THEN
    RAISE EXCEPTION 'Filing history mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER butler_filing_event_guard BEFORE INSERT OR UPDATE OR DELETE ON public.filing_execution_events
  FOR EACH ROW EXECUTE FUNCTION public.butler_seal_filing_event();
CREATE TRIGGER butler_filing_event_truncate BEFORE TRUNCATE ON public.filing_execution_events
  FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_filing_event();
""")


def downgrade():
    op.execute("""
DROP TABLE public.filing_execution_events;
DROP FUNCTION public.butler_seal_filing_event();
DROP TABLE public.filing_executions;
DROP FUNCTION public.butler_seal_filing();
""")
