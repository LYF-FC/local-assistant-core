"""Private synthetic capture preparation and exactly-once local outcome.

Revision ID: 0014_work_capture
Revises: 0013_work_parties
"""

import sqlalchemy as sa

from alembic import op

revision = "0014_work_capture"
down_revision = "0013_work_parties"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE TABLE work.capture_intents (
        workspace_id uuid NOT NULL,
        id uuid NOT NULL DEFAULT gen_random_uuid(),
        actor_id uuid NOT NULL, session_id uuid NOT NULL, request_id uuid NOT NULL,
        payload jsonb NULL,
        payload_hash text NULL,
        CHECK((payload IS NULL AND payload_hash IS NULL) OR
              (payload IS NOT NULL AND payload_hash IS NOT NULL AND payload_hash ~ '^[a-f0-9]{64}$')),
        state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','applied','denied')),
        record_id uuid NULL, reason_code text NULL CHECK(reason_code IN ('authority','expired','evidence','stale')),
        prepared_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        expires_at timestamptz NOT NULL,
        finished_at timestamptz NULL,
        PRIMARY KEY(workspace_id,id), UNIQUE(id),
        UNIQUE(workspace_id,actor_id,session_id,request_id),
        FOREIGN KEY(workspace_id) REFERENCES public.work_workspaces(id),
        FOREIGN KEY(workspace_id,record_id) REFERENCES work.drafts(workspace_id,id),
        CHECK(expires_at>prepared_at AND expires_at<=prepared_at+interval '5 minutes'),
        CHECK((state='pending' AND payload IS NOT NULL AND finished_at IS NULL AND record_id IS NULL AND reason_code IS NULL)
          OR (state='applied' AND payload IS NULL AND finished_at IS NOT NULL AND record_id IS NOT NULL AND reason_code IS NULL)
          OR (state='denied' AND payload IS NULL AND finished_at IS NOT NULL AND record_id IS NULL AND reason_code IS NOT NULL)),
        CHECK(payload IS NULL OR (jsonb_typeof(payload)='object' AND jsonb_typeof(payload->'draft')='object'
          AND (payload->'draft'->>'marker' ~ '^synthetic:[a-zA-Z0-9 _.-]+$') IS TRUE
          AND octet_length(payload->'draft'->>'marker') BETWEEN 11 AND 256
          AND octet_length(payload::text)<=8192))
      );
      CREATE TABLE work.capture_audit (
        workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(),
        capture_id uuid NOT NULL, event_type text NOT NULL CHECK(event_type IN ('capture.prepared','capture.applied','capture.denied')),
        database_initiator text NOT NULL DEFAULT current_user,
        occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,capture_id,event_type),
        FOREIGN KEY(workspace_id,capture_id) REFERENCES work.capture_intents(workspace_id,id)
      );
      CREATE FUNCTION work.guard_capture() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      DECLARE actual_owner boolean; event_time timestamptz;
      BEGIN
        actual_owner:=session_user=current_user AND current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.capture_intents'::regclass);
        event_time:=clock_timestamp();
        IF current_setting('transaction_isolation')<>'read committed' THEN
          RAISE EXCEPTION 'Capture isolation denied' USING ERRCODE='23514';
        END IF;
        IF TG_OP='INSERT' THEN
          IF actual_owner THEN
            IF NOT EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=NEW.workspace_id AND is_active AND slug LIKE 'synthetic-%') THEN
              RAISE EXCEPTION 'Capture workspace denied' USING ERRCODE='23514';
            END IF;
          ELSIF NOT EXISTS(SELECT 1 FROM work.active_workspace WHERE id=NEW.workspace_id) THEN
            RAISE EXCEPTION 'Capture workspace denied' USING ERRCODE='23514';
          END IF;
          IF NEW.state<>'pending' OR NEW.expires_at<=event_time OR NEW.expires_at>event_time+interval '5 minutes' THEN
            RAISE EXCEPTION 'Capture preparation denied' USING ERRCODE='23514';
          END IF;
          NEW.prepared_at:=event_time;
        ELSE
          IF NOT actual_owner OR OLD.state<>'pending' OR NEW.state NOT IN ('applied','denied')
            OR NEW.payload IS NOT NULL
            OR (to_jsonb(NEW)-ARRAY['payload','payload_hash','state','record_id','reason_code','finished_at']) IS DISTINCT FROM
               (to_jsonb(OLD)-ARRAY['payload','payload_hash','state','record_id','reason_code','finished_at']) THEN
            RAISE EXCEPTION 'Capture outcome denied' USING ERRCODE='23514';
          END IF;
          NEW.finished_at:=event_time;
        END IF;
        NEW.payload_hash:=CASE WHEN NEW.payload IS NULL THEN NULL ELSE encode(sha256(convert_to(NEW.payload::text,'UTF8')),'hex') END;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER capture_guard BEFORE INSERT OR UPDATE ON work.capture_intents
        FOR EACH ROW EXECUTE FUNCTION work.guard_capture();
      CREATE TRIGGER capture_no_delete BEFORE DELETE OR TRUNCATE ON work.capture_intents
        FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation();
      CREATE FUNCTION work.audit_capture() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      BEGIN
        INSERT INTO work.capture_audit(workspace_id,capture_id,event_type)
          VALUES(NEW.workspace_id,NEW.id,CASE WHEN TG_OP='INSERT' THEN 'capture.prepared'
            WHEN NEW.state='applied' THEN 'capture.applied' ELSE 'capture.denied' END);
        RETURN NEW;
      END; $$;
      CREATE TRIGGER capture_event AFTER INSERT OR UPDATE ON work.capture_intents
        FOR EACH ROW EXECUTE FUNCTION work.audit_capture();
      CREATE FUNCTION work.guard_capture_audit() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      DECLARE phase text;
      BEGIN
        SELECT CASE state WHEN 'pending' THEN 'capture.prepared' WHEN 'applied' THEN 'capture.applied' ELSE 'capture.denied' END
          INTO phase FROM work.capture_intents WHERE workspace_id=NEW.workspace_id AND id=NEW.capture_id;
        IF phase IS NULL OR NEW.event_type<>phase THEN
          RAISE EXCEPTION 'Capture audit phase denied' USING ERRCODE='23514';
        END IF;
        NEW.database_initiator:=current_user;
        NEW.occurred_at:=clock_timestamp();
        RETURN NEW;
      END; $$;
      CREATE TRIGGER capture_audit_guard BEFORE INSERT ON work.capture_audit
        FOR EACH ROW EXECUTE FUNCTION work.guard_capture_audit();
      CREATE TRIGGER capture_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON work.capture_audit
        FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation();
      REVOKE ALL ON FUNCTION work.guard_capture(),work.audit_capture(),work.guard_capture_audit() FROM PUBLIC;
    """)
    bind = op.get_bind()
    quoted = bind.dialect.identifier_preparer.quote(bind.scalar(sa.text("SELECT current_user")))
    for table in ("capture_intents", "capture_audit"):
        op.execute(f"ALTER TABLE work.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE work.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON work.{table} FROM PUBLIC")
        op.execute(
            f"CREATE POLICY workspace_access ON work.{table} USING(workspace_id IN (SELECT id FROM work.active_workspace))"
        )
        op.execute(
            f"CREATE POLICY operator_access ON work.{table} TO {quoted} USING(true) WITH CHECK(true)"
        )


def downgrade():
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SELECT pg_advisory_xact_lock(1508310,1)")
    op.execute("DROP TABLE work.capture_audit")
    op.execute("DROP TABLE work.capture_intents")
    op.execute("DROP FUNCTION work.guard_capture_audit()")
    op.execute("DROP FUNCTION work.audit_capture()")
    op.execute("DROP FUNCTION work.guard_capture()")
