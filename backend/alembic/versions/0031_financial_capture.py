"""Owner-private financial capture and sealed history."""

from alembic import op

revision = "0031_financial_capture"
down_revision = "0030_installation_config"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE public.financial_records (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES public.users(id), scope_key varchar(96) NOT NULL,
 kind varchar(16) NOT NULL, state varchar(16) NOT NULL, revision integer NOT NULL, payload jsonb,
 accepted_by uuid REFERENCES public.users(id), accepted_at timestamptz, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT ck_financial_revision CHECK(revision BETWEEN 1 AND 101),
 CONSTRAINT ck_financial_scope CHECK(scope_key='finance_private'),
 CONSTRAINT ck_financial_kind CHECK(kind IN ('goal','assumption','plan','source')),
 CONSTRAINT ck_financial_state CHECK((state='active' AND revision<=100 AND payload IS NOT NULL) OR (state='forgotten' AND payload IS NULL AND accepted_by IS NULL AND accepted_at IS NULL)),
 CONSTRAINT ck_financial_acceptance CHECK((accepted_by IS NULL AND accepted_at IS NULL) OR (kind='plan' AND accepted_by=owner_id AND accepted_at IS NOT NULL))
);
CREATE TABLE public.financial_revisions (
 id uuid PRIMARY KEY, record_id uuid NOT NULL REFERENCES public.financial_records(id), revision integer NOT NULL,
 actor_id uuid NOT NULL REFERENCES public.users(id), snapshot jsonb, created_at timestamptz NOT NULL,
 CONSTRAINT uq_financial_revision UNIQUE(record_id,revision)
);
CREATE FUNCTION public.butler_lock_finance_scope(p_actor uuid,p_scope text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
 IF p_scope<>'finance_private' THEN RETURN false; END IF;
 PERFORM g.user_id FROM public.user_scopes g JOIN public.scopes s ON s.id=g.scope_id WHERE g.user_id=p_actor AND s.key=p_scope FOR SHARE OF g;
 RETURN FOUND; END; $$;
REVOKE ALL ON FUNCTION public.butler_lock_finance_scope(uuid,text) FROM PUBLIC;
CREATE FUNCTION public.butler_seal_financial_record() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ DECLARE field text; BEGIN
 IF TG_OP NOT IN ('INSERT','UPDATE') THEN RAISE EXCEPTION 'Financial deletion sealed' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.revision<>1 OR NEW.state<>'active' OR NEW.accepted_by IS NOT NULL OR NEW.created_at<>NEW.updated_at THEN RAISE EXCEPTION 'Invalid initial financial state' USING ERRCODE='23514'; END IF;
 ELSE
  IF ROW(NEW.id,NEW.owner_id,NEW.scope_key,NEW.kind,NEW.created_at) IS DISTINCT FROM ROW(OLD.id,OLD.owner_id,OLD.scope_key,OLD.kind,OLD.created_at)
   OR OLD.state='forgotten' OR NEW.revision<>OLD.revision+1 OR NEW.updated_at<OLD.updated_at
   OR (NEW.accepted_by IS NOT NULL AND (OLD.accepted_by IS NOT NULL OR NEW.payload IS DISTINCT FROM OLD.payload OR NEW.accepted_at<>NEW.updated_at)) THEN
   RAISE EXCEPTION 'Financial identity/history sealed' USING ERRCODE='23514'; END IF;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.users u JOIN public.user_scopes g ON g.user_id=u.id JOIN public.scopes s ON s.id=g.scope_id WHERE u.id=NEW.owner_id AND u.is_active AND s.key='finance_private') THEN RAISE EXCEPTION 'Current finance authority required' USING ERRCODE='23514'; END IF;
 IF NEW.state='active' THEN
  FOREACH field IN ARRAY ARRAY['topic','basis','title','statement','as_of','source_reference'] LOOP
   IF jsonb_typeof(NEW.payload->field) IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'Financial string required' USING ERRCODE='23514'; END IF;
  END LOOP;
  FOREACH field IN ARRAY ARRAY['target_date','source_date'] LOOP
   IF NEW.payload->field IS DISTINCT FROM 'null'::jsonb AND (jsonb_typeof(NEW.payload->field) IS DISTINCT FROM 'string' OR (NEW.payload->>field)::date NOT BETWEEN DATE '1900-01-01' AND DATE '2200-12-31') THEN RAISE EXCEPTION 'Invalid financial date' USING ERRCODE='23514'; END IF;
  END LOOP;
  IF jsonb_typeof(NEW.payload) IS DISTINCT FROM 'object' OR octet_length(NEW.payload::text)>32768
   OR NEW.payload->'schema_version' IS DISTINCT FROM '1'::jsonb
   OR NOT (NEW.payload ?& ARRAY['schema_version','topic','basis','title','statement','as_of','target_date','source_reference','source_date','amount','currency'])
   OR NEW.payload-'schema_version'-'topic'-'basis'-'title'-'statement'-'as_of'-'target_date'-'source_reference'-'source_date'-'amount'-'currency'<>'{}'::jsonb
   OR NEW.payload->>'topic' NOT IN ('lifestyle','horizon','spending','property','constraint','general')
   OR NEW.payload->>'basis' NOT IN ('confirmed_input','assumption','forecast','unknown')
   OR length(trim(NEW.payload->>'title')) NOT BETWEEN 1 AND 160
   OR length(NEW.payload->>'statement')>4000 OR length(trim(NEW.payload->>'source_reference')) NOT BETWEEN 1 AND 512
   OR (NEW.payload->>'as_of')::date NOT BETWEEN DATE '1900-01-01' AND DATE '2200-12-31'
   OR (NEW.payload->'amount' IS DISTINCT FROM 'null'::jsonb AND jsonb_typeof(NEW.payload->'amount') IS DISTINCT FROM 'string')
   OR ((NEW.payload->>'amount') IS NULL)<>((NEW.payload->>'currency') IS NULL)
   OR (NEW.payload->>'amount' IS NOT NULL AND ((NEW.payload->>'amount')!~'^(0|[1-9][0-9]{0,11})[.][0-9]{2}$' OR NEW.payload->>'currency' NOT IN ('EUR','USD','GBP','CHF','CAD','JPY'))) THEN
   RAISE EXCEPTION 'Invalid financial payload' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW; END; $$;
CREATE TRIGGER financial_guard BEFORE INSERT OR UPDATE OR DELETE ON public.financial_records FOR EACH ROW EXECUTE FUNCTION public.butler_seal_financial_record();
CREATE TRIGGER financial_truncate BEFORE TRUNCATE ON public.financial_records FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_financial_record();
CREATE FUNCTION public.butler_seal_financial_revision() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ DECLARE parent public.financial_records; BEGIN
 IF TG_OP NOT IN ('INSERT','UPDATE') THEN RAISE EXCEPTION 'Financial history sealed' USING ERRCODE='23514'; END IF;
 SELECT * INTO parent FROM public.financial_records WHERE id=NEW.record_id;
 IF TG_OP='UPDATE' THEN
  IF parent.state<>'forgotten' OR NEW.snapshot IS NOT NULL OR ROW(NEW.id,NEW.record_id,NEW.revision,NEW.actor_id,NEW.created_at) IS DISTINCT FROM ROW(OLD.id,OLD.record_id,OLD.revision,OLD.actor_id,OLD.created_at) THEN RAISE EXCEPTION 'Financial history rewrite denied' USING ERRCODE='23514'; END IF;
 ELSE
  IF parent.id IS NULL OR NEW.revision<>parent.revision OR NEW.actor_id<>parent.owner_id OR NEW.created_at<>parent.updated_at OR (parent.state='forgotten' AND NEW.snapshot IS NOT NULL)
   OR (parent.state='active' AND (NEW.snapshot IS NULL OR NEW.snapshot->>'id' IS DISTINCT FROM parent.id::text OR NEW.snapshot->>'owner_id' IS DISTINCT FROM parent.owner_id::text
    OR (NEW.snapshot->>'revision')::int IS DISTINCT FROM parent.revision OR NEW.snapshot->'values' IS DISTINCT FROM parent.payload
    OR NEW.snapshot->>'scope' IS DISTINCT FROM parent.scope_key OR NEW.snapshot->>'kind' IS DISTINCT FROM parent.kind OR NEW.snapshot->>'state' IS DISTINCT FROM parent.state
    OR (NEW.snapshot->>'created_at')::timestamptz IS DISTINCT FROM parent.created_at OR (NEW.snapshot->>'updated_at')::timestamptz IS DISTINCT FROM parent.updated_at
    OR (NEW.snapshot->>'accepted_at')::timestamptz IS DISTINCT FROM parent.accepted_at OR (NEW.snapshot->>'accepted_by')::uuid IS DISTINCT FROM parent.accepted_by
    OR NEW.snapshot->>'plan_status' IS DISTINCT FROM CASE WHEN parent.kind='plan' THEN CASE WHEN parent.accepted_by IS NULL THEN 'proposed' ELSE 'accepted' END ELSE NULL END
    OR NEW.snapshot-'id'-'owner_id'-'scope'-'kind'-'state'-'revision'-'created_at'-'updated_at'-'values'-'plan_status'-'accepted_by'-'accepted_at'<>'{}'::jsonb)) THEN
   RAISE EXCEPTION 'Financial history mismatch' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW; END; $$;
CREATE TRIGGER financial_history_guard BEFORE INSERT OR UPDATE OR DELETE ON public.financial_revisions FOR EACH ROW EXECUTE FUNCTION public.butler_seal_financial_revision();
CREATE TRIGGER financial_history_truncate BEFORE TRUNCATE ON public.financial_revisions FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_financial_revision();
""")


def downgrade():
    op.drop_table("financial_revisions")
    op.execute("DROP FUNCTION public.butler_seal_financial_revision()")
    op.drop_table("financial_records")
    op.execute("DROP FUNCTION public.butler_seal_financial_record()")
    op.execute("DROP FUNCTION public.butler_lock_finance_scope(uuid,text)")
