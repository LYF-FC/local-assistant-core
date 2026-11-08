"""Narrow private-scope locking and digest receipt verification; no audit-log read grant.

Revision ID: 0019_discovery_digest_checks
Revises: 0018_work_restore_requests
"""

from alembic import op

revision = "0019_discovery_digest_checks"
down_revision = "0018_work_restore_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE FUNCTION public.butler_lock_discovery_scope(p_actor uuid, p_scope text)
      RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      BEGIN
        IF p_scope NOT IN ('member_a_private','member_b_private') THEN RETURN false; END IF;
        PERFORM g.user_id FROM public.user_scopes AS g JOIN public.scopes AS s ON s.id=g.scope_id
          WHERE g.user_id=p_actor AND s.key=p_scope FOR SHARE OF g;
        RETURN FOUND;
      END; $$;
      REVOKE ALL ON FUNCTION public.butler_lock_discovery_scope(uuid,text) FROM PUBLIC;
      CREATE FUNCTION public.butler_discovery_review_deadline(
        p_review uuid, p_actor uuid, p_session uuid, p_scope text, p_hash text, p_count integer)
      RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
        SELECT a.metadata_json->>'valid_until' FROM public.audit_events AS a
        WHERE p_scope IN ('member_a_private','member_b_private') AND p_count BETWEEN 1 AND 10
          AND p_hash ~ '^[a-f0-9]{64}$'
          AND a.event_type='discovery.digest_preview' AND a.result_status='success'
          AND a.initiator_type='human' AND a.initiator_id=p_actor::text
          AND a.scope_key=p_scope AND a.entity_type='discovery_digest' AND a.entity_id=p_review::text
          AND a.occurred_at >= statement_timestamp()-interval '60 seconds'
          AND a.metadata_json->>'schema_version'='1'
          AND a.metadata_json->>'session_id'=p_session::text
          AND a.metadata_json->>'reviewed_hash'=p_hash
          AND a.metadata_json->>'selected_count'=p_count::text
        ORDER BY a.occurred_at DESC LIMIT 1;
      $$;
      REVOKE ALL ON FUNCTION public.butler_discovery_review_deadline(uuid,uuid,uuid,text,text,integer) FROM PUBLIC;
    """)


def downgrade():
    op.execute(
        "DROP FUNCTION public.butler_discovery_review_deadline(uuid,uuid,uuid,text,text,integer)"
    )
    op.execute("DROP FUNCTION public.butler_lock_discovery_scope(uuid,text)")
