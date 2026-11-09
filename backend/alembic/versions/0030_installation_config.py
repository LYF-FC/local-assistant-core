"""Explicit installation identity, bounded defaults and sealed configuration history."""

from alembic import op

revision = "0030_installation_config"
down_revision = "0029_email_intake"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE FUNCTION public.butler_lock_installation_scope(p_actor uuid, p_scope text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF p_scope <> 'technical_admin' THEN RETURN false; END IF;
 PERFORM g.user_id FROM public.user_scopes g JOIN public.scopes s ON s.id=g.scope_id
 WHERE g.user_id=p_actor AND s.key=p_scope FOR SHARE OF g;
 RETURN FOUND;
END; $$;
REVOKE ALL ON FUNCTION public.butler_lock_installation_scope(uuid,text) FROM PUBLIC;
CREATE TABLE public.installation_config (
 id integer PRIMARY KEY, installation_id uuid UNIQUE, revision integer NOT NULL,
 configuration jsonb, updated_by uuid REFERENCES public.users(id),
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT ck_installation_singleton CHECK(id=1 AND revision BETWEEN 0 AND 100),
 CONSTRAINT ck_installation_state CHECK((revision=0 AND installation_id IS NULL AND configuration IS NULL AND updated_by IS NULL) OR (revision>=1 AND installation_id IS NOT NULL AND configuration IS NOT NULL AND updated_by IS NOT NULL))
);
INSERT INTO public.installation_config(id,revision,created_at,updated_at) VALUES(1,0,now(),now());
CREATE TABLE public.installation_revisions (
 id uuid PRIMARY KEY, singleton_id integer NOT NULL REFERENCES public.installation_config(id),
 revision integer NOT NULL UNIQUE CONSTRAINT ck_installation_history_revision CHECK(revision BETWEEN 1 AND 100), actor_id uuid NOT NULL REFERENCES public.users(id),
 snapshot jsonb NOT NULL, created_at timestamptz NOT NULL
);
CREATE FUNCTION public.butler_seal_installation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 IF TG_OP<>'UPDATE' THEN RAISE EXCEPTION 'Installation identity/root is sealed' USING ERRCODE='23514'; END IF;
 IF NEW.id<>OLD.id OR NEW.created_at<>OLD.created_at OR NEW.revision<>OLD.revision+1
 OR (OLD.installation_id IS NOT NULL AND NEW.installation_id IS DISTINCT FROM OLD.installation_id)
 OR NEW.installation_id IS NULL OR NEW.updated_at<OLD.updated_at OR NEW.updated_by IS NULL
 OR jsonb_typeof(NEW.configuration) IS DISTINCT FROM 'object' OR octet_length(NEW.configuration::text)>2048
 OR NEW.configuration->'schema_version' IS DISTINCT FROM '1'::jsonb
 OR NEW.configuration-'schema_version'-'defaults'<>'{}'::jsonb
 OR (NEW.configuration->'defaults')-'languages'-'timezone'<>'{}'::jsonb
 OR jsonb_typeof(NEW.configuration->'defaults') IS DISTINCT FROM 'object'
 OR jsonb_typeof(NEW.configuration->'defaults'->'languages') IS DISTINCT FROM 'array'
 OR jsonb_array_length(NEW.configuration->'defaults'->'languages') NOT BETWEEN 1 AND 3
 OR jsonb_typeof(NEW.configuration->'defaults'->'timezone') IS DISTINCT FROM 'string'
 OR length(NEW.configuration->'defaults'->>'timezone') NOT BETWEEN 1 AND 64
 OR NOT (NEW.configuration->'defaults'->'languages' <@ '["en","fr","es"]'::jsonb)
 OR (SELECT count(DISTINCT value) FROM jsonb_array_elements_text(NEW.configuration->'defaults'->'languages')) <> jsonb_array_length(NEW.configuration->'defaults'->'languages')
 OR NOT EXISTS(SELECT 1 FROM public.users u JOIN public.user_scopes g ON g.user_id=u.id JOIN public.scopes s ON s.id=g.scope_id WHERE u.id=NEW.updated_by AND u.is_active AND s.key='technical_admin') THEN
  RAISE EXCEPTION 'Invalid installation update' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER butler_installation_guard BEFORE INSERT OR UPDATE OR DELETE ON public.installation_config FOR EACH ROW EXECUTE FUNCTION public.butler_seal_installation();
CREATE TRIGGER butler_installation_truncate BEFORE TRUNCATE ON public.installation_config FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_installation();
CREATE FUNCTION public.butler_seal_installation_revision() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE parent public.installation_config;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Installation history is sealed' USING ERRCODE='23514'; END IF;
 SELECT * INTO parent FROM public.installation_config WHERE id=NEW.singleton_id;
 IF parent.id IS NULL OR parent.revision<1 OR parent.updated_by IS NULL OR NEW.revision<>parent.revision OR NEW.actor_id<>parent.updated_by OR NEW.created_at<>parent.updated_at
 OR NEW.snapshot->>'installation_id' IS DISTINCT FROM parent.installation_id::text
 OR (NEW.snapshot->>'revision')::int IS DISTINCT FROM parent.revision
 OR NEW.snapshot->'configuration' IS DISTINCT FROM parent.configuration
 OR NEW.snapshot-'installation_id'-'revision'-'configuration'-'updated_by'-'created_at'-'updated_at'<>'{}'::jsonb
 OR NEW.snapshot->>'updated_by' IS DISTINCT FROM parent.updated_by::text
 OR (NEW.snapshot->>'created_at')::timestamptz IS DISTINCT FROM parent.created_at
 OR (NEW.snapshot->>'updated_at')::timestamptz IS DISTINCT FROM parent.updated_at THEN
  RAISE EXCEPTION 'Installation history mismatch' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER butler_installation_history_guard BEFORE INSERT OR UPDATE OR DELETE ON public.installation_revisions FOR EACH ROW EXECUTE FUNCTION public.butler_seal_installation_revision();
CREATE TRIGGER butler_installation_history_truncate BEFORE TRUNCATE ON public.installation_revisions FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_installation_revision();
""")


def downgrade():
    op.execute("DROP FUNCTION public.butler_lock_installation_scope(uuid,text)")
    op.drop_table("installation_revisions")
    op.execute("DROP FUNCTION public.butler_seal_installation_revision()")
    op.drop_table("installation_config")
    op.execute("DROP FUNCTION public.butler_seal_installation()")
