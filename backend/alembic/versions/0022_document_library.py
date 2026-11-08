"""Bounded development document library, exact originals and sealed versions."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0022_document_library"
down_revision = "0021_task_reminders"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_records",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, primary_key=False
        ),
        sa.Column("scope_key", sa.String(length=96), nullable=False, primary_key=False),
        sa.Column("state", sa.String(length=16), nullable=False, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("title", sa.String(length=160), nullable=True, primary_key=False),
        sa.Column("filename", sa.String(length=120), nullable=True, primary_key=False),
        sa.Column("source_reference", sa.String(length=512), nullable=True, primary_key=False),
        sa.Column("content_text", sa.Text(), nullable=True, primary_key=False),
        sa.Column("sha256", sa.String(length=64), nullable=True, primary_key=False),
        sa.Column("byte_size", sa.Integer(), nullable=True, primary_key=False),
        sa.Column("reviewed", sa.Boolean(), nullable=True, primary_key=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint(
            "(state='active' AND title IS NOT NULL AND length(trim(title)) BETWEEN 1 AND 160 AND filename IS NOT NULL AND source_reference IS NOT NULL AND length(trim(source_reference)) BETWEEN 1 AND 512 AND content_text IS NOT NULL AND length(content_text) BETWEEN 1 AND 32000 AND sha256 IS NOT NULL AND length(sha256)=64 AND byte_size IS NOT NULL AND byte_size BETWEEN 1 AND 131072 AND reviewed IS NOT NULL) OR (state='forgotten' AND title IS NULL AND filename IS NULL AND source_reference IS NULL AND content_text IS NULL AND sha256 IS NULL AND byte_size IS NULL AND reviewed IS NULL)",
            name="ck_document_content",
        ),
        sa.CheckConstraint("revision>=1", name="ck_document_revision"),
        sa.CheckConstraint(
            "scope_key IN ('household_shared','member_a_private','member_b_private')",
            name="ck_document_scope",
        ),
        sa.CheckConstraint("state IN ('active','forgotten')", name="ck_document_state"),
    )
    op.create_index("ix_document_scope_owner", "document_records", ["scope_key", "owner_id", "id"])
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("document_records.id"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, primary_key=False
        ),
        sa.Column("operation", sa.String(length=16), nullable=False, primary_key=False),
        sa.Column(
            "snapshot", postgresql.JSONB(none_as_null=True), nullable=True, primary_key=False
        ),
        sa.Column("original_bytes", sa.LargeBinary(), nullable=True, primary_key=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint(
            "operation IN ('uploaded','corrected','replaced','forgotten')",
            name="ck_document_operation",
        ),
        sa.CheckConstraint(
            "(snapshot IS NULL AND original_bytes IS NULL) OR (snapshot IS NOT NULL AND original_bytes IS NOT NULL)",
            name="ck_document_version_content",
        ),
        sa.CheckConstraint("revision>=1", name="ck_document_version_revision"),
        sa.UniqueConstraint("document_id", "revision", name="uq_document_version"),
    )
    op.execute("""
      CREATE FUNCTION public.butler_seal_document() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      BEGIN
        IF TG_OP IN ('DELETE','TRUNCATE') THEN
          RAISE EXCEPTION 'Document deletion is sealed' USING ERRCODE='23514';
        END IF;
        IF TG_OP='INSERT' THEN
          IF NEW.revision<>1 OR NEW.state<>'active' OR NEW.reviewed IS DISTINCT FROM false
            OR NEW.created_at<>NEW.updated_at THEN
            RAISE EXCEPTION 'Document must start unreviewed' USING ERRCODE='23514';
          END IF;
        ELSE
          IF ROW(NEW.id,NEW.owner_id,NEW.scope_key,NEW.created_at)
            IS DISTINCT FROM ROW(OLD.id,OLD.owner_id,OLD.scope_key,OLD.created_at)
            OR OLD.state='forgotten' OR NEW.revision<>OLD.revision+1
            OR NEW.updated_at<OLD.updated_at THEN
            RAISE EXCEPTION 'Document identity or revision is sealed' USING ERRCODE='23514';
          END IF;
          IF NEW.state='active' AND ROW(NEW.filename,NEW.content_text,NEW.sha256,NEW.byte_size)
            IS DISTINCT FROM ROW(OLD.filename,OLD.content_text,OLD.sha256,OLD.byte_size)
            AND (NEW.reviewed IS DISTINCT FROM false OR ROW(NEW.title,NEW.source_reference)
              IS DISTINCT FROM ROW(OLD.title,OLD.source_reference)) THEN
            RAISE EXCEPTION 'Replacement must reset review' USING ERRCODE='23514';
          END IF;
        END IF;
        IF NEW.state='active' AND (
          NEW.byte_size<>octet_length(convert_to(NEW.content_text,'UTF8'))
          OR NEW.sha256<>encode(sha256(convert_to(NEW.content_text,'UTF8')),'hex')
          OR NEW.filename !~* '[.](txt|md)$' OR position('/' in NEW.filename)>0
          OR position(chr(92) in NEW.filename)>0 OR NEW.filename ~ '[[:cntrl:]]'
          OR length(NEW.filename)>120) THEN
          RAISE EXCEPTION 'Document original provenance is invalid' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER butler_document_guard BEFORE INSERT OR UPDATE OR DELETE ON public.document_records
        FOR EACH ROW EXECUTE FUNCTION public.butler_seal_document();
      CREATE TRIGGER butler_document_truncate_guard BEFORE TRUNCATE ON public.document_records
        FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_document();
      CREATE FUNCTION public.butler_seal_document_version() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      DECLARE parent public.document_records;
      BEGIN
        IF TG_OP='INSERT' THEN
          SELECT * INTO parent FROM public.document_records WHERE id=NEW.document_id;
          IF parent.id IS NULL OR NEW.actor_id<>parent.owner_id OR NEW.revision<>parent.revision
            OR NEW.created_at<>parent.updated_at
            OR ((parent.state='forgotten') IS DISTINCT FROM (NEW.snapshot IS NULL))
            OR ((parent.state='forgotten') IS DISTINCT FROM (NEW.original_bytes IS NULL))
            OR ((NEW.operation='forgotten') IS DISTINCT FROM (parent.state='forgotten'))
            OR (NEW.revision=1 AND NEW.operation<>'uploaded')
            OR (NEW.revision>1 AND NEW.operation='uploaded') THEN
            RAISE EXCEPTION 'Document version does not match parent' USING ERRCODE='23514';
          END IF;
          IF parent.state='active' AND (
            NEW.snapshot IS DISTINCT FROM jsonb_build_object(
              'id',parent.id::text,'owner_id',parent.owner_id::text,'scope',parent.scope_key,
              'state',parent.state,'revision',parent.revision,'title',parent.title,
              'filename',parent.filename,'source_reference',parent.source_reference,
              'content_text',parent.content_text,'sha256',parent.sha256,'byte_size',parent.byte_size,
              'reviewed',parent.reviewed,'text_origin','original_utf8',
              'line_count',array_length(string_to_array(parent.content_text,E'\n'),1),
              'created_at',NEW.snapshot->>'created_at','updated_at',NEW.snapshot->>'updated_at')
            OR (NEW.snapshot->>'created_at')::timestamptz IS DISTINCT FROM parent.created_at
            OR (NEW.snapshot->>'updated_at')::timestamptz IS DISTINCT FROM parent.updated_at
            OR NEW.original_bytes IS DISTINCT FROM convert_to(parent.content_text,'UTF8')
          ) THEN
            RAISE EXCEPTION 'Document snapshot provenance is sealed' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END IF;
        IF TG_OP='UPDATE' THEN
          IF ROW(NEW.id,NEW.document_id,NEW.revision,NEW.actor_id,NEW.operation,NEW.created_at)
            IS NOT DISTINCT FROM ROW(OLD.id,OLD.document_id,OLD.revision,OLD.actor_id,OLD.operation,OLD.created_at)
            AND NEW.snapshot IS NULL AND NEW.original_bytes IS NULL
            AND EXISTS(SELECT 1 FROM public.document_records WHERE id=OLD.document_id AND state='forgotten') THEN
            RETURN NEW;
          END IF;
        END IF;
        RAISE EXCEPTION 'Document versions are sealed' USING ERRCODE='23514';
      END; $$;
      CREATE TRIGGER butler_document_version_guard BEFORE INSERT OR UPDATE OR DELETE ON public.document_versions
        FOR EACH ROW EXECUTE FUNCTION public.butler_seal_document_version();
      CREATE TRIGGER butler_document_version_truncate_guard BEFORE TRUNCATE ON public.document_versions
        FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_document_version();
    """)


def downgrade():
    op.drop_table("document_versions")
    op.execute("DROP FUNCTION public.butler_seal_document_version()")
    op.drop_table("document_records")
    op.execute("DROP FUNCTION public.butler_seal_document()")
