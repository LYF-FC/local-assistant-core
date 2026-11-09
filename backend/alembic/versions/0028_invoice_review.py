"""Source-bound invoice field candidates, explicit review and sealed history."""

from alembic import op

revision = "0028_invoice_review"
down_revision = "0027_recurring_routines"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""

CREATE TABLE invoice_reviews (
	document_id UUID NOT NULL,
	owner_id UUID NOT NULL,
	scope_key VARCHAR(96) NOT NULL,
	state VARCHAR(16) NOT NULL,
	revision INTEGER NOT NULL,
	source_revision INTEGER NOT NULL,
	data JSONB,
	issuer_key VARCHAR(512),
	number_key VARCHAR(288),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (document_id),
	CONSTRAINT ck_invoice_revision CHECK (revision BETWEEN 1 AND 101 AND source_revision>=1),
	CONSTRAINT ck_invoice_scope CHECK (scope_key IN ('household_shared','member_a_private','member_b_private')),
	CONSTRAINT ck_invoice_content CHECK ((state IN ('draft','reviewed') AND data IS NOT NULL) OR (state='forgotten' AND data IS NULL AND issuer_key IS NULL AND number_key IS NULL)),
	CONSTRAINT ck_invoice_keys CHECK (state='reviewed' OR (issuer_key IS NULL AND number_key IS NULL)),
	FOREIGN KEY(document_id) REFERENCES document_records (id),
	FOREIGN KEY(owner_id) REFERENCES users (id)
)

;
CREATE INDEX ix_invoice_match ON invoice_reviews (scope_key, issuer_key, number_key, document_id);

CREATE TABLE invoice_revisions (
	id UUID NOT NULL,
	document_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	actor_id UUID NOT NULL,
	snapshot JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_invoice_revision UNIQUE (document_id, revision),
	FOREIGN KEY(document_id) REFERENCES invoice_reviews (document_id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;
CREATE FUNCTION public.butler_seal_invoice() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE source public.document_records;
BEGIN
 IF TG_OP IN ('DELETE','TRUNCATE') THEN RAISE EXCEPTION 'Invoice deletion is sealed' USING ERRCODE='23514'; END IF;
 SELECT * INTO source FROM public.document_records WHERE id=NEW.document_id;
 IF source.id IS NULL OR NEW.owner_id<>source.owner_id OR NEW.scope_key<>source.scope_key THEN
  RAISE EXCEPTION 'Invoice source identity mismatch' USING ERRCODE='23514'; END IF;
 IF NEW.state<>'forgotten' AND (source.state<>'active' OR source.reviewed IS DISTINCT FROM true
    OR NEW.source_revision<>source.revision OR jsonb_typeof(NEW.data) IS DISTINCT FROM 'object'
    OR octet_length(NEW.data::text)>65536 OR (NEW.data->'source'->>'revision')::int IS DISTINCT FROM NEW.source_revision
    OR NEW.data->'source'->>'sha256' IS DISTINCT FROM source.sha256
    OR (NEW.state='draft' AND NEW.data->>'decisions' IS NOT NULL)
    OR (NEW.state='reviewed' AND jsonb_typeof(NEW.data->'decisions') IS DISTINCT FROM 'object')) THEN
  RAISE EXCEPTION 'Invalid current invoice payload' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.revision<>1 OR NEW.state<>'draft' OR NEW.created_at<>NEW.updated_at THEN
   RAISE EXCEPTION 'Invoice must start draft' USING ERRCODE='23514'; END IF;
 ELSE
  IF ROW(NEW.document_id,NEW.owner_id,NEW.scope_key,NEW.created_at) IS DISTINCT FROM ROW(OLD.document_id,OLD.owner_id,OLD.scope_key,OLD.created_at)
    OR OLD.state='forgotten' OR NEW.revision<>OLD.revision+1 OR NEW.updated_at<OLD.updated_at
    OR NEW.source_revision<OLD.source_revision OR (NEW.state<>'forgotten' AND NEW.revision>100) THEN
   RAISE EXCEPTION 'Invoice identity/revision is sealed' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER butler_invoice_guard BEFORE INSERT OR UPDATE OR DELETE ON public.invoice_reviews FOR EACH ROW EXECUTE FUNCTION public.butler_seal_invoice();
CREATE TRIGGER butler_invoice_truncate BEFORE TRUNCATE ON public.invoice_reviews FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_invoice();
CREATE FUNCTION public.butler_seal_invoice_history() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE parent public.invoice_reviews;
BEGIN
 IF TG_OP='INSERT' THEN
  SELECT * INTO parent FROM public.invoice_reviews WHERE document_id=NEW.document_id;
  IF parent.document_id IS NULL OR NEW.actor_id<>parent.owner_id OR NEW.revision<>parent.revision OR NEW.created_at<>parent.updated_at
    OR ((parent.state='forgotten') IS DISTINCT FROM (NEW.snapshot IS NULL)) THEN
   RAISE EXCEPTION 'Invoice history mismatches parent' USING ERRCODE='23514'; END IF;
  IF NEW.snapshot IS NOT NULL AND (NEW.snapshot->>'document_id' IS DISTINCT FROM parent.document_id::text
    OR NEW.snapshot->>'owner_id' IS DISTINCT FROM parent.owner_id::text OR NEW.snapshot->>'scope' IS DISTINCT FROM parent.scope_key
    OR NEW.snapshot->>'state' IS DISTINCT FROM parent.state OR (NEW.snapshot->>'revision')::int IS DISTINCT FROM parent.revision
    OR (NEW.snapshot->>'source_revision')::int IS DISTINCT FROM parent.source_revision OR NEW.snapshot->'data' IS DISTINCT FROM parent.data
    OR (NEW.snapshot->>'created_at')::timestamptz IS DISTINCT FROM parent.created_at OR (NEW.snapshot->>'updated_at')::timestamptz IS DISTINCT FROM parent.updated_at) THEN
   RAISE EXCEPTION 'Invoice snapshot differs from parent' USING ERRCODE='23514'; END IF;
  RETURN NEW;
 ELSIF TG_OP='UPDATE' THEN
  IF ROW(NEW.id,NEW.document_id,NEW.revision,NEW.actor_id,NEW.created_at) IS NOT DISTINCT FROM ROW(OLD.id,OLD.document_id,OLD.revision,OLD.actor_id,OLD.created_at)
    AND NEW.snapshot IS NULL AND EXISTS(SELECT 1 FROM public.invoice_reviews WHERE document_id=OLD.document_id AND state='forgotten') THEN RETURN NEW; END IF;
 END IF;
 RAISE EXCEPTION 'Invoice history is sealed' USING ERRCODE='23514';
END; $$;
CREATE TRIGGER butler_invoice_history_guard BEFORE INSERT OR UPDATE OR DELETE ON public.invoice_revisions FOR EACH ROW EXECUTE FUNCTION public.butler_seal_invoice_history();
CREATE TRIGGER butler_invoice_history_truncate BEFORE TRUNCATE ON public.invoice_revisions FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_invoice_history();

    """)


def downgrade():
    op.drop_table("invoice_revisions")
    op.execute("DROP FUNCTION public.butler_seal_invoice_history()")
    op.drop_table("invoice_reviews")
    op.execute("DROP FUNCTION public.butler_seal_invoice()")
