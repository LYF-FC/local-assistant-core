"""Bounded PDF originals, derived provenance and idempotent capture."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0024_pdf_ingestion"
down_revision = "0023_document_archive"
branch_labels = None
depends_on = None

OLD_CONTENT = "(state='active' AND title IS NOT NULL AND length(trim(title)) BETWEEN 1 AND 160 AND filename IS NOT NULL AND source_reference IS NOT NULL AND length(trim(source_reference)) BETWEEN 1 AND 512 AND content_text IS NOT NULL AND length(content_text) BETWEEN 1 AND 32000 AND sha256 IS NOT NULL AND length(sha256)=64 AND byte_size IS NOT NULL AND byte_size BETWEEN 1 AND 131072 AND reviewed IS NOT NULL) OR (state='forgotten' AND title IS NULL AND filename IS NULL AND source_reference IS NULL AND content_text IS NULL AND sha256 IS NULL AND byte_size IS NULL AND reviewed IS NULL)"
NEW_CONTENT = "(state='active' AND title IS NOT NULL AND length(trim(title)) BETWEEN 1 AND 160 AND filename IS NOT NULL AND source_reference IS NOT NULL AND length(trim(source_reference)) BETWEEN 1 AND 512 AND content_text IS NOT NULL AND length(content_text) BETWEEN 0 AND 32000 AND sha256 IS NOT NULL AND length(sha256)=64 AND byte_size IS NOT NULL AND byte_size BETWEEN 1 AND 131072 AND reviewed IS NOT NULL AND ((extraction_json IS NULL AND length(content_text)>=1) OR (extraction_json IS NOT NULL AND (reviewed=false OR extraction_json ->> 'status'='ready'))) AND ((ingest_key IS NULL AND ingest_hash IS NULL) OR (ingest_key IS NOT NULL AND ingest_hash IS NOT NULL AND length(ingest_hash)=64))) OR (state='forgotten' AND title IS NULL AND filename IS NULL AND source_reference IS NULL AND content_text IS NULL AND sha256 IS NULL AND byte_size IS NULL AND reviewed IS NULL AND extraction_json IS NULL AND ingest_hash IS NULL)"
VALIDATION = r"""
CREATE FUNCTION public.butler_pdf_extraction_valid(info jsonb, content text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $$
DECLARE span jsonb; item jsonb; pages integer; next_line integer:=1; page_no integer:=0; previous integer:=0;
BEGIN
  IF jsonb_typeof(info)<>'object' OR NOT info ?& ARRAY['engine','version','status','pages','page_spans','empty_pages']
    OR info-ARRAY['engine','version','status','pages','page_spans','empty_pages']<>'{}'::jsonb
    OR jsonb_typeof(info->'engine')<>'string' OR info->>'engine'<>'poppler-text-v1' OR jsonb_typeof(info->'version')<>'string'
    OR info->>'version' !~ '^(unavailable|[0-9.]{1,15}([+][a-f0-9]{64})?)$'
    OR info->>'status' NOT IN ('ready','no_text','encrypted','invalid','resource_limit','unavailable')
    OR jsonb_typeof(info->'status')<>'string' OR jsonb_typeof(info->'pages')<>'number'
    OR info->>'pages' !~ '^[0-9]{1,2}$' OR jsonb_typeof(info->'page_spans')<>'array'
    OR jsonb_typeof(info->'empty_pages')<>'array' THEN RETURN false; END IF;
  pages:=(info->>'pages')::integer;
  IF pages>12 OR ((info->>'status'='unavailable') IS DISTINCT FROM (info->>'version'='unavailable')) THEN RETURN false; END IF;
  IF info->>'status'<>'ready' THEN
    RETURN content='' AND info->'page_spans'='[]'::jsonb AND info->'empty_pages'='[]'::jsonb
      AND CASE WHEN info->>'status'='no_text' THEN pages BETWEEN 1 AND 12 ELSE pages=0 END;
  END IF;
  IF pages<1 OR content !~ '\S' OR jsonb_array_length(info->'page_spans')<>pages THEN RETURN false; END IF;
  FOR span IN SELECT value FROM jsonb_array_elements(info->'page_spans') LOOP
    page_no:=page_no+1;
    IF jsonb_typeof(span)<>'object' OR NOT span ?& ARRAY['page','start_line','end_line']
      OR span-ARRAY['page','start_line','end_line']<>'{}'::jsonb
      OR jsonb_typeof(span->'page')<>'number' OR span->>'page' !~ '^[0-9]{1,2}$'
      OR jsonb_typeof(span->'start_line')<>'number' OR span->>'start_line' !~ '^[0-9]{1,5}$'
      OR jsonb_typeof(span->'end_line')<>'number' OR span->>'end_line' !~ '^[0-9]{1,5}$'
      OR (span->>'page')::integer<>page_no OR (span->>'start_line')::integer<>next_line
      OR (span->>'end_line')::integer<next_line THEN RETURN false; END IF;
    next_line:=(span->>'end_line')::integer+1;
  END LOOP;
  IF next_line<>array_length(string_to_array(content,E'\n'),1)+1 THEN RETURN false; END IF;
  FOR item IN SELECT value FROM jsonb_array_elements(info->'empty_pages') LOOP
    IF jsonb_typeof(item)<>'number' OR item::text !~ '^[0-9]{1,2}$' OR item::text::integer<=previous OR item::text::integer>pages THEN RETURN false; END IF;
    previous:=item::text::integer;
  END LOOP;
  RETURN true;
END; $$;
"""
SEALS = r"""
      CREATE OR REPLACE FUNCTION public.butler_seal_document() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      BEGIN
        IF TG_OP IN ('DELETE','TRUNCATE') THEN
          RAISE EXCEPTION 'Document deletion is sealed' USING ERRCODE='23514';
        END IF;
        IF TG_OP='INSERT' THEN
          IF NEW.revision<>1 OR NEW.state<>'active' OR NEW.reviewed IS DISTINCT FROM false
            OR NEW.created_at<>NEW.updated_at
            OR (NEW.extraction_json IS NOT NULL AND NEW.ingest_key IS NULL) THEN
            RAISE EXCEPTION 'Document must start unreviewed' USING ERRCODE='23514';
          END IF;
        ELSE
          IF ROW(NEW.id,NEW.owner_id,NEW.scope_key,NEW.created_at,NEW.ingest_key)
            IS DISTINCT FROM ROW(OLD.id,OLD.owner_id,OLD.scope_key,OLD.created_at,OLD.ingest_key)
            OR OLD.state='forgotten' OR NEW.revision<>OLD.revision+1
            OR NEW.updated_at<OLD.updated_at
            OR (NEW.state='active' AND NEW.ingest_hash IS DISTINCT FROM OLD.ingest_hash) THEN
            RAISE EXCEPTION 'Document identity or revision is sealed' USING ERRCODE='23514';
          END IF;
          IF NEW.state='active' AND ROW(NEW.filename,NEW.content_text,NEW.sha256,NEW.byte_size,NEW.extraction_json)
            IS DISTINCT FROM ROW(OLD.filename,OLD.content_text,OLD.sha256,OLD.byte_size,OLD.extraction_json)
            AND (NEW.reviewed IS DISTINCT FROM false OR ROW(NEW.title,NEW.source_reference)
              IS DISTINCT FROM ROW(OLD.title,OLD.source_reference)) THEN
            RAISE EXCEPTION 'Replacement must reset review' USING ERRCODE='23514';
          END IF;
        END IF;
        IF NEW.state='active' AND (
          position('/' in NEW.filename)>0 OR position(chr(92) in NEW.filename)>0
          OR NEW.filename ~ '[[:cntrl:]]' OR length(NEW.filename)>120
          OR (NEW.extraction_json IS NULL AND (
            NEW.byte_size<>octet_length(convert_to(NEW.content_text,'UTF8'))
            OR NEW.sha256<>encode(sha256(convert_to(NEW.content_text,'UTF8')),'hex')
            OR NEW.filename !~* '[.](txt|md)$'))
          OR (NEW.extraction_json IS NOT NULL AND (
            NEW.filename !~* '[.]pdf$' OR NOT public.butler_pdf_extraction_valid(NEW.extraction_json,NEW.content_text)))) THEN
          RAISE EXCEPTION 'Document original provenance is invalid' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END; $$;


      CREATE OR REPLACE FUNCTION public.butler_seal_document_version() RETURNS trigger
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
            NEW.snapshot IS DISTINCT FROM (jsonb_build_object(
              'id',parent.id::text,'owner_id',parent.owner_id::text,'scope',parent.scope_key,
              'state',parent.state,'revision',parent.revision,'title',parent.title,
              'filename',parent.filename,'source_reference',parent.source_reference,
              'content_text',parent.content_text,'sha256',parent.sha256,'byte_size',parent.byte_size,
              'reviewed',parent.reviewed,'text_origin',CASE WHEN parent.extraction_json IS NULL THEN 'original_utf8' ELSE 'pdf_text' END,
              'line_count',CASE WHEN parent.content_text='' THEN 0 ELSE array_length(string_to_array(parent.content_text,E'
'),1) END,
              'created_at',NEW.snapshot->>'created_at','updated_at',NEW.snapshot->>'updated_at')
              || CASE WHEN parent.extraction_json IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('extraction',parent.extraction_json,'text_sha256',encode(sha256(convert_to(parent.content_text,'UTF8')),'hex')) END)
            OR (NEW.snapshot->>'created_at')::timestamptz IS DISTINCT FROM parent.created_at
            OR (NEW.snapshot->>'updated_at')::timestamptz IS DISTINCT FROM parent.updated_at
            OR (parent.extraction_json IS NULL AND NEW.original_bytes IS DISTINCT FROM convert_to(parent.content_text,'UTF8'))
            OR (parent.extraction_json IS NOT NULL AND (octet_length(NEW.original_bytes)<>parent.byte_size OR encode(sha256(NEW.original_bytes),'hex')<>parent.sha256 OR substring(NEW.original_bytes FROM 1 FOR 5)<>convert_to('%PDF-','UTF8')))
            OR (NEW.operation='extracted' AND (parent.extraction_json IS NULL OR parent.reviewed IS DISTINCT FROM false OR NEW.original_bytes IS DISTINCT FROM (SELECT original_bytes FROM public.document_versions WHERE document_id=NEW.document_id AND revision=NEW.revision-1)))
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


    """
LEGACY_SEALS = r"""
      CREATE OR REPLACE FUNCTION public.butler_seal_document() RETURNS trigger
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


      CREATE OR REPLACE FUNCTION public.butler_seal_document_version() RETURNS trigger
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
              'line_count',array_length(string_to_array(parent.content_text,E'
'),1),
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


    """


def upgrade():
    op.add_column(
        "document_records", sa.Column("extraction_json", postgresql.JSONB(none_as_null=True))
    )
    op.add_column("document_records", sa.Column("ingest_key", sa.Uuid()))
    op.add_column("document_records", sa.Column("ingest_hash", sa.String(64)))
    op.create_unique_constraint(
        "uq_document_ingest_key", "document_records", ["owner_id", "ingest_key"]
    )
    op.drop_constraint("ck_document_content", "document_records")
    op.create_check_constraint("ck_document_content", "document_records", NEW_CONTENT)
    op.drop_constraint("ck_document_operation", "document_versions")
    op.create_check_constraint(
        "ck_document_operation",
        "document_versions",
        "operation IN ('uploaded','corrected','replaced','extracted','forgotten')",
    )
    op.execute(VALIDATION)
    op.execute(SEALS)


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM document_records WHERE extraction_json IS NOT NULL) OR EXISTS(SELECT 1 FROM document_versions WHERE snapshot ? 'extraction' OR operation='extracted')"
        )
    ):
        raise RuntimeError(
            "PDF provenance evidence exists; scrub content first and retain the migration while extraction operation history exists"
        )
    op.execute(LEGACY_SEALS)
    op.execute("DROP FUNCTION public.butler_pdf_extraction_valid(jsonb,text)")
    op.drop_constraint("ck_document_operation", "document_versions")
    op.create_check_constraint(
        "ck_document_operation",
        "document_versions",
        "operation IN ('uploaded','corrected','replaced','forgotten')",
    )
    op.drop_constraint("ck_document_content", "document_records")
    op.create_check_constraint("ck_document_content", "document_records", OLD_CONTENT)
    op.drop_constraint("uq_document_ingest_key", "document_records")
    for column in ["ingest_hash", "ingest_key", "extraction_json"]:
        op.drop_column("document_records", column)
