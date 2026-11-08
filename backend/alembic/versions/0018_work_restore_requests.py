"""Reviewed pending-request and cached-review cleanup after restore.

Revision ID: 0018_work_restore_requests
Revises: 0017_work_suppression
"""

import sqlalchemy as sa

from alembic import op

revision = "0018_work_restore_requests"
down_revision = "0017_work_suppression"
branch_labels = None
depends_on = None

OLD = """OR NOT (EXISTS(SELECT 1 FROM work.drafts WHERE workspace_id=OLD.workspace_id AND id=OLD.record_id AND state='forgotten')
              OR (OLD.expires_at<=clock_timestamp() AND current_setting('butler.retention_cleanup',true)='expired'
                AND session_user=current_user AND current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.draft_reviews'::regclass)
                AND EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=OLD.workspace_id AND NOT is_active AND slug LIKE 'synthetic-%'))) THEN"""
NEW = (
    "OR NOT COALESCE(("
    + OLD.removeprefix("OR NOT (").removesuffix(") THEN")
    + " OR work.restore_requests_allowed(OLD.workspace_id)),false) THEN"
)
OLD_BARRIER = "IF current_setting('butler.retention_cleanup',true)='expired' THEN"
NEW_BARRIER = "IF current_setting('butler.retention_cleanup',true)='expired' OR current_setting('butler.restore_requests',true)='reviewed' THEN"


def _patch(function, old, new):
    definition = op.get_bind().scalar(
        sa.text("SELECT pg_get_functiondef(to_regprocedure(:name))"), {"name": function + "()"}
    )
    if definition.count(old) != 1:
        raise RuntimeError("Expected one reviewed request cleanup guard fragment")
    op.execute(definition.replace(old, new))


def upgrade():
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SELECT pg_advisory_xact_lock(1508310,1)")
    op.execute("""
      CREATE FUNCTION work.restore_requests_allowed(workspace uuid) RETURNS boolean
      LANGUAGE sql STABLE SET search_path=pg_catalog AS $$
        SELECT COALESCE(session_user=current_user
          AND current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.draft_reviews'::regclass)
          AND current_setting('butler.restore_requests',true)='reviewed'
          AND current_setting('transaction_isolation')='read committed'
          AND EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=workspace AND NOT is_active AND slug LIKE 'synthetic-%')
          AND NOT EXISTS(SELECT 1 FROM public.work_access_grants WHERE workspace_id=workspace),false);
      $$;
      REVOKE ALL ON FUNCTION work.restore_requests_allowed(uuid) FROM PUBLIC;
    """)
    _patch("work.guard_draft_review", OLD, NEW)
    _patch("work.review_retention_barrier", OLD_BARRIER, NEW_BARRIER)


def downgrade():
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SELECT pg_advisory_xact_lock(1508310,1)")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM public.audit_events WHERE event_type='admin.work_restore_requests_discarded')"
        )
    ):
        raise RuntimeError("Restore request cleanup evidence exists; use reviewed recovery")
    _patch("work.review_retention_barrier", NEW_BARRIER, OLD_BARRIER)
    _patch("work.guard_draft_review", NEW, OLD)
    op.execute("DROP FUNCTION work.restore_requests_allowed(uuid)")
