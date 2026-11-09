"""Finite recurring routines, sealed plans/history and unique local-date receipts."""

from alembic import op

revision = "0027_recurring_routines"
down_revision = "0026_calendar_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""

CREATE TABLE routines (
	id UUID NOT NULL,
	owner_id UUID NOT NULL,
	scope_key VARCHAR(96) NOT NULL,
	state VARCHAR(16) NOT NULL,
	revision INTEGER NOT NULL,
	changes INTEGER NOT NULL,
	position INTEGER NOT NULL,
	next_at TIMESTAMP WITH TIME ZONE,
	data JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_routine_versions CHECK (revision BETWEEN 1 AND 1000 AND changes BETWEEN 0 AND 102 AND position BETWEEN 0 AND 366),
	CONSTRAINT ck_routine_scope CHECK (scope_key IN ('household_shared','member_a_private','member_b_private')),
	CONSTRAINT ck_routine_content CHECK ((state='active' AND data IS NOT NULL AND next_at IS NOT NULL) OR (state IN ('paused','finished','blocked') AND data IS NOT NULL AND next_at IS NULL) OR (state='forgotten' AND data IS NULL AND next_at IS NULL)),
	FOREIGN KEY(owner_id) REFERENCES users (id)
)

;
CREATE INDEX ix_routine_due ON routines (state, next_at, id);
CREATE INDEX ix_routine_scope_owner ON routines (scope_key, owner_id, id);

CREATE TABLE routine_revisions (
	id UUID NOT NULL,
	routine_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	actor_id UUID,
	snapshot JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_routine_revision UNIQUE (routine_id, revision),
	FOREIGN KEY(routine_id) REFERENCES routines (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;

CREATE TABLE routine_occurrences (
	id UUID NOT NULL,
	routine_id UUID NOT NULL,
	routine_revision INTEGER NOT NULL,
	local_date VARCHAR(10) NOT NULL,
	due_at TIMESTAMP WITH TIME ZONE,
	task_id UUID,
	outcome VARCHAR(16) NOT NULL,
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_routine_local_date UNIQUE (routine_id, local_date),
	CONSTRAINT uq_routine_task UNIQUE (task_id),
	CONSTRAINT ck_routine_occurrence_revision CHECK (routine_revision>=1),
	CONSTRAINT ck_routine_outcome CHECK ((outcome='created' AND task_id IS NOT NULL AND due_at IS NOT NULL) OR (outcome='missed' AND task_id IS NULL AND due_at IS NOT NULL) OR (outcome='dst_gap' AND task_id IS NULL AND due_at IS NULL)),
	FOREIGN KEY(routine_id) REFERENCES routines (id),
	FOREIGN KEY(task_id) REFERENCES manual_tasks (id)
)

;
CREATE FUNCTION public.butler_seal_routine() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE due timestamptz;
BEGIN
 IF TG_OP IN ('DELETE','TRUNCATE') THEN RAISE EXCEPTION 'Routine deletion is sealed' USING ERRCODE='23514'; END IF;
 IF NEW.state<>'forgotten' THEN
  IF jsonb_typeof(NEW.data) IS DISTINCT FROM 'object' OR jsonb_typeof(NEW.data->'plan') IS DISTINCT FROM 'array'
    OR jsonb_array_length(NEW.data->'plan') NOT BETWEEN 1 AND 366 OR NEW.position>jsonb_array_length(NEW.data->'plan')
    OR octet_length(NEW.data::text)>65000 OR NEW.data->'values'->>'scope' IS DISTINCT FROM NEW.scope_key THEN
   RAISE EXCEPTION 'Invalid routine plan' USING ERRCODE='23514'; END IF;
  SELECT (item->>'due_at')::timestamptz INTO due FROM jsonb_array_elements(NEW.data->'plan') WITH ORDINALITY p(item,n)
    WHERE n>NEW.position AND item->>'due_at' IS NOT NULL ORDER BY n LIMIT 1;
  IF (NEW.state='active' AND NEW.next_at IS DISTINCT FROM due) OR (NEW.state='finished' AND due IS NOT NULL) THEN
   RAISE EXCEPTION 'Routine cursor differs from plan' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.revision<>1 OR NEW.changes<>0 OR NEW.position<>0 OR NEW.state<>'active'
    OR NEW.created_at<>NEW.updated_at OR NEW.next_at<=NEW.created_at THEN
   RAISE EXCEPTION 'Routine must start with explicit future intent' USING ERRCODE='23514'; END IF;
 ELSE
  IF ROW(NEW.id,NEW.owner_id,NEW.scope_key,NEW.created_at) IS DISTINCT FROM ROW(OLD.id,OLD.owner_id,OLD.scope_key,OLD.created_at)
    OR OLD.state='forgotten' OR NEW.revision<>OLD.revision+1 OR NEW.updated_at<OLD.updated_at
    OR NEW.changes NOT IN (OLD.changes,OLD.changes+1)
    OR (NEW.data IS DISTINCT FROM OLD.data AND NEW.changes<>OLD.changes+1)
    OR (NEW.changes=OLD.changes AND NEW.position<OLD.position)
    OR (NEW.changes=OLD.changes AND OLD.state<>'active')
    OR (NEW.changes=OLD.changes AND NEW.state NOT IN ('active','finished','blocked')) THEN
   RAISE EXCEPTION 'Routine identity or progression is sealed' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER butler_routine_guard BEFORE INSERT OR UPDATE OR DELETE ON public.routines FOR EACH ROW EXECUTE FUNCTION public.butler_seal_routine();
CREATE TRIGGER butler_routine_truncate BEFORE TRUNCATE ON public.routines FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_routine();
CREATE FUNCTION public.butler_seal_routine_history() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE parent public.routines;
BEGIN
 IF TG_OP='INSERT' THEN
  SELECT * INTO parent FROM public.routines WHERE id=NEW.routine_id;
  IF parent.id IS NULL OR (NEW.actor_id IS NOT NULL AND NEW.actor_id<>parent.owner_id)
    OR NEW.revision<>parent.revision OR NEW.created_at<>parent.updated_at
    OR ((parent.state='forgotten') IS DISTINCT FROM (NEW.snapshot IS NULL)) THEN
   RAISE EXCEPTION 'Routine history mismatches parent' USING ERRCODE='23514'; END IF;
  IF NEW.snapshot IS NOT NULL AND (NEW.snapshot->>'id' IS DISTINCT FROM parent.id::text
    OR NEW.snapshot->>'owner_id' IS DISTINCT FROM parent.owner_id::text OR NEW.snapshot->>'scope' IS DISTINCT FROM parent.scope_key
    OR NEW.snapshot->>'state' IS DISTINCT FROM parent.state OR (NEW.snapshot->>'revision')::int IS DISTINCT FROM parent.revision
    OR (NEW.snapshot->>'changes')::int IS DISTINCT FROM parent.changes OR (NEW.snapshot->>'position')::int IS DISTINCT FROM parent.position
    OR (NEW.snapshot->>'next_at')::timestamptz IS DISTINCT FROM parent.next_at
    OR (NEW.snapshot->>'created_at')::timestamptz IS DISTINCT FROM parent.created_at
    OR (NEW.snapshot->>'updated_at')::timestamptz IS DISTINCT FROM parent.updated_at
    OR NEW.snapshot->'data' IS DISTINCT FROM parent.data) THEN
   RAISE EXCEPTION 'Routine snapshot differs from parent' USING ERRCODE='23514'; END IF;
  RETURN NEW;
 ELSIF TG_OP='UPDATE' THEN
  IF ROW(NEW.id,NEW.routine_id,NEW.revision,NEW.actor_id,NEW.created_at) IS NOT DISTINCT FROM ROW(OLD.id,OLD.routine_id,OLD.revision,OLD.actor_id,OLD.created_at)
    AND NEW.snapshot IS NULL AND EXISTS(SELECT 1 FROM public.routines WHERE id=OLD.routine_id AND state='forgotten') THEN RETURN NEW; END IF;
 END IF;
 RAISE EXCEPTION 'Routine history is sealed' USING ERRCODE='23514';
END; $$;
CREATE TRIGGER butler_routine_history_guard BEFORE INSERT OR UPDATE OR DELETE ON public.routine_revisions FOR EACH ROW EXECUTE FUNCTION public.butler_seal_routine_history();
CREATE TRIGGER butler_routine_history_truncate BEFORE TRUNCATE ON public.routine_revisions FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_routine_history();
CREATE FUNCTION public.butler_seal_routine_occurrence() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE parent public.routines;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Routine occurrence is sealed' USING ERRCODE='23514'; END IF;
 SELECT * INTO parent FROM public.routines WHERE id=NEW.routine_id;
 IF parent.id IS NULL OR parent.state<>'active' OR NEW.routine_revision>parent.revision
   OR NEW.local_date!~'^\d{4}-\d{2}-\d{2}$' OR NOT EXISTS(SELECT 1 FROM public.routine_revisions WHERE routine_id=NEW.routine_id AND revision=NEW.routine_revision)
   OR (SELECT count(*) FROM public.routine_occurrences WHERE routine_id=NEW.routine_id)>=400 THEN
  RAISE EXCEPTION 'Invalid routine occurrence' USING ERRCODE='23514'; END IF;
 IF NEW.task_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.manual_tasks WHERE id=NEW.task_id AND owner_id=parent.owner_id
    AND scope_key=parent.scope_key AND revision=1 AND state='active' AND due_at=NEW.due_at) THEN
  RAISE EXCEPTION 'Routine task identity mismatch' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER butler_routine_occurrence_guard BEFORE INSERT OR UPDATE OR DELETE ON public.routine_occurrences FOR EACH ROW EXECUTE FUNCTION public.butler_seal_routine_occurrence();
CREATE TRIGGER butler_routine_occurrence_truncate BEFORE TRUNCATE ON public.routine_occurrences FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_routine_occurrence();

    """)


def downgrade():
    op.drop_table("routine_occurrences")
    op.execute("DROP FUNCTION public.butler_seal_routine_occurrence()")
    op.drop_table("routine_revisions")
    op.execute("DROP FUNCTION public.butler_seal_routine_history()")
    op.drop_table("routines")
    op.execute("DROP FUNCTION public.butler_seal_routine()")
