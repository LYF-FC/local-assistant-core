"""Owner-only expiry cleanup while a synthetic workspace is disabled.

Revision ID: 0016_work_retention
Revises: 0015_work_note_changes
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_work_retention"
down_revision = "0015_work_note_changes"
branch_labels = None
depends_on = None

ACTIVE = "IF NOT EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=NEW.workspace_id AND is_active AND slug LIKE 'synthetic-%') THEN"
REVIEW = "OR NOT EXISTS(SELECT 1 FROM work.drafts WHERE workspace_id=OLD.workspace_id AND id=OLD.record_id AND state='forgotten') THEN"
BARRIER = "PERFORM pg_advisory_xact_lock_shared(1508310,1);"
MAINTENANCE_BARRIER = """IF current_setting('butler.retention_cleanup',true)='expired' THEN
          PERFORM pg_advisory_xact_lock(1508310,1);
        ELSE PERFORM pg_advisory_xact_lock_shared(1508310,1); END IF;"""
EVENTS = "'draft.created','draft.corrected','draft.confirmed','draft.forgotten','draft.read_prepared','draft.review_prepared'"


def _workspace(table):
    return f"""IF NOT (EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=NEW.workspace_id AND is_active AND slug LIKE 'synthetic-%')
          OR (TG_OP='UPDATE' AND NEW.state='forgotten' AND OLD.retain_until<=clock_timestamp()
            AND current_setting('butler.retention_cleanup',true)='expired' AND session_user=current_user
            AND current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.{table}'::regclass)
            AND EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=NEW.workspace_id AND NOT is_active AND slug LIKE 'synthetic-%'))) THEN"""


REVIEW_MAINTENANCE = """OR NOT (EXISTS(SELECT 1 FROM work.drafts WHERE workspace_id=OLD.workspace_id AND id=OLD.record_id AND state='forgotten')
              OR (OLD.expires_at<=clock_timestamp() AND current_setting('butler.retention_cleanup',true)='expired'
                AND session_user=current_user AND current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.draft_reviews'::regclass)
                AND EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=OLD.workspace_id AND NOT is_active AND slug LIKE 'synthetic-%'))) THEN"""


def _patch(function, old, new):
    definition = op.get_bind().scalar(
        sa.text("SELECT pg_get_functiondef(to_regprocedure(:function))"),
        {"function": function + "()"},
    )
    if definition is None or definition.count(old) != 1:
        raise RuntimeError("Expected one reviewed guard fragment; inspect schema before migration")
    op.execute(definition.replace(old, new))


def upgrade():
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SELECT pg_advisory_xact_lock(1508310,1)")
    _patch("work.guard_draft", ACTIVE, _workspace("drafts"))
    _patch("work.guard_party", ACTIVE, _workspace("parties"))
    _patch("work.draft_write_barrier", BARRIER, MAINTENANCE_BARRIER)
    _patch("work.guard_draft_review", REVIEW, REVIEW_MAINTENANCE)
    op.execute(
        f"ALTER TABLE work.draft_audit DROP CONSTRAINT draft_audit_event_type_check, ADD CONSTRAINT draft_audit_event_type_check CHECK(event_type IN ({EVENTS},'draft.review_expired'))"
    )
    op.execute("""
      CREATE FUNCTION work.review_retention_barrier() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      BEGIN
        IF current_setting('butler.retention_cleanup',true)='expired' THEN
          IF current_setting('transaction_isolation')<>'read committed' THEN
            RAISE EXCEPTION 'Retention isolation denied' USING ERRCODE='23514';
          END IF;
          PERFORM pg_advisory_xact_lock(1508310,1);
        END IF;
        RETURN NULL;
      END; $$;
      CREATE TRIGGER draft_review_retention_barrier BEFORE UPDATE ON work.draft_reviews
        FOR EACH STATEMENT EXECUTE FUNCTION work.review_retention_barrier();
      REVOKE ALL ON FUNCTION work.review_retention_barrier() FROM PUBLIC;
    """)


def downgrade():
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SELECT pg_advisory_xact_lock(1508310,1)")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM work.draft_audit WHERE event_type='draft.review_expired') OR EXISTS(SELECT 1 FROM public.audit_events WHERE event_type='admin.work_retention_applied')"
        )
    ):
        raise RuntimeError("Retention evidence exists; use reviewed recovery before downgrade")
    op.execute("DROP TRIGGER draft_review_retention_barrier ON work.draft_reviews")
    op.execute("DROP FUNCTION work.review_retention_barrier()")
    _patch("work.guard_draft_review", REVIEW_MAINTENANCE, REVIEW)
    _patch("work.draft_write_barrier", MAINTENANCE_BARRIER, BARRIER)
    _patch("work.guard_party", _workspace("parties"), ACTIVE)
    _patch("work.guard_draft", _workspace("drafts"), ACTIVE)
    op.execute(
        f"ALTER TABLE work.draft_audit DROP CONSTRAINT draft_audit_event_type_check, ADD CONSTRAINT draft_audit_event_type_check CHECK(event_type IN ({EVENTS}))"
    )
