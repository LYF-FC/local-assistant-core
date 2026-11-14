"""Classify the spec 073 work-status view as an operations read in the audit summary.

Owner decision D3 (14 November 2026). ``operations.work_status`` is a reviewed technical-admin
view of operations, so the count-only audit summary (migration 0037) maps it to
``operations_read`` instead of the holding category ``other_security``. Only that one literal
changes: the signature, return type, ``SECURITY DEFINER``, fixed ``search_path``, token binding,
recent-window predicate, window guard, event-family filter and every other mapping are identical
to 0037. ``CREATE OR REPLACE`` keeps the owner, the runtime EXECUTE grant and the PUBLIC
revocation; the revocation is re-run defensively. The seven-category response shape is unchanged.

Downgrade restores 0037's exact body (no DROP; 0037's own downgrade still drops the function).
No data changes: existing ``operations.work_status`` rows count as ``other_security`` again.
"""

from alembic import op

revision = "0038_work_status_audit_category"
down_revision = "0037_audit_summary"
branch_labels = None
depends_on = None

READ_EVENTS_0037 = ("operations.read", "operations.audit_summary")
READ_EVENTS_0038 = (*READ_EVENTS_0037, "operations.work_status")

DEFINITION = """
      CREATE OR REPLACE FUNCTION public.butler_audit_summary(p_token text, p_end timestamptz, p_hours integer)
      RETURNS TABLE(category_key text, outcome_key text, event_count bigint)
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
      DECLARE
        v_actor uuid;
        v_now timestamptz := clock_timestamp();
      BEGIN
        IF p_end IS NULL OR p_hours IS NULL OR p_hours NOT IN (24, 168) THEN
          RAISE EXCEPTION 'Unsupported audit summary window' USING ERRCODE = '22023';
        END IF;
        -- Recent window only: the end must be the current time, within 60 s before (the
        -- summary's own validity) or 5 s after (clock skew) the database's actual clock.
        IF p_end < v_now - interval '60 seconds' OR p_end > v_now + interval '5 seconds' THEN
          RAISE EXCEPTION 'Audit summary window must end at the current time' USING ERRCODE = '22023';
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
              WHEN a.event_type IN ({read_events}) THEN 'operations_read'
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
"""


def define(read_events):
    listed = ", ".join(f"'{name}'" for name in read_events)
    op.execute(DEFINITION.format(read_events=listed))
    op.execute(
        "REVOKE ALL ON FUNCTION public.butler_audit_summary(text, timestamptz, integer) FROM PUBLIC"
    )


def upgrade():
    define(READ_EVENTS_0038)


def downgrade():
    define(READ_EVENTS_0037)
