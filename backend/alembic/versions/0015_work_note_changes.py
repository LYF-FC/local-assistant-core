"""Revision-bound synthetic corrections and privacy-preserving forget intent.

Revision ID: 0015_work_note_changes
Revises: 0014_work_capture
"""

import sqlalchemy as sa

from alembic import op

revision = "0015_work_note_changes"
down_revision = "0014_work_capture"
branch_labels = None
depends_on = None


def _drop_check(fragment):
    bind = op.get_bind()
    names = (
        bind.execute(
            sa.text(
                "SELECT conname FROM pg_constraint WHERE conrelid='work.capture_intents'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE :pattern"
            ),
            {"pattern": "%" + fragment + "%"},
        )
        .scalars()
        .all()
    )
    if len(names) != 1:
        raise RuntimeError("Expected one existing private intent constraint")
    quoted = bind.dialect.identifier_preparer.quote(names[0])
    op.execute(f"ALTER TABLE work.capture_intents DROP CONSTRAINT {quoted}")


def _guard(changes):
    mutable = "'payload','payload_hash','state','record_id','reason_code','finished_at'"
    if changes:
        mutable += ",'result_revision'"
    application = (
        """
        IF NEW.state='applied' THEN
          IF NEW.intent='capture_draft' THEN NEW.result_revision:=1;
          ELSE
            NEW.result_revision:=OLD.expected_revision+1;
            IF NOT EXISTS(SELECT 1 FROM work.drafts WHERE workspace_id=NEW.workspace_id
              AND id=NEW.target_record_id AND id=NEW.record_id AND revision=NEW.result_revision
              AND state=CASE WHEN NEW.intent='forget_note' THEN 'forgotten' ELSE 'draft' END) THEN
              RAISE EXCEPTION 'Note outcome mismatch' USING ERRCODE='23514';
            END IF;
          END IF;
        ELSE NEW.result_revision:=NULL;
        END IF;
    """
        if changes
        else ""
    )
    op.execute(f"""
      CREATE OR REPLACE FUNCTION work.guard_capture() RETURNS trigger
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
            OR (to_jsonb(NEW)-ARRAY[{mutable}]) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY[{mutable}]) THEN
            RAISE EXCEPTION 'Capture outcome denied' USING ERRCODE='23514';
          END IF;
          NEW.finished_at:=event_time;
        END IF;
        {application}
        NEW.payload_hash:=CASE WHEN NEW.payload IS NULL THEN NULL ELSE encode(sha256(convert_to(NEW.payload::text,'UTF8')),'hex') END;
        RETURN NEW;
      END; $$;
    """)


def upgrade():
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SELECT pg_advisory_xact_lock(1508310,1)")
    _drop_check("jsonb_typeof(payload)")
    _drop_check("'authority'")
    op.execute("""
      ALTER TABLE work.capture_intents
        ADD COLUMN intent text NOT NULL DEFAULT 'capture_draft' CHECK(intent IN ('capture_draft','correct_note','forget_note')),
        ADD COLUMN target_record_id uuid NULL,
        ADD COLUMN expected_revision smallint NULL,
        ADD COLUMN result_revision smallint NULL CHECK(result_revision BETWEEN 1 AND 101),
        ADD FOREIGN KEY(workspace_id,target_record_id) REFERENCES work.drafts(workspace_id,id),
        ADD CONSTRAINT note_intent_target CHECK(
          (intent='capture_draft' AND target_record_id IS NULL AND expected_revision IS NULL) OR
          (intent IN ('correct_note','forget_note') AND target_record_id IS NOT NULL AND expected_revision IS NOT NULL AND expected_revision BETWEEN 1 AND 100)),
        ADD CONSTRAINT note_intent_outcome CHECK(intent='capture_draft' OR
          (state='applied' AND record_id=target_record_id AND result_revision IS NOT NULL AND result_revision=expected_revision+1) OR
          (state<>'applied' AND result_revision IS NULL)),
        ADD CONSTRAINT note_intent_reason CHECK(reason_code IN ('authority','expired','evidence','stale','forgotten')),
        ADD CONSTRAINT note_intent_payload CHECK(payload IS NULL OR
          (intent='forget_note' AND payload=jsonb_build_object('forget',true)) OR
          (intent IN ('capture_draft','correct_note') AND jsonb_typeof(payload)='object'
            AND jsonb_typeof(payload->'draft')='object'
            AND (payload->'draft'->>'marker' ~ '^synthetic:[a-zA-Z0-9 _.-]+$') IS TRUE
            AND octet_length(payload->'draft'->>'marker') BETWEEN 11 AND 256
            AND octet_length(payload::text)<=8192));
      CREATE VIEW work.note_metadata WITH (security_barrier=true) AS
        SELECT workspace_id,id,revision,state,retain_until FROM work.drafts
        WHERE workspace_id IN (SELECT id FROM work.active_workspace);
      REVOKE ALL ON work.note_metadata FROM PUBLIC;
      CREATE FUNCTION work.scrub_note_change_intents() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      BEGIN
        UPDATE work.capture_intents SET state='denied',reason_code='forgotten',payload=NULL,finished_at=clock_timestamp()
          WHERE workspace_id=NEW.workspace_id AND target_record_id=NEW.id AND intent='correct_note' AND state='pending';
        RETURN NEW;
      END; $$;
      CREATE TRIGGER scrub_note_change_intents AFTER UPDATE ON work.drafts
        FOR EACH ROW WHEN(NEW.state='forgotten') EXECUTE FUNCTION work.scrub_note_change_intents();
      REVOKE ALL ON FUNCTION work.scrub_note_change_intents() FROM PUBLIC;
    """)
    _guard(True)


def downgrade():
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SELECT pg_advisory_xact_lock(1508310,1)")
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM work.capture_intents WHERE intent<>'capture_draft')")
    ):
        raise RuntimeError(
            "Note-change evidence exists; use reviewed recovery/reconciliation before downgrade"
        )
    op.execute("DROP TRIGGER scrub_note_change_intents ON work.drafts")
    op.execute("DROP FUNCTION work.scrub_note_change_intents()")
    op.execute("DROP VIEW work.note_metadata")
    _guard(False)
    op.execute("""
      ALTER TABLE work.capture_intents DROP CONSTRAINT note_intent_target,
        DROP CONSTRAINT note_intent_outcome, DROP CONSTRAINT note_intent_reason, DROP CONSTRAINT note_intent_payload,
        DROP COLUMN intent,DROP COLUMN target_record_id,DROP COLUMN expected_revision,DROP COLUMN result_revision;
      ALTER TABLE work.capture_intents ADD CHECK(reason_code IN ('authority','expired','evidence','stale'));
      ALTER TABLE work.capture_intents ADD CHECK(payload IS NULL OR (jsonb_typeof(payload)='object' AND jsonb_typeof(payload->'draft')='object'
        AND (payload->'draft'->>'marker' ~ '^synthetic:[a-zA-Z0-9 _.-]+$') IS TRUE
        AND octet_length(payload->'draft'->>'marker') BETWEEN 11 AND 256 AND octet_length(payload::text)<=8192));
    """)
