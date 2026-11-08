"""Owner-only forgetting reconciliation on quarantined synthetic restores.

Revision ID: 0017_work_suppression
Revises: 0016_work_retention
"""

import sqlalchemy as sa

from alembic import op

revision = "0017_work_suppression"
down_revision = "0016_work_retention"
branch_labels = None
depends_on = None


def _old(table):
    return f"""IF NOT (EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=NEW.workspace_id AND is_active AND slug LIKE 'synthetic-%')
          OR (TG_OP='UPDATE' AND NEW.state='forgotten' AND OLD.retain_until<=clock_timestamp()
            AND current_setting('butler.retention_cleanup',true)='expired' AND session_user=current_user
            AND current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.{table}'::regclass)
            AND EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=NEW.workspace_id AND NOT is_active AND slug LIKE 'synthetic-%'))) THEN"""


def _new(table):
    expression = _old(table).removeprefix("IF NOT (").removesuffix(") THEN")
    return (
        "IF NOT COALESCE(("
        + expression
        + " OR (TG_OP='UPDATE' AND NEW.state='forgotten' AND work.restore_suppression_allowed(NEW.workspace_id))),false) THEN"
    )


OLD_BARRIER = "IF current_setting('butler.retention_cleanup',true)='expired' THEN"
NEW_BARRIER = "IF current_setting('butler.retention_cleanup',true)='expired' OR current_setting('butler.restore_suppression',true)='reviewed' THEN"


def _patch(function, old, new):
    definition = op.get_bind().scalar(
        sa.text("SELECT pg_get_functiondef(to_regprocedure(:name))"), {"name": function + "()"}
    )
    if definition is None or definition.count(old) != 1:
        raise RuntimeError("Expected one reviewed suppression guard fragment")
    op.execute(definition.replace(old, new))


def upgrade():
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SELECT pg_advisory_xact_lock(1508310,1)")
    op.execute("""
      CREATE FUNCTION work.restore_suppression_allowed(workspace uuid) RETURNS boolean
      LANGUAGE sql STABLE SET search_path=pg_catalog AS $$
        SELECT COALESCE(session_user=current_user
          AND current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.drafts'::regclass)
          AND current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.parties'::regclass)
          AND current_setting('butler.restore_suppression',true)='reviewed'
          AND current_setting('transaction_isolation')='read committed'
          AND EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=workspace AND NOT is_active AND slug LIKE 'synthetic-%')
          AND NOT EXISTS(SELECT 1 FROM public.work_access_grants WHERE workspace_id=workspace),false);
      $$;
      REVOKE ALL ON FUNCTION work.restore_suppression_allowed(uuid) FROM PUBLIC;
    """)
    _patch("work.guard_draft", _old("drafts"), _new("drafts"))
    _patch("work.guard_party", _old("parties"), _new("parties"))
    _patch("work.draft_write_barrier", OLD_BARRIER, NEW_BARRIER)


def downgrade():
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SELECT pg_advisory_xact_lock(1508310,1)")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM public.audit_events WHERE event_type='admin.work_suppression_applied')"
        )
    ):
        raise RuntimeError("Suppression reconciliation evidence exists; use reviewed recovery")
    _patch("work.draft_write_barrier", NEW_BARRIER, OLD_BARRIER)
    _patch("work.guard_party", _new("parties"), _old("parties"))
    _patch("work.guard_draft", _new("drafts"), _old("drafts"))
    op.execute("DROP FUNCTION work.restore_suppression_allowed(uuid)")
