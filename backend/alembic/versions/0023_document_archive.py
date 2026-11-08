"""Immutable archive cleanup obligations; no original bytes move in this migration."""

import sqlalchemy as sa

from alembic import op

revision = "0023_document_archive"
down_revision = "0022_document_library"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_archive_bindings",
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("document_records.id"), primary_key=True),
        sa.Column("root_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("""
      CREATE FUNCTION public.butler_seal_document_archive() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$
      BEGIN
        IF TG_OP <> 'INSERT' THEN
          RAISE EXCEPTION 'Archive bindings are immutable cleanup obligations' USING ERRCODE='23514';
        END IF;
        IF NOT EXISTS(SELECT 1 FROM public.document_records WHERE id=NEW.document_id AND state='active') THEN
          RAISE EXCEPTION 'Archive binding needs an active document' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END; $$;
      CREATE TRIGGER butler_document_archive_guard BEFORE INSERT OR UPDATE OR DELETE
        ON public.document_archive_bindings FOR EACH ROW EXECUTE FUNCTION public.butler_seal_document_archive();
      CREATE TRIGGER butler_document_archive_truncate_guard BEFORE TRUNCATE
        ON public.document_archive_bindings FOR EACH STATEMENT EXECUTE FUNCTION public.butler_seal_document_archive();
    """)


def downgrade():
    op.drop_table("document_archive_bindings")
    op.execute("DROP FUNCTION public.butler_seal_document_archive()")
