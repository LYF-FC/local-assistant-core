"""Narrow, count-only audit projection for the technical-admin operations summary.

The runtime role keeps INSERT-only access to audit_events. This function is the only read
path: it returns aggregate counts by a closed category and outcome catalogue for the fixed
auth./admin./operations. event families, and never an id, actor, scope, entity, metadata or
timestamp. It writes nothing.
"""

from alembic import op

revision = "0037_audit_summary"
down_revision = "0036_notification_recheck"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE FUNCTION public.butler_audit_summary(p_actor uuid, p_end timestamptz, p_hours integer)
      RETURNS TABLE(category_key text, outcome_key text, event_count bigint)
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
      BEGIN
        IF p_end IS NULL OR p_hours IS NULL OR p_hours NOT IN (24, 168) THEN
          RAISE EXCEPTION 'Unsupported audit summary window' USING ERRCODE = '22023';
        END IF;
        PERFORM 1 FROM public.users AS u
          JOIN public.user_scopes AS g ON g.user_id = u.id
          JOIN public.scopes AS s ON s.id = g.scope_id
          WHERE u.id = p_actor AND u.is_active AND s.key = 'technical_admin';
        IF NOT FOUND THEN
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
      REVOKE ALL ON FUNCTION public.butler_audit_summary(uuid, timestamptz, integer) FROM PUBLIC;
    """)


def downgrade():
    op.execute("DROP FUNCTION public.butler_audit_summary(uuid, timestamptz, integer)")
