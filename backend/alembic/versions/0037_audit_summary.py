"""Narrow, count-only audit projection for the technical-admin operations summary.

The runtime role keeps INSERT-only access to audit_events. This function is the only read
path: it returns aggregate counts by a closed category and outcome catalogue for the fixed
auth./admin./operations. event families, and never an id, actor, scope, entity, metadata or
timestamp. It writes nothing.

Actor binding: the function takes no actor id. The only trusted identity inside a database
transaction is the session the application authenticated, so the caller passes the raw session
token, the function hashes it exactly as the application does and derives the actor from a
current, unrevoked, unexpired, non-idle auth_sessions row of an active technical administrator.
The stored token_hash alone (readable by the runtime role) is not accepted, and a user id cannot
be supplied. Limit: the runtime role is the application and may insert auth_sessions rows, so a
fully compromised runtime role could mint a session; the function narrows, but cannot remove,
that trust.
"""

from alembic import op

revision = "0037_audit_summary"
down_revision = "0036_notification_recheck"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE FUNCTION public.butler_audit_summary(p_token text, p_end timestamptz, p_hours integer)
      RETURNS TABLE(category_key text, outcome_key text, event_count bigint)
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
      DECLARE
        v_actor uuid;
      BEGIN
        IF p_end IS NULL OR p_hours IS NULL OR p_hours NOT IN (24, 168) THEN
          RAISE EXCEPTION 'Unsupported audit summary window' USING ERRCODE = '22023';
        END IF;
        IF p_token IS NULL OR length(p_token) NOT BETWEEN 40 AND 128 THEN
          RAISE EXCEPTION 'Technical administration is required' USING ERRCODE = '42501';
        END IF;
        SELECT u.id INTO v_actor
          FROM public.auth_sessions AS a
          JOIN public.users AS u ON u.id = a.user_id
          JOIN public.user_scopes AS g ON g.user_id = u.id
          JOIN public.scopes AS s ON s.id = g.scope_id
          WHERE a.token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex')
            AND a.revoked_at IS NULL
            AND a.expires_at > now()
            AND a.last_seen_at > now() - interval '30 minutes'
            AND u.is_active AND s.key = 'technical_admin'
          LIMIT 1;
        IF v_actor IS NULL THEN
          RAISE EXCEPTION 'Technical administration is required' USING ERRCODE = '42501';
        END IF;
        RETURN QUERY
        SELECT c.cat, c.res, count(*)::bigint
        FROM (
          SELECT
            CASE
              WHEN a.event_type IN ('auth.login', 'auth.logout', 'auth.session_bootstrap') THEN 'sign_in'
              WHEN a.event_type IN ('auth.login_denied', 'auth.session_denied', 'auth.scope_denied',
                'auth.csrf_denied', 'auth.host_denied', 'auth.origin_denied', 'auth.tls_required',
                'auth.bootstrap_type_denied', 'auth.rate_limited', 'operations.session_denied')
                THEN 'denied_access'
              WHEN a.event_type IN ('admin.user_created', 'admin.password_changed',
                'admin.user_status_changed', 'admin.scope_changed') THEN 'access_change'
              WHEN a.event_type = 'admin.recovery_assessed'
                OR starts_with(a.event_type, 'admin.restored_')
                OR starts_with(a.event_type, 'admin.work_restore_') THEN 'recovery_admin'
              WHEN starts_with(a.event_type, 'admin.') THEN 'other_admin'
              WHEN a.event_type IN ('operations.read', 'operations.audit_summary') THEN 'operations_read'
              ELSE 'other_security'
            END AS cat,
            CASE a.result_status
              WHEN 'success' THEN 'success'
              WHEN 'denied' THEN 'denied'
              ELSE 'other'
            END AS res
          FROM public.audit_events AS a
          WHERE a.occurred_at >= p_end - make_interval(hours => p_hours)
            AND a.occurred_at <= p_end
            AND (starts_with(a.event_type, 'auth.') OR starts_with(a.event_type, 'admin.')
              OR starts_with(a.event_type, 'operations.'))
        ) AS c
        GROUP BY c.cat, c.res;
      END; $$;
      REVOKE ALL ON FUNCTION public.butler_audit_summary(text, timestamptz, integer) FROM PUBLIC;
    """)


def downgrade():
    op.execute("DROP FUNCTION public.butler_audit_summary(text, timestamptz, integer)")
