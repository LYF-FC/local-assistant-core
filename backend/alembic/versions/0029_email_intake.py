"""Creator-only offline email originals and terminal replay tombstones."""

from alembic import op

revision = "0029_email_intake"
down_revision = "0028_invoice_review"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE public.email_envelopes (
 document_id uuid PRIMARY KEY REFERENCES public.document_records(id),
 owner_id uuid NOT NULL REFERENCES public.users(id), scope_key varchar(96) NOT NULL,
 state varchar(16) NOT NULL, message_sha256 varchar(64) NOT NULL, message_size integer NOT NULL,
 attachment_sha256 varchar(64), attachment_filename varchar(120), original_message bytea,
 created_at timestamptz NOT NULL, forgotten_at timestamptz,
 CONSTRAINT uq_email_message UNIQUE(owner_id,scope_key,message_sha256),
 CONSTRAINT ck_email_scope CHECK(scope_key IN ('household_shared','member_a_private','member_b_private')),
 CONSTRAINT ck_email_size CHECK(message_size BETWEEN 1 AND 262144),
 CONSTRAINT ck_email_content CHECK((state='active' AND original_message IS NOT NULL AND length(original_message)=message_size AND attachment_filename IS NOT NULL AND attachment_sha256 IS NOT NULL AND forgotten_at IS NULL) OR (state='forgotten' AND original_message IS NULL AND attachment_filename IS NULL AND attachment_sha256 IS NULL AND forgotten_at IS NOT NULL))
);
CREATE FUNCTION public.butler_seal_email() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE source public.document_records;
BEGIN
 IF TG_OP IN ('DELETE','TRUNCATE') THEN RAISE EXCEPTION 'Email original is sealed' USING ERRCODE='23514'; END IF;
 SELECT * INTO source FROM public.document_records WHERE id=NEW.document_id;
 IF source.id IS NULL OR NEW.owner_id<>source.owner_id OR NEW.scope_key<>source.scope_key THEN
  RAISE EXCEPTION 'Email source identity mismatch' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
  IF source.state<>'active' OR source.revision<>1 OR NEW.state<>'active' OR NEW.created_at<>source.created_at
   OR NEW.attachment_sha256<>source.sha256 OR NEW.attachment_filename<>source.filename
   OR NEW.message_sha256 IS DISTINCT FROM encode(sha256(NEW.original_message),'hex') THEN
   RAISE EXCEPTION 'Invalid initial email original' USING ERRCODE='23514'; END IF;
 ELSE
  IF OLD.state<>'active' OR NEW.state<>'forgotten' OR source.state<>'forgotten'
   OR ROW(NEW.document_id,NEW.owner_id,NEW.scope_key,NEW.message_sha256,NEW.message_size,NEW.created_at)
      IS DISTINCT FROM ROW(OLD.document_id,OLD.owner_id,OLD.scope_key,OLD.message_sha256,OLD.message_size,OLD.created_at)
   OR NEW.original_message IS NOT NULL OR NEW.attachment_filename IS NOT NULL OR NEW.attachment_sha256 IS NOT NULL
   OR NEW.forgotten_at IS NULL OR NEW.forgotten_at<NEW.created_at THEN
   RAISE EXCEPTION 'Email may only be scrubbed with its source' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER butler_email_guard BEFORE INSERT OR UPDATE OR DELETE ON public.email_envelopes FOR EACH ROW EXECUTE FUNCTION public.butler_seal_email();
CREATE TRIGGER butler_email_truncate BEFORE TRUNCATE ON public.email_envelopes FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_email();
""")


def downgrade():
    op.drop_table("email_envelopes")
    op.execute("DROP FUNCTION public.butler_seal_email()")
