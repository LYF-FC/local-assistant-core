"""Quarantined transactional synthetic drafts; no application write grants.

Revision ID: 0010_work_drafts
Revises: 0009_work_read_audit
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_work_drafts"
down_revision = "0009_work_read_audit"
branch_labels = None
depends_on = None

TABLES = (
    "retention_policies",
    "source_registry",
    "drafts",
    "draft_revisions",
    "draft_audit",
    "draft_tombstones",
)


def upgrade():
    op.execute("""
      CREATE TABLE work.retention_policies (
        workspace_id uuid NOT NULL REFERENCES public.work_workspaces(id),
        id uuid NOT NULL, max_age_seconds integer NOT NULL CHECK(max_age_seconds BETWEEN 1 AND 31536000),
        PRIMARY KEY(workspace_id,id)
      );
      CREATE TABLE work.source_registry (
        workspace_id uuid NOT NULL, id uuid NOT NULL, is_active boolean NOT NULL DEFAULT true,
        PRIMARY KEY(workspace_id,id),
        FOREIGN KEY(workspace_id,id) REFERENCES work.validation_records(workspace_id,id)
      );
      CREATE TABLE work.drafts (
        workspace_id uuid NOT NULL, id uuid NOT NULL, policy_id uuid NOT NULL,
        revision smallint NOT NULL CHECK(revision BETWEEN 1 AND 101),
        state text NOT NULL CHECK(state IN ('draft','confirmed','forgotten')),
        retain_until timestamptz NULL,
        snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object'),
        PRIMARY KEY(workspace_id,id),
        FOREIGN KEY(workspace_id,policy_id) REFERENCES work.retention_policies(workspace_id,id),
        CHECK((snapshot->>'workspace_id'=workspace_id::text AND snapshot->>'id'=id::text
          AND snapshot->>'policy_id'=policy_id::text AND (snapshot->>'revision')::int=revision
          AND snapshot->>'state'=state) IS TRUE),
        CHECK(snapshot ?& ARRAY['id','workspace_id','policy_id','revision','state','marker','source_ids','owner_id','due_at','retain_until','created_at','updated_at','actor_id','kind']),
        CHECK(jsonb_typeof(snapshot->'source_ids')='array' AND jsonb_array_length(snapshot->'source_ids')<=10),
        CHECK(snapshot->>'owner_id' IS NULL),
        CHECK((snapshot->>'kind' IN ('observation','question','decision','action')) IS TRUE),
        CHECK(state='forgotten' OR (snapshot->>'marker' IS NOT NULL AND snapshot->>'retain_until' IS NOT NULL)),
        CHECK(snapshot->>'due_at' IS NULL OR (snapshot->>'due_at')::timestamptz IS NOT NULL),
        CHECK((state='forgotten' AND retain_until IS NULL AND snapshot->>'marker' IS NULL
          AND snapshot->'source_ids'='[]' AND snapshot->>'due_at' IS NULL AND snapshot->>'retain_until' IS NULL)
          OR (state<>'forgotten' AND retain_until IS NOT NULL
          AND snapshot->>'marker' ~ '^synthetic:[a-zA-Z0-9 _.-]+$'
          AND octet_length(snapshot->>'marker') BETWEEN 11 AND 256
          AND (snapshot->>'retain_until')::timestamptz=retain_until)),
        CHECK(state<>'confirmed' OR jsonb_array_length(snapshot->'source_ids')>0)
      );
      CREATE TABLE work.draft_revisions (
        workspace_id uuid NOT NULL, record_id uuid NOT NULL, revision smallint NOT NULL,
        actor_id uuid NOT NULL, occurred_at timestamptz NOT NULL, snapshot jsonb NULL,
        PRIMARY KEY(workspace_id,record_id,revision),
        FOREIGN KEY(workspace_id,record_id) REFERENCES work.drafts(workspace_id,id)
      );
      CREATE TABLE work.draft_audit (
        workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(),
        record_id uuid NOT NULL, revision smallint NOT NULL, actor_id uuid NOT NULL,
        event_type text NOT NULL CHECK(event_type IN ('draft.created','draft.corrected','draft.confirmed','draft.forgotten','draft.read_prepared')),
        database_initiator text NOT NULL DEFAULT current_user,
        occurred_at timestamptz NOT NULL DEFAULT statement_timestamp(),
        PRIMARY KEY(workspace_id,id),
        FOREIGN KEY(workspace_id,record_id) REFERENCES work.drafts(workspace_id,id)
      );
      CREATE TABLE work.draft_tombstones (
        workspace_id uuid NOT NULL, record_id uuid NOT NULL, revision smallint NOT NULL,
        forgotten_at timestamptz NOT NULL DEFAULT statement_timestamp(),
        PRIMARY KEY(workspace_id,record_id),
        FOREIGN KEY(workspace_id,record_id) REFERENCES work.drafts(workspace_id,id)
      );
      CREATE FUNCTION work.draft_write_barrier() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      BEGIN
        IF TG_OP IN ('DELETE','TRUNCATE') OR current_setting('transaction_isolation')<>'read committed' THEN
          RAISE EXCEPTION 'Draft operation denied' USING ERRCODE='23514';
        END IF;
        PERFORM pg_advisory_xact_lock_shared(1508310,1);
        RETURN NULL;
      END; $$;
      CREATE TRIGGER draft_write_barrier BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE
        ON work.drafts FOR EACH STATEMENT EXECUTE FUNCTION work.draft_write_barrier();
      CREATE TRIGGER source_registry_barrier BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE
        ON work.source_registry FOR EACH STATEMENT EXECUTE FUNCTION public.butler_work_registry_barrier();

      CREATE FUNCTION work.guard_draft() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      DECLARE maximum integer; total integer; selected_count integer; event_time timestamptz;
      BEGIN
        event_time:=clock_timestamp();
        IF NOT EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=NEW.workspace_id AND is_active AND slug LIKE 'synthetic-%') THEN
          RAISE EXCEPTION 'Draft operation denied' USING ERRCODE='23514';
        END IF;
        IF TG_OP='INSERT' THEN
          IF NEW.revision<>1 OR NEW.state<>'draft' THEN
            RAISE EXCEPTION 'Draft operation denied' USING ERRCODE='23514';
          END IF;
          NEW.snapshot:=NEW.snapshot || jsonb_build_object('created_at',event_time,'updated_at',event_time);
        ELSE
          IF OLD.state='forgotten' OR event_time<(OLD.snapshot->>'updated_at')::timestamptz
            OR NEW.workspace_id<>OLD.workspace_id OR NEW.id<>OLD.id
            OR NEW.policy_id<>OLD.policy_id OR NEW.revision<>OLD.revision+1
            OR NEW.snapshot->>'kind' IS DISTINCT FROM OLD.snapshot->>'kind'
            OR (NEW.state<>'forgotten' AND (OLD.retain_until<=event_time OR OLD.revision>=100
              OR NEW.retain_until>OLD.retain_until)) THEN
            RAISE EXCEPTION 'Draft operation denied' USING ERRCODE='23514';
          END IF;
          IF NEW.state='confirmed' AND (OLD.state<>'draft'
            OR (NEW.snapshot-ARRAY['state','revision','actor_id','updated_at','created_at']) IS DISTINCT FROM
               (OLD.snapshot-ARRAY['state','revision','actor_id','updated_at','created_at'])) THEN
            RAISE EXCEPTION 'Draft operation denied' USING ERRCODE='23514';
          END IF;
          NEW.snapshot:=NEW.snapshot || jsonb_build_object('created_at',OLD.snapshot->'created_at','updated_at',event_time);
        END IF;
        IF NEW.state<>'forgotten' THEN
          SELECT max_age_seconds INTO maximum FROM work.retention_policies
            WHERE workspace_id=NEW.workspace_id AND id=NEW.policy_id FOR SHARE;
          IF maximum IS NULL OR NEW.retain_until<=event_time
            OR NEW.retain_until>event_time+make_interval(secs=>maximum) THEN
            RAISE EXCEPTION 'Draft policy denied' USING ERRCODE='23514';
          END IF;
          SELECT count(*),count(DISTINCT value) INTO total,selected_count FROM jsonb_array_elements_text(NEW.snapshot->'source_ids');
          IF total<>selected_count THEN
            RAISE EXCEPTION 'Draft source denied' USING ERRCODE='23514';
          END IF;
          PERFORM id FROM work.source_registry WHERE workspace_id=NEW.workspace_id AND is_active
            AND id IN (SELECT value::uuid FROM jsonb_array_elements_text(NEW.snapshot->'source_ids'))
            ORDER BY id FOR SHARE;
          GET DIAGNOSTICS selected_count=ROW_COUNT;
          IF selected_count<>total THEN
            RAISE EXCEPTION 'Draft source denied' USING ERRCODE='23514';
          END IF;
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER draft_guard BEFORE INSERT OR UPDATE ON work.drafts
        FOR EACH ROW EXECUTE FUNCTION work.guard_draft();

      CREATE FUNCTION work.guard_draft_revision() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      BEGIN
        IF NEW.snapshot IS NOT NULL OR OLD.snapshot IS NULL
          OR (to_jsonb(NEW)-'snapshot') IS DISTINCT FROM (to_jsonb(OLD)-'snapshot')
          OR NOT EXISTS(SELECT 1 FROM work.drafts WHERE workspace_id=OLD.workspace_id AND id=OLD.record_id AND state='forgotten') THEN
          RAISE EXCEPTION 'Revision mutation denied' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER draft_revision_redaction BEFORE UPDATE ON work.draft_revisions
        FOR EACH ROW EXECUTE FUNCTION work.guard_draft_revision();

      CREATE FUNCTION work.append_draft_event() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      DECLARE event_name text;
      BEGIN
        event_name:=CASE WHEN TG_OP='INSERT' THEN 'draft.created'
          WHEN NEW.state='forgotten' THEN 'draft.forgotten'
          WHEN NEW.state='confirmed' THEN 'draft.confirmed' ELSE 'draft.corrected' END;
        IF NEW.state='forgotten' THEN
          UPDATE work.draft_revisions SET snapshot=NULL WHERE workspace_id=NEW.workspace_id AND record_id=NEW.id AND snapshot IS NOT NULL;
          INSERT INTO work.draft_tombstones(workspace_id,record_id,revision) VALUES(NEW.workspace_id,NEW.id,NEW.revision);
        END IF;
        INSERT INTO work.draft_revisions(workspace_id,record_id,revision,actor_id,occurred_at,snapshot)
          VALUES(NEW.workspace_id,NEW.id,NEW.revision,(NEW.snapshot->>'actor_id')::uuid,
            (NEW.snapshot->>'updated_at')::timestamptz,CASE WHEN NEW.state='forgotten' THEN NULL ELSE NEW.snapshot END);
        INSERT INTO work.draft_audit(workspace_id,record_id,revision,actor_id,event_type)
          VALUES(NEW.workspace_id,NEW.id,NEW.revision,(NEW.snapshot->>'actor_id')::uuid,event_name);
        RETURN NEW;
      END; $$;
      CREATE TRIGGER draft_event AFTER INSERT OR UPDATE ON work.drafts
        FOR EACH ROW EXECUTE FUNCTION work.append_draft_event();
    """)
    owner = op.get_bind().scalar(sa.text("SELECT current_user"))
    quoted = op.get_bind().dialect.identifier_preparer.quote(owner)
    for table in TABLES:
        op.execute(f"ALTER TABLE work.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE work.{table} FORCE ROW LEVEL SECURITY")
        predicate = "workspace_id IN (SELECT id FROM work.active_workspace)"
        if table == "drafts":
            predicate += """ AND (state='forgotten' OR (retain_until>statement_timestamp() AND NOT EXISTS(
              SELECT 1 FROM jsonb_array_elements_text(snapshot->'source_ids') refs(value)
              WHERE NOT EXISTS(SELECT 1 FROM work.source_registry s WHERE s.workspace_id=drafts.workspace_id AND s.id=refs.value::uuid AND s.is_active))))"""
        elif table == "draft_revisions":
            predicate += """ AND (snapshot IS NULL OR (EXISTS(SELECT 1 FROM work.drafts d WHERE d.workspace_id=draft_revisions.workspace_id AND d.id=draft_revisions.record_id) AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements_text(draft_revisions.snapshot->'source_ids') refs(value) WHERE NOT EXISTS(SELECT 1 FROM work.source_registry s WHERE s.workspace_id=draft_revisions.workspace_id AND s.id=refs.value::uuid AND s.is_active))))"""
        op.execute(f"CREATE POLICY workspace_access ON work.{table} USING ({predicate})")
        op.execute(
            f"CREATE POLICY operator_access ON work.{table} TO {quoted} USING (true) WITH CHECK (true)"
        )
        op.execute(f"REVOKE ALL ON work.{table} FROM PUBLIC")
        if table in {"retention_policies", "draft_audit", "draft_tombstones"}:
            op.execute(
                f"CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE OR TRUNCATE ON work.{table} FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation()"
            )
        elif table == "draft_revisions":
            op.execute(
                "CREATE TRIGGER immutable_rows BEFORE DELETE OR TRUNCATE ON work.draft_revisions FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation()"
            )
    for function in (
        "draft_write_barrier",
        "guard_draft",
        "guard_draft_revision",
        "append_draft_event",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION work.{function}() FROM PUBLIC")


def downgrade():
    for table in (
        "draft_tombstones",
        "draft_audit",
        "draft_revisions",
        "drafts",
        "source_registry",
        "retention_policies",
    ):
        op.execute(f"DROP TABLE work.{table}")
    for function in (
        "append_draft_event",
        "guard_draft_revision",
        "guard_draft",
        "draft_write_barrier",
    ):
        op.execute(f"DROP FUNCTION work.{function}()")
