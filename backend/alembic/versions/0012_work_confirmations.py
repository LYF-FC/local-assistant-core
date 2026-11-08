"""Metadata-only confirmation requests and private one-time consumption.

Revision ID: 0012_work_confirmations
Revises: 0011_work_reviews
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_work_confirmations"
down_revision = "0011_work_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE TABLE public.work_confirmation_requests (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        workspace_id uuid NOT NULL, record_id uuid NOT NULL,
        review_preparation_id uuid NOT NULL, reviewed_revision smallint NOT NULL CHECK(reviewed_revision BETWEEN 1 AND 99),
        actor_id uuid NOT NULL, session_id uuid NOT NULL, request_id uuid NOT NULL,
        created_at timestamptz NOT NULL DEFAULT statement_timestamp(), expires_at timestamptz NOT NULL,
        state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','applied','denied')),
        applied_revision smallint NULL, reason_code text NULL CHECK(reason_code IN ('authority','expired','evidence','stale')),
        finished_at timestamptz NULL,
        UNIQUE(workspace_id,actor_id,session_id,request_id),
        UNIQUE(workspace_id,review_preparation_id),
        CHECK(expires_at>created_at AND expires_at<=created_at+interval '5 minutes'),
        CHECK((state='pending' AND finished_at IS NULL AND applied_revision IS NULL AND reason_code IS NULL)
          OR (state='applied' AND finished_at IS NOT NULL AND applied_revision IS NOT NULL AND applied_revision=reviewed_revision+1 AND reason_code IS NULL)
          OR (state='denied' AND finished_at IS NOT NULL AND applied_revision IS NULL AND reason_code IS NOT NULL))
      );
      REVOKE ALL ON public.work_confirmation_requests FROM PUBLIC;
      CREATE FUNCTION public.guard_work_confirmation_request() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
      BEGIN
        IF TG_OP='INSERT' THEN
          IF NEW.state<>'pending' THEN RAISE EXCEPTION 'Pending request required' USING ERRCODE='23514'; END IF;
        ELSE
          IF OLD.state<>'pending' OR NEW.state='pending'
            OR (to_jsonb(NEW)-ARRAY['state','applied_revision','reason_code','finished_at'])
              IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','applied_revision','reason_code','finished_at']) THEN
            RAISE EXCEPTION 'Request mutation denied' USING ERRCODE='23514';
          END IF;
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER work_confirmation_guard BEFORE INSERT OR UPDATE ON public.work_confirmation_requests
        FOR EACH ROW EXECUTE FUNCTION public.guard_work_confirmation_request();
      CREATE TRIGGER work_confirmation_no_delete BEFORE DELETE OR TRUNCATE ON public.work_confirmation_requests
        FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation();
      REVOKE ALL ON FUNCTION public.guard_work_confirmation_request() FROM PUBLIC;

      CREATE TABLE work.draft_confirmations (
        workspace_id uuid NOT NULL, request_id uuid NOT NULL REFERENCES public.work_confirmation_requests(id),
        review_preparation_id uuid NOT NULL, record_id uuid NOT NULL,
        reviewed_revision smallint NOT NULL CHECK(reviewed_revision BETWEEN 1 AND 99),
        confirmed_revision smallint NOT NULL CHECK(confirmed_revision=reviewed_revision+1),
        actor_id uuid NOT NULL, session_id uuid NOT NULL,
        confirmed_at timestamptz NOT NULL DEFAULT statement_timestamp(),
        PRIMARY KEY(workspace_id,request_id), UNIQUE(workspace_id,review_preparation_id),
        FOREIGN KEY(workspace_id,review_preparation_id) REFERENCES work.draft_reviews(workspace_id,id),
        FOREIGN KEY(workspace_id,record_id) REFERENCES work.drafts(workspace_id,id)
      );
      ALTER TABLE work.draft_confirmations ENABLE ROW LEVEL SECURITY;
      ALTER TABLE work.draft_confirmations FORCE ROW LEVEL SECURITY;
      REVOKE ALL ON work.draft_confirmations FROM PUBLIC;
      CREATE TRIGGER draft_confirmation_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON work.draft_confirmations
        FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation();
    """)
    owner = op.get_bind().scalar(sa.text("SELECT current_user"))
    quoted = op.get_bind().dialect.identifier_preparer.quote(owner)
    op.execute(
        f"CREATE POLICY operator_access ON work.draft_confirmations TO {quoted} USING(true) WITH CHECK(true)"
    )


def downgrade():
    # Explicit operator rollback only: disable requests/worker and back up first.
    op.execute("DROP TABLE work.draft_confirmations")
    op.execute("DROP TABLE public.work_confirmation_requests")
    op.execute("DROP FUNCTION public.guard_work_confirmation_request()")
