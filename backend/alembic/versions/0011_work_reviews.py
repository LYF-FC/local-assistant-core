"""Scoped prepared draft review acknowledgements; not a confirmation writer.

Revision ID: 0011_work_reviews
Revises: 0010_work_drafts
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_work_reviews"
down_revision = "0010_work_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      ALTER TABLE work.draft_audit DROP CONSTRAINT draft_audit_event_type_check;
      ALTER TABLE work.draft_audit ADD CONSTRAINT draft_audit_event_type_check CHECK(event_type IN
        ('draft.created','draft.corrected','draft.confirmed','draft.forgotten','draft.read_prepared','draft.review_prepared'));
      CREATE TABLE work.draft_reviews (
        workspace_id uuid NOT NULL, id uuid NOT NULL DEFAULT gen_random_uuid(),
        record_id uuid NOT NULL, revision smallint NOT NULL CHECK(revision BETWEEN 1 AND 100),
        actor_id uuid NOT NULL, session_id uuid NOT NULL, request_id uuid NOT NULL,
        intent text NOT NULL CHECK(intent='confirm_note'),
        payload_hash text NULL CHECK(payload_hash IS NULL OR payload_hash ~ '^[a-f0-9]{64}$'),
        prepared_at timestamptz NOT NULL DEFAULT statement_timestamp(),
        expires_at timestamptz NOT NULL DEFAULT statement_timestamp()+interval '5 minutes',
        PRIMARY KEY(workspace_id,id),
        UNIQUE(workspace_id,actor_id,session_id,request_id),
        FOREIGN KEY(workspace_id,record_id) REFERENCES work.drafts(workspace_id,id),
        CHECK(expires_at>prepared_at)
      );
      ALTER TABLE work.draft_reviews ENABLE ROW LEVEL SECURITY;
      ALTER TABLE work.draft_reviews FORCE ROW LEVEL SECURITY;
      CREATE POLICY workspace_access ON work.draft_reviews
        USING(workspace_id IN (SELECT id FROM work.active_workspace)
          AND (payload_hash IS NULL OR EXISTS(SELECT 1 FROM work.drafts d
            WHERE d.workspace_id=draft_reviews.workspace_id AND d.id=draft_reviews.record_id
              AND d.state='draft' AND d.revision=draft_reviews.revision)))
        WITH CHECK(workspace_id IN (SELECT id FROM work.active_workspace)
          AND EXISTS(SELECT 1 FROM work.drafts d WHERE d.workspace_id=draft_reviews.workspace_id
            AND d.id=draft_reviews.record_id AND d.state='draft' AND d.revision=draft_reviews.revision));
      REVOKE ALL ON work.draft_reviews FROM PUBLIC;

      CREATE FUNCTION work.guard_draft_review() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      DECLARE item work.drafts%ROWTYPE; actual_hash text;
      BEGIN
        IF TG_OP='UPDATE' THEN
          IF OLD.payload_hash IS NULL OR NEW.payload_hash IS NOT NULL
            OR (to_jsonb(NEW)-'payload_hash') IS DISTINCT FROM (to_jsonb(OLD)-'payload_hash')
            OR NOT EXISTS(SELECT 1 FROM work.drafts WHERE workspace_id=OLD.workspace_id AND id=OLD.record_id AND state='forgotten') THEN
            RAISE EXCEPTION 'Review mutation denied' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END IF;
        SELECT * INTO item FROM work.drafts WHERE workspace_id=NEW.workspace_id AND id=NEW.record_id FOR SHARE;
        actual_hash:=encode(sha256(convert_to(item.snapshot::text,'UTF8')),'hex');
        IF item.id IS NULL OR item.state<>'draft' OR item.revision<>NEW.revision
          OR item.retain_until<=clock_timestamp() OR NEW.payload_hash IS DISTINCT FROM actual_hash
          OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(item.snapshot->'source_ids') refs(value)
            WHERE NOT EXISTS(SELECT 1 FROM work.source_registry s WHERE s.workspace_id=NEW.workspace_id AND s.id=refs.value::uuid AND s.is_active))
          OR jsonb_array_length(item.snapshot->'source_ids')=0 THEN
          RAISE EXCEPTION 'Review preparation denied' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER draft_review_guard BEFORE INSERT OR UPDATE ON work.draft_reviews
        FOR EACH ROW EXECUTE FUNCTION work.guard_draft_review();
      CREATE TRIGGER draft_review_no_delete BEFORE DELETE OR TRUNCATE ON work.draft_reviews
        FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation();

      CREATE FUNCTION work.audit_draft_review() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      BEGIN
        INSERT INTO work.draft_audit(workspace_id,record_id,revision,actor_id,event_type)
          VALUES(NEW.workspace_id,NEW.record_id,NEW.revision,NEW.actor_id,'draft.review_prepared');
        RETURN NEW;
      END; $$;
      CREATE TRIGGER draft_review_audit AFTER INSERT ON work.draft_reviews
        FOR EACH ROW EXECUTE FUNCTION work.audit_draft_review();

      CREATE FUNCTION work.scrub_draft_reviews() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      BEGIN
        UPDATE work.draft_reviews SET payload_hash=NULL
          WHERE workspace_id=NEW.workspace_id AND record_id=NEW.id AND payload_hash IS NOT NULL;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER scrub_draft_reviews AFTER UPDATE ON work.drafts
        FOR EACH ROW WHEN (NEW.state='forgotten') EXECUTE FUNCTION work.scrub_draft_reviews();
      REVOKE ALL ON FUNCTION work.guard_draft_review(),work.audit_draft_review(),work.scrub_draft_reviews() FROM PUBLIC;
    """)
    owner = op.get_bind().scalar(sa.text("SELECT current_user"))
    quoted = op.get_bind().dialect.identifier_preparer.quote(owner)
    op.execute(
        f"CREATE POLICY operator_access ON work.draft_reviews TO {quoted} USING(true) WITH CHECK(true)"
    )


def downgrade():
    op.execute("DROP TRIGGER scrub_draft_reviews ON work.drafts")
    op.execute("DROP TABLE work.draft_reviews")
    op.execute("DROP FUNCTION work.scrub_draft_reviews()")
    op.execute("DROP FUNCTION work.audit_draft_review()")
    op.execute("DROP FUNCTION work.guard_draft_review()")
    # Existing metadata-only review audit survives downgrade; do not erase history.
