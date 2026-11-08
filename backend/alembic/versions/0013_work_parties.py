"""Synthetic workspace parties; explicit owners without application writes.

Revision ID: 0013_work_parties
Revises: 0012_work_confirmations
"""

import sqlalchemy as sa

from alembic import op

revision = "0013_work_parties"
down_revision = "0012_work_confirmations"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE TABLE work.parties (
        workspace_id uuid NOT NULL,
        id uuid NOT NULL,
        policy_id uuid NOT NULL,
        revision integer NOT NULL CHECK(revision BETWEEN 1 AND 3),
        state text NOT NULL CHECK(state IN ('active','retired','forgotten')),
        marker text NULL,
        retain_until timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(workspace_id,id),
        FOREIGN KEY(workspace_id,policy_id) REFERENCES work.retention_policies(workspace_id,id),
        CHECK((state='forgotten' AND marker IS NULL) OR
          (state<>'forgotten' AND marker IS NOT NULL AND marker ~ '^synthetic:[a-zA-Z0-9 _.-]+$'
           AND octet_length(marker) BETWEEN 11 AND 256)),
        CHECK(retain_until>created_at AND updated_at>=created_at)
      );
      CREATE TABLE work.party_audit (
        workspace_id uuid NOT NULL,
        id uuid NOT NULL DEFAULT gen_random_uuid(),
        party_id uuid NOT NULL,
        revision integer NOT NULL,
        event_type text NOT NULL CHECK(event_type IN ('party.created','party.retired','party.forgotten')),
        database_initiator text NOT NULL DEFAULT current_user,
        occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(workspace_id,id),
        UNIQUE(workspace_id,party_id,revision),
        FOREIGN KEY(workspace_id,party_id) REFERENCES work.parties(workspace_id,id)
      );
      CREATE TRIGGER party_write_barrier BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE
        ON work.parties FOR EACH STATEMENT EXECUTE FUNCTION public.butler_work_registry_barrier();
      CREATE FUNCTION work.guard_party() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      DECLARE event_time timestamptz; maximum integer;
      BEGIN
        IF TG_OP IN ('DELETE','TRUNCATE') OR current_setting('transaction_isolation')<>'read committed'
          OR session_user<>current_user OR current_user<>(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.parties'::regclass) THEN
          RAISE EXCEPTION 'Party mutation denied' USING ERRCODE='23514';
        END IF;
        event_time:=clock_timestamp();
        IF NOT EXISTS(SELECT 1 FROM public.work_workspaces WHERE id=NEW.workspace_id AND is_active AND slug LIKE 'synthetic-%') THEN
          RAISE EXCEPTION 'Party workspace denied' USING ERRCODE='23514';
        END IF;
        IF TG_OP='INSERT' THEN
          SELECT max_age_seconds INTO maximum FROM work.retention_policies
            WHERE workspace_id=NEW.workspace_id AND id=NEW.policy_id FOR SHARE;
          IF NEW.revision<>1 OR NEW.state<>'active' OR maximum IS NULL
            OR NEW.retain_until<=event_time OR NEW.retain_until>event_time+make_interval(secs=>maximum) THEN
            RAISE EXCEPTION 'Party policy denied' USING ERRCODE='23514';
          END IF;
          NEW.created_at:=event_time;
        ELSE
          IF OLD.state='forgotten' OR NEW.revision<>OLD.revision+1
            OR NEW.workspace_id<>OLD.workspace_id OR NEW.id<>OLD.id OR NEW.policy_id<>OLD.policy_id
            OR NEW.created_at<>OLD.created_at OR NEW.retain_until<>OLD.retain_until
            OR (NEW.state<>'forgotten' AND NEW.marker IS DISTINCT FROM OLD.marker)
            OR NOT ((OLD.state='active' AND NEW.state IN ('retired','forgotten'))
                    OR (OLD.state='retired' AND NEW.state='forgotten')) THEN
            RAISE EXCEPTION 'Party transition denied' USING ERRCODE='23514';
          END IF;
        END IF;
        NEW.updated_at:=event_time;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER party_guard BEFORE INSERT OR UPDATE ON work.parties
        FOR EACH ROW EXECUTE FUNCTION work.guard_party();
      CREATE TRIGGER party_no_delete BEFORE DELETE OR TRUNCATE ON work.parties
        FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation();
      CREATE FUNCTION work.audit_party() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      BEGIN
        INSERT INTO work.party_audit(workspace_id,party_id,revision,event_type)
          VALUES(NEW.workspace_id,NEW.id,NEW.revision,CASE WHEN TG_OP='INSERT' THEN 'party.created'
                 WHEN NEW.state='retired' THEN 'party.retired' ELSE 'party.forgotten' END);
        RETURN NEW;
      END; $$;
      CREATE TRIGGER party_event AFTER INSERT OR UPDATE ON work.parties
        FOR EACH ROW EXECUTE FUNCTION work.audit_party();
      CREATE TRIGGER party_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON work.party_audit
        FOR EACH STATEMENT EXECUTE FUNCTION work.reject_mutation();
      CREATE FUNCTION work.guard_draft_owner() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog,work AS $$
      BEGIN
        IF NEW.state<>'forgotten' AND NEW.snapshot->>'owner_id' IS NOT NULL THEN
          PERFORM id FROM work.parties WHERE workspace_id=NEW.workspace_id
            AND id=(NEW.snapshot->>'owner_id')::uuid AND state='active'
            AND retain_until>clock_timestamp() FOR SHARE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'Active workspace party required' USING ERRCODE='23514';
          END IF;
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER draft_owner_guard BEFORE INSERT OR UPDATE ON work.drafts
        FOR EACH ROW EXECUTE FUNCTION work.guard_draft_owner();
      REVOKE ALL ON FUNCTION work.guard_party(),work.audit_party(),work.guard_draft_owner() FROM PUBLIC;
    """)
    bind = op.get_bind()
    owner = bind.scalar(sa.text("SELECT current_user"))
    quoted = bind.dialect.identifier_preparer.quote(owner)
    for table in ("parties", "party_audit"):
        op.execute(f"ALTER TABLE work.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE work.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON work.{table} FROM PUBLIC")
        op.execute(
            f"CREATE POLICY workspace_access ON work.{table} USING(workspace_id IN (SELECT id FROM work.active_workspace))"
        )
        op.execute(
            f"CREATE POLICY operator_access ON work.{table} TO {quoted} USING(true) WITH CHECK(true)"
        )
    constraints = (
        bind.execute(
            sa.text(
                "SELECT conname FROM pg_constraint WHERE conrelid='work.drafts'::regclass AND contype='c' AND pg_get_expr(conbin,conrelid)=:expression"
            ),
            {"expression": "((snapshot ->> 'owner_id'::text) IS NULL)"},
        )
        .scalars()
        .all()
    )
    if len(constraints) != 1:
        raise RuntimeError("Expected the existing unknown-owner constraint")
    name = bind.dialect.identifier_preparer.quote(constraints[0])
    op.execute(f"ALTER TABLE work.drafts DROP CONSTRAINT {name}")


def downgrade():
    # Fence all note and party writers before inspecting surviving references.
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SELECT pg_advisory_xact_lock(1508310,1)")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM work.drafts WHERE snapshot->>'owner_id' IS NOT NULL UNION ALL SELECT 1 FROM work.draft_revisions WHERE snapshot->>'owner_id' IS NOT NULL)"
        )
    ):
        raise RuntimeError(
            "Forget assigned note histories before party downgrade; verify backup first"
        )
    op.execute(
        "ALTER TABLE work.drafts ADD CONSTRAINT drafts_unknown_owner CHECK(snapshot->>'owner_id' IS NULL)"
    )
    op.execute("DROP TRIGGER draft_owner_guard ON work.drafts")
    op.execute("DROP FUNCTION work.guard_draft_owner()")
    op.execute("DROP TABLE work.party_audit")
    op.execute("DROP TABLE work.parties")
    op.execute("DROP FUNCTION work.audit_party()")
    op.execute("DROP FUNCTION work.guard_party()")
