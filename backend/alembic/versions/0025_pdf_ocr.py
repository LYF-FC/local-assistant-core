"""Permit explicit bounded OCR provenance without rewriting snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "0025_pdf_ocr"
down_revision = "0024_pdf_ingestion"
branch_labels = None
depends_on = None

OLD_VALIDATION = r"""
CREATE OR REPLACE FUNCTION public.butler_pdf_extraction_valid(info jsonb, content text) RETURNS boolean
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
VALIDATION = r"""
CREATE OR REPLACE FUNCTION public.butler_pdf_extraction_valid(info jsonb, content text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $$
DECLARE span jsonb; item jsonb; pages integer; next_line integer:=1; page_no integer:=0; previous integer:=0;
BEGIN
  IF jsonb_typeof(info)<>'object' OR NOT info ?& ARRAY['engine','version','status','pages','page_spans','empty_pages']
    OR info-ARRAY['engine','version','status','pages','page_spans','empty_pages']<>'{}'::jsonb
    OR jsonb_typeof(info->'engine')<>'string' OR info->>'engine' NOT IN ('poppler-text-v1','poppler-tesseract-v1') OR jsonb_typeof(info->'version')<>'string'
    OR info->>'version' !~ '^(unavailable|[0-9.]{1,15}([+][a-f0-9]{64})?)$'
    OR info->>'status' NOT IN ('ready','no_text','encrypted','invalid','resource_limit','unavailable')
    OR jsonb_typeof(info->'status')<>'string' OR jsonb_typeof(info->'pages')<>'number'
    OR info->>'pages' !~ '^[0-9]{1,2}$' OR jsonb_typeof(info->'page_spans')<>'array'
    OR jsonb_typeof(info->'empty_pages')<>'array' THEN RETURN false; END IF;
  pages:=(info->>'pages')::integer;
  IF pages>12 OR (info->>'engine'='poppler-tesseract-v1' AND pages>2) OR ((info->>'status'='unavailable') IS DISTINCT FROM (info->>'version'='unavailable')) THEN RETURN false; END IF;
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


def upgrade():
    op.execute(VALIDATION)


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM document_records WHERE extraction_json->>'engine'='poppler-tesseract-v1') OR EXISTS(SELECT 1 FROM document_versions WHERE snapshot->'extraction'->>'engine'='poppler-tesseract-v1')"
        )
    ):
        raise RuntimeError(
            "OCR provenance evidence exists; forget managed OCR content before downgrade"
        )
    op.execute(OLD_VALIDATION)
