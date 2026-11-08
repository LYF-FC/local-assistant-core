"""Seal approval context and protect audit history through normal SQL.

Revision ID: 0003_audit_approvals
Revises: 0002_identity
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_audit_approvals"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("payload_hash", sa.String(64), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    ]:
        op.add_column("approvals", column)
    # Nullable fields deliberately leave legacy rows unbound and unusable for authorization.
    op.execute("""
    CREATE FUNCTION public.butler_deny_audit_mutation() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
    BEGIN
      RAISE EXCEPTION 'Audit history is append-only' USING ERRCODE = '42501';
    END; $$;
    CREATE TRIGGER butler_audit_row_guard BEFORE UPDATE OR DELETE ON public.audit_events
      FOR EACH ROW EXECUTE FUNCTION public.butler_deny_audit_mutation();
    CREATE TRIGGER butler_audit_truncate_guard BEFORE TRUNCATE ON public.audit_events
      FOR EACH STATEMENT EXECUTE FUNCTION public.butler_deny_audit_mutation();
    CREATE FUNCTION public.butler_seal_approval() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
    BEGIN
      IF TG_OP = 'INSERT' THEN
        IF NEW.payload_hash IS NULL OR NEW.policy_version IS NULL OR NEW.expires_at IS NULL
           OR NEW.status <> 'pending' OR NEW.approved_by IS NOT NULL
           OR NEW.resolved_at IS NOT NULL OR NEW.consumed_at IS NOT NULL
           OR NEW.expires_at <= NEW.requested_at THEN
          RAISE EXCEPTION 'Approval must start bound and pending' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
      END IF;
      IF ROW(NEW.id, NEW.task_id, NEW.scope_key, NEW.action_type, NEW.requested_by,
             NEW.request_payload, NEW.requested_at, NEW.payload_hash, NEW.policy_version, NEW.expires_at)
         IS DISTINCT FROM
         ROW(OLD.id, OLD.task_id, OLD.scope_key, OLD.action_type, OLD.requested_by,
             OLD.request_payload, OLD.requested_at, OLD.payload_hash, OLD.policy_version, OLD.expires_at) THEN
        RAISE EXCEPTION 'Approval context is sealed' USING ERRCODE = '23514';
      END IF;
      IF NEW.status = OLD.status THEN
        IF ROW(NEW.approved_by, NEW.resolved_at, NEW.consumed_at)
           IS DISTINCT FROM ROW(OLD.approved_by, OLD.resolved_at, OLD.consumed_at) THEN
          RAISE EXCEPTION 'Approval decision cannot be rewritten' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
      END IF;
      IF OLD.payload_hash IS NULL OR OLD.policy_version IS NULL OR OLD.expires_at IS NULL THEN
        RAISE EXCEPTION 'Legacy approval is unbound' USING ERRCODE = '23514';
      END IF;
      IF OLD.status = 'pending' AND NEW.status IN ('approved','rejected','cancelled','expired')
         AND NEW.resolved_at IS NOT NULL AND NEW.consumed_at IS NULL
         AND ((NEW.status = 'approved' AND NEW.approved_by IS NOT NULL)
              OR (NEW.status <> 'approved' AND NEW.approved_by IS NULL)) THEN
        RETURN NEW;
      END IF;
      IF OLD.status = 'approved' AND NEW.status IN ('consumed','cancelled','expired')
         AND NEW.approved_by IS NOT DISTINCT FROM OLD.approved_by
         AND NEW.resolved_at IS NOT DISTINCT FROM OLD.resolved_at
         AND ((NEW.status = 'consumed' AND NEW.consumed_at IS NOT NULL)
              OR (NEW.status <> 'consumed' AND NEW.consumed_at IS NULL)) THEN
        RETURN NEW;
      END IF;
      RAISE EXCEPTION 'Invalid approval transition' USING ERRCODE = '23514';
    END; $$;
    CREATE TRIGGER butler_approval_guard BEFORE INSERT OR UPDATE ON public.approvals
      FOR EACH ROW EXECUTE FUNCTION public.butler_seal_approval();
    """)


def downgrade():
    op.execute("DROP TRIGGER butler_approval_guard ON public.approvals")
    op.execute("DROP FUNCTION public.butler_seal_approval()")
    op.execute("DROP TRIGGER butler_audit_row_guard ON public.audit_events")
    op.execute("DROP TRIGGER butler_audit_truncate_guard ON public.audit_events")
    op.execute("DROP FUNCTION public.butler_deny_audit_mutation()")
    for name in ("consumed_at", "expires_at", "policy_version", "payload_hash"):
        op.drop_column("approvals", name)
