"""Calendar provider mode: recurring series, overrides, change log and sync state.

Five new tables (provider links, series, overrides, change history, sync state) with a chain of
composite foreign keys from ``calendar_sources(id, owner_id, scope_key)`` so that every child row
carries its parent's owner and scope, plus the triggers that make the database refuse every write
outside the documented transitions (proposal revision 11, sections 6 and 12).

Additive DDL on the sealed ``calendar_sources`` only: one unique index, the exclusivity trigger
``butler_calendar_provider_exclusive`` and the deferred scrub-completeness constraint trigger. No
existing column, function or trigger is changed.

F1 (floor / ``deleted_by_cascade`` coupling) is enforced by the database: see
``butler_calendar_override_guard`` and docs/BATCH3_F1_AUDIT.md.

The migration is self-contained (no application imports). The blocked-reason, last-error-code and
tombstone-hash literals below are compared with ``app.calendar_codes`` by a unit test.

Downgrade drops the five tables, their functions, the two additive triggers and the additive
index. All provider-mode data is lost by design; legacy manual sources are untouched.
"""

from alembic import op

revision = "0035_calendar_provider_sync"
down_revision = "0034_invoice_filing_execution"
branch_labels = None
depends_on = None

BLOCKED_REASONS = (
    "range_thisandfuture",
    "freq_unsupported",
    "by_rule_unsupported",
    "by_day_ordinal",
    "by_month_day_negative",
    "rscale_unsupported",
    "count_until_both",
    "count_limit",
    "interval_limit",
    "rule_part_unknown",
    "rule_part_duplicate",
    "rdate_period",
    "utc_value_ambiguous",
    "rrule_syntax",
    "by_list_duplicate",
    "by_day_freq_unsupported",
    "by_rule_freq_mismatch",
    "until_before_start",
    "until_type_mismatch",
    "dtstart_not_synchronized",
    "exdate_type_mismatch",
    "rdate_type_mismatch",
    "override_type_mismatch",
    "zone_mismatch",
    "zone_floating",
    "zone_unknown",
    "rule_too_large",
    "exdate_limit",
    "rdate_limit",
    "item_malformed",
    "override_unmatched",
    "override_orphan",
    "sequence_conflict",
    "series_limit",
    "override_limit",
    "tombstone_limit",
    "change_log_full",
    "page_too_large",
    "cursor_malformed",
    "cursor_no_progress",
    "cursor_invalid",
    "cursor_expired",
    "source_forgotten",
)
LAST_ERROR_CODES = ("provider_unavailable", "provider_timeout")
TOMBSTONE_HASH = "136a90c93d282c605c5a7003b6a381fa429e9bce3201d454cb59a41480005b01"


def _in(values):
    return ", ".join(f"'{value}'" for value in values)


SCOPES = "'household_shared','member_a_private','member_b_private'"
WALL = "'^[0-9]{4}-[0-9]{2}-[0-9]{2}(T[0-9]{2}:[0-9]{2}:[0-9]{2})?$'"

TABLES = f"""
CREATE UNIQUE INDEX uq_calendar_source_identity
  ON public.calendar_sources (id, owner_id, scope_key);

CREATE TABLE public.calendar_provider_links (
  source_id uuid PRIMARY KEY,
  owner_id uuid NOT NULL REFERENCES public.users(id),
  scope_key varchar(96) NOT NULL,
  provider_kind varchar(16) NOT NULL,
  provider_ref varchar(64),
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_calendar_link_source FOREIGN KEY (source_id, owner_id, scope_key)
    REFERENCES public.calendar_sources (id, owner_id, scope_key),
  CONSTRAINT uq_calendar_link_identity UNIQUE (source_id, owner_id, scope_key),
  CONSTRAINT ck_calendar_link_scope CHECK (scope_key IN ({SCOPES})),
  CONSTRAINT ck_calendar_link_kind CHECK (provider_kind IN ('synthetic')),
  CONSTRAINT ck_calendar_link_ref CHECK (provider_ref IS NULL OR provider_ref ~ '^[a-z0-9_-]{{1,64}}$')
);

CREATE TABLE public.calendar_series (
  id uuid PRIMARY KEY,
  source_id uuid NOT NULL,
  owner_id uuid NOT NULL REFERENCES public.users(id),
  scope_key varchar(96) NOT NULL,
  uid varchar(255),
  state varchar(16) NOT NULL,
  kind varchar(16),
  status varchar(16),
  sequence integer NOT NULL,
  title varchar(160),
  start_local timestamp,
  start_date date,
  zone varchar(64),
  duration_seconds integer,
  duration_days integer,
  rule jsonb,
  exdates jsonb,
  rdates jsonb,
  provider_version varchar(128),
  revision integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  deleted_at timestamptz,
  CONSTRAINT fk_calendar_series_link FOREIGN KEY (source_id, owner_id, scope_key)
    REFERENCES public.calendar_provider_links (source_id, owner_id, scope_key),
  CONSTRAINT uq_calendar_series_identity UNIQUE (id, source_id, owner_id, scope_key),
  CONSTRAINT uq_calendar_series_uid UNIQUE (source_id, uid),
  CONSTRAINT ck_calendar_series_scope CHECK (scope_key IN ({SCOPES})),
  CONSTRAINT ck_calendar_series_state CHECK (state IN ('active','deleted','forgotten')),
  CONSTRAINT ck_calendar_series_kind CHECK (kind IS NULL OR kind IN ('timed','all_day')),
  CONSTRAINT ck_calendar_series_status
    CHECK (status IS NULL OR status IN ('confirmed','tentative','cancelled')),
  CONSTRAINT ck_calendar_series_sequence CHECK (sequence >= 0),
  CONSTRAINT ck_calendar_series_revision CHECK (revision >= 1),
  CONSTRAINT ck_calendar_series_duration_seconds
    CHECK (duration_seconds IS NULL OR duration_seconds BETWEEN 1 AND 2678400),
  CONSTRAINT ck_calendar_series_duration_days
    CHECK (duration_days IS NULL OR duration_days BETWEEN 1 AND 31),
  CONSTRAINT ck_calendar_series_title CHECK (title IS NULL OR length(trim(title)) > 0),
  CONSTRAINT ck_calendar_series_rule_size CHECK (rule IS NULL OR octet_length(rule::text) <= 4096),
  CONSTRAINT ck_calendar_series_lists CHECK (
    (exdates IS NULL OR (jsonb_typeof(exdates) = 'array' AND jsonb_array_length(exdates) <= 100))
    AND (rdates IS NULL OR (jsonb_typeof(rdates) = 'array' AND jsonb_array_length(rdates) <= 100))),
  CONSTRAINT ck_calendar_series_uid CHECK (
    (state = 'forgotten' AND uid IS NULL) OR (state <> 'forgotten' AND uid IS NOT NULL)),
  CONSTRAINT ck_calendar_series_deleted_at CHECK ((state = 'deleted') = (deleted_at IS NOT NULL)),
  CONSTRAINT ck_calendar_series_content CHECK (
    (state = 'active' AND status IS NOT NULL AND title IS NOT NULL
      AND exdates IS NOT NULL AND rdates IS NOT NULL
      AND ((kind = 'timed' AND start_local IS NOT NULL AND zone IS NOT NULL
            AND duration_seconds IS NOT NULL AND start_date IS NULL AND duration_days IS NULL)
        OR (kind = 'all_day' AND start_date IS NOT NULL AND duration_days IS NOT NULL
            AND start_local IS NULL AND zone IS NULL AND duration_seconds IS NULL)))
    OR (state IN ('deleted','forgotten') AND kind IS NULL AND status IS NULL AND title IS NULL
      AND start_local IS NULL AND start_date IS NULL AND zone IS NULL
      AND duration_seconds IS NULL AND duration_days IS NULL AND rule IS NULL
      AND exdates IS NULL AND rdates IS NULL AND provider_version IS NULL))
);
CREATE INDEX ix_calendar_series_source_state ON public.calendar_series (source_id, state);

CREATE TABLE public.calendar_overrides (
  id uuid PRIMARY KEY,
  series_id uuid NOT NULL,
  source_id uuid NOT NULL,
  owner_id uuid NOT NULL REFERENCES public.users(id),
  scope_key varchar(96) NOT NULL,
  recurrence_id varchar(32) NOT NULL,
  state varchar(16) NOT NULL,
  deleted_by_cascade boolean NOT NULL DEFAULT false,
  status varchar(16),
  sequence integer NOT NULL,
  start_wall varchar(32),
  duration integer,
  title varchar(160),
  revision integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  deleted_at timestamptz,
  CONSTRAINT fk_calendar_override_series FOREIGN KEY (series_id, source_id, owner_id, scope_key)
    REFERENCES public.calendar_series (id, source_id, owner_id, scope_key),
  CONSTRAINT uq_calendar_override_identity UNIQUE (id, source_id, owner_id, scope_key),
  CONSTRAINT uq_calendar_override_instance UNIQUE (series_id, recurrence_id),
  CONSTRAINT ck_calendar_override_scope CHECK (scope_key IN ({SCOPES})),
  CONSTRAINT ck_calendar_override_state CHECK (state IN ('active','deleted','forgotten')),
  CONSTRAINT ck_calendar_override_status
    CHECK (status IS NULL OR status IN ('confirmed','tentative','cancelled')),
  CONSTRAINT ck_calendar_override_sequence CHECK (sequence >= 0),
  CONSTRAINT ck_calendar_override_revision CHECK (revision >= 1),
  CONSTRAINT ck_calendar_override_duration
    CHECK (duration IS NULL OR duration BETWEEN 1 AND 2678400),
  CONSTRAINT ck_calendar_override_title CHECK (title IS NULL OR length(trim(title)) > 0),
  CONSTRAINT ck_calendar_override_recurrence_id CHECK (recurrence_id ~ {WALL}),
  CONSTRAINT ck_calendar_override_start CHECK (start_wall IS NULL OR start_wall ~ {WALL}),
  CONSTRAINT ck_calendar_override_cascade CHECK (NOT deleted_by_cascade OR state = 'deleted'),
  CONSTRAINT ck_calendar_override_deleted_at CHECK ((state = 'deleted') = (deleted_at IS NOT NULL)),
  CONSTRAINT ck_calendar_override_content CHECK (
    (state = 'active' AND status IS NOT NULL)
    OR (state IN ('deleted','forgotten') AND status IS NULL AND start_wall IS NULL
      AND duration IS NULL AND title IS NULL))
);

CREATE TABLE public.calendar_changes (
  id uuid PRIMARY KEY,
  source_id uuid NOT NULL,
  owner_id uuid NOT NULL REFERENCES public.users(id),
  scope_key varchar(96) NOT NULL,
  seq integer NOT NULL,
  entity varchar(16) NOT NULL,
  series_id uuid,
  override_id uuid,
  operation varchar(16) NOT NULL,
  sequence integer NOT NULL,
  cascade_count integer NOT NULL DEFAULT 0,
  content_hash char(64) NOT NULL,
  snapshot jsonb,
  actor_id uuid,
  sync_run_id uuid NOT NULL,
  cursor_after varchar(512) NOT NULL,
  applied_at timestamptz NOT NULL,
  CONSTRAINT fk_calendar_change_link FOREIGN KEY (source_id, owner_id, scope_key)
    REFERENCES public.calendar_provider_links (source_id, owner_id, scope_key),
  CONSTRAINT fk_calendar_change_series FOREIGN KEY (series_id, source_id, owner_id, scope_key)
    REFERENCES public.calendar_series (id, source_id, owner_id, scope_key),
  CONSTRAINT fk_calendar_change_override FOREIGN KEY (override_id, source_id, owner_id, scope_key)
    REFERENCES public.calendar_overrides (id, source_id, owner_id, scope_key),
  CONSTRAINT uq_calendar_change_seq UNIQUE (source_id, seq),
  CONSTRAINT ck_calendar_change_scope CHECK (scope_key IN ({SCOPES})),
  CONSTRAINT ck_calendar_change_seq CHECK (seq BETWEEN 1 AND 5000),
  CONSTRAINT ck_calendar_change_entity CHECK (entity IN ('series','override')),
  CONSTRAINT ck_calendar_change_target CHECK (
    (entity = 'series' AND series_id IS NOT NULL AND override_id IS NULL)
    OR (entity = 'override' AND override_id IS NOT NULL AND series_id IS NULL)),
  CONSTRAINT ck_calendar_change_operation CHECK (operation IN ('upsert','delete','revive')),
  CONSTRAINT ck_calendar_change_sequence CHECK (sequence >= 0),
  CONSTRAINT ck_calendar_change_cascade CHECK (
    cascade_count BETWEEN 0 AND 100
    AND (cascade_count = 0 OR (entity = 'series' AND operation IN ('delete','revive')))),
  CONSTRAINT ck_calendar_change_hash CHECK (
    content_hash ~ '^[0-9a-f]{{64}}$'
    AND ((operation = 'delete') = (content_hash = '{TOMBSTONE_HASH}'))),
  CONSTRAINT ck_calendar_change_actor CHECK (actor_id IS NULL)
);
CREATE UNIQUE INDEX uq_calendar_change_applied ON public.calendar_changes
  (source_id, entity, COALESCE(series_id, override_id), sequence, content_hash);

CREATE TABLE public.calendar_sync_state (
  source_id uuid PRIMARY KEY,
  owner_id uuid NOT NULL REFERENCES public.users(id),
  scope_key varchar(96) NOT NULL,
  status varchar(16) NOT NULL,
  cursor varchar(512),
  applied_seq integer NOT NULL,
  claim_token uuid,
  claim_expires_at timestamptz,
  attempts integer NOT NULL,
  next_attempt_at timestamptz,
  last_attempt_at timestamptz,
  last_success_at timestamptz,
  blocked_reason varchar(32),
  blocked_detail jsonb,
  last_error_code varchar(32),
  revision integer NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT fk_calendar_sync_link FOREIGN KEY (source_id, owner_id, scope_key)
    REFERENCES public.calendar_provider_links (source_id, owner_id, scope_key),
  CONSTRAINT ck_calendar_sync_scope CHECK (scope_key IN ({SCOPES})),
  CONSTRAINT ck_calendar_sync_status
    CHECK (status IN ('never','ok','retry_wait','failed','blocked')),
  CONSTRAINT ck_calendar_sync_attempts CHECK (attempts BETWEEN 0 AND 5),
  CONSTRAINT ck_calendar_sync_applied CHECK (applied_seq BETWEEN 0 AND 5000),
  CONSTRAINT ck_calendar_sync_revision CHECK (revision >= 1),
  CONSTRAINT ck_calendar_sync_claim CHECK ((claim_token IS NULL) = (claim_expires_at IS NULL)),
  CONSTRAINT ck_calendar_sync_blocked
    CHECK ((status = 'blocked') = (blocked_reason IS NOT NULL)),
  CONSTRAINT ck_calendar_sync_blocked_reason
    CHECK (blocked_reason IS NULL OR blocked_reason IN ({_in(BLOCKED_REASONS)})),
  CONSTRAINT ck_calendar_sync_detail
    CHECK (blocked_detail IS NULL OR (status = 'blocked' AND octet_length(blocked_detail::text) <= 1024)),
  CONSTRAINT ck_calendar_sync_error
    CHECK (last_error_code IS NULL OR last_error_code IN ({_in(LAST_ERROR_CODES)}))
);
"""

# Violations use SQLSTATE 23514 and name the rule in CONSTRAINT so tests (and operators) can
# assert exactly which guard refused a statement.
FUNCTIONS = """
CREATE FUNCTION public.butler_calendar_provider_sealed() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
  RAISE EXCEPTION 'Calendar provider rows are never deleted' USING ERRCODE='23514',
    CONSTRAINT='butler_calendar_provider_sealed';
END; $$;

CREATE FUNCTION public.butler_calendar_link_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE src public.calendar_sources;
BEGIN
  IF TG_OP='INSERT' THEN
    SELECT * INTO src FROM public.calendar_sources WHERE id=NEW.source_id FOR UPDATE;
    IF src.id IS NULL OR src.state<>'active' OR src.revision<>1
      OR src.data->>'status' IS DISTINCT FROM 'setup_required' OR NEW.provider_ref IS NULL THEN
      RAISE EXCEPTION 'A provider link needs an unconfigured, unforgotten source'
        USING ERRCODE='23514', CONSTRAINT='butler_calendar_link_unconfigured';
    END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.source_id,NEW.owner_id,NEW.scope_key,NEW.provider_kind,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.source_id,OLD.owner_id,OLD.scope_key,OLD.provider_kind,OLD.created_at)
    OR NEW.provider_ref IS NOT NULL OR OLD.provider_ref IS NULL
    OR NOT EXISTS (SELECT 1 FROM public.calendar_sources WHERE id=OLD.source_id AND state='forgotten') THEN
    RAISE EXCEPTION 'A provider link is immutable except provider_ref to NULL after forgetting'
      USING ERRCODE='23514', CONSTRAINT='butler_calendar_link_immutable';
  END IF;
  RETURN NEW;
END; $$;

CREATE FUNCTION public.butler_calendar_series_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE src public.calendar_sources; active_n integer; total_n integer;
BEGIN
  SELECT * INTO src FROM public.calendar_sources WHERE id=NEW.source_id FOR UPDATE;
  IF TG_OP='INSERT' THEN
    IF src.state IS DISTINCT FROM 'active' OR NEW.state='forgotten' OR NEW.revision<>1
      OR NEW.created_at<>NEW.updated_at THEN
      RAISE EXCEPTION 'Invalid new calendar series' USING ERRCODE='23514',
        CONSTRAINT='butler_calendar_series_insert';
    END IF;
    SELECT count(*) FILTER (WHERE state='active'), count(*) INTO active_n, total_n
      FROM public.calendar_series WHERE source_id=NEW.source_id;
    IF total_n+1>400 OR (NEW.state='active' AND active_n+1>200) THEN
      RAISE EXCEPTION 'Calendar series limit' USING ERRCODE='23514',
        CONSTRAINT='butler_calendar_series_limit';
    END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.source_id,NEW.owner_id,NEW.scope_key,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id,OLD.source_id,OLD.owner_id,OLD.scope_key,OLD.created_at)
    OR (NEW.uid IS DISTINCT FROM OLD.uid AND NOT (NEW.uid IS NULL AND NEW.state='forgotten')) THEN
    RAISE EXCEPTION 'Calendar series identity is immutable' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_series_identity';
  END IF;
  IF OLD.state='forgotten' THEN
    RAISE EXCEPTION 'A forgotten calendar series is terminal' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_series_terminal';
  END IF;
  IF NEW.revision<>OLD.revision+1 OR NEW.updated_at<OLD.updated_at THEN
    RAISE EXCEPTION 'Calendar series revision must advance by one' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_series_revision';
  END IF;
  IF NEW.state='forgotten' THEN
    IF src.state IS DISTINCT FROM 'forgotten' OR NEW.sequence<>OLD.sequence THEN
      RAISE EXCEPTION 'A series is forgotten only with its forgotten source' USING ERRCODE='23514',
        CONSTRAINT='butler_calendar_series_forget';
    END IF;
    RETURN NEW;
  END IF;
  IF src.state IS DISTINCT FROM 'active' OR NEW.sequence<=OLD.sequence
    OR (OLD.state='deleted' AND NEW.state='deleted' AND NEW.deleted_at IS DISTINCT FROM OLD.deleted_at) THEN
    RAISE EXCEPTION 'Calendar series sequence must strictly increase on an unforgotten source'
      USING ERRCODE='23514', CONSTRAINT='butler_calendar_series_transition';
  END IF;
  IF OLD.state='deleted' AND NEW.state='active' THEN
    SELECT count(*) INTO active_n FROM public.calendar_series
      WHERE source_id=NEW.source_id AND state='active';
    IF active_n+1>200 THEN
      RAISE EXCEPTION 'Calendar series limit' USING ERRCODE='23514',
        CONSTRAINT='butler_calendar_series_limit';
    END IF;
  END IF;
  RETURN NEW;
END; $$;

CREATE FUNCTION public.butler_calendar_series_orphans() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
  -- Deferred: the queued event carries the row version that fired it, but the rule is about the
  -- state at commit, so a series that was deleted and revived in one transaction is not refused.
  IF EXISTS (SELECT 1 FROM public.calendar_series WHERE id=NEW.id AND state<>'active')
    AND EXISTS (SELECT 1 FROM public.calendar_overrides WHERE series_id=NEW.id AND state='active') THEN
    RAISE EXCEPTION 'An active override cannot outlive its active series' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_override_series_active';
  END IF;
  RETURN NULL;
END; $$;

CREATE FUNCTION public.butler_calendar_override_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE src public.calendar_sources; ser public.calendar_series; active_n integer; total_n integer;
BEGIN
  SELECT * INTO src FROM public.calendar_sources WHERE id=NEW.source_id FOR UPDATE;
  SELECT * INTO ser FROM public.calendar_series WHERE id=NEW.series_id;
  IF TG_OP='INSERT' THEN
    IF src.state IS DISTINCT FROM 'active' OR ser.state IS NULL OR ser.state='forgotten'
      OR NEW.state='forgotten' OR NEW.revision<>1 OR NEW.created_at<>NEW.updated_at
      OR NEW.deleted_by_cascade THEN
      RAISE EXCEPTION 'Invalid new calendar override' USING ERRCODE='23514',
        CONSTRAINT='butler_calendar_override_insert';
    END IF;
    IF NEW.state='active' AND ser.state<>'active' THEN
      RAISE EXCEPTION 'An active override needs an active series' USING ERRCODE='23514',
        CONSTRAINT='butler_calendar_override_series_active';
    END IF;
    SELECT count(*) FILTER (WHERE state='active'), count(*) INTO active_n, total_n
      FROM public.calendar_overrides WHERE series_id=NEW.series_id;
    IF total_n+1>200 OR (NEW.state='active' AND active_n+1>100) THEN
      RAISE EXCEPTION 'Calendar override limit' USING ERRCODE='23514',
        CONSTRAINT='butler_calendar_override_limit';
    END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.series_id,NEW.source_id,NEW.owner_id,NEW.scope_key,NEW.recurrence_id,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id,OLD.series_id,OLD.source_id,OLD.owner_id,OLD.scope_key,OLD.recurrence_id,OLD.created_at) THEN
    RAISE EXCEPTION 'Calendar override identity is immutable' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_override_identity';
  END IF;
  IF OLD.state='forgotten' THEN
    RAISE EXCEPTION 'A forgotten calendar override is terminal' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_override_terminal';
  END IF;
  IF NEW.revision<>OLD.revision+1 OR NEW.updated_at<OLD.updated_at THEN
    RAISE EXCEPTION 'Calendar override revision must advance by one' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_override_revision';
  END IF;
  IF NEW.state='forgotten' THEN
    IF src.state IS DISTINCT FROM 'forgotten' OR NEW.sequence<>OLD.sequence THEN
      RAISE EXCEPTION 'An override is forgotten only with its forgotten source' USING ERRCODE='23514',
        CONSTRAINT='butler_calendar_override_forget';
    END IF;
    RETURN NEW;
  END IF;
  IF src.state IS DISTINCT FROM 'active' THEN
    RAISE EXCEPTION 'Calendar override change on a forgotten source' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_override_transition';
  END IF;
  -- F1: the floor and its origin flag change only together.
  IF NEW.deleted_by_cascade AND NOT OLD.deleted_by_cascade THEN
    -- the flag becomes true only in the active -> deleted cascade, floor unchanged, series deleted
    IF OLD.state<>'active' OR NEW.state<>'deleted' OR NEW.sequence<>OLD.sequence
      OR ser.state<>'deleted' THEN
      RAISE EXCEPTION 'Cascade origin only on the active to deleted cascade with an unchanged floor'
        USING ERRCODE='23514', CONSTRAINT='butler_calendar_override_floor_origin';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.deleted_by_cascade THEN
    -- a cascade tombstone is final until a strictly higher floor-raising delete or revive
    RAISE EXCEPTION 'A cascade tombstone changes only with a strictly higher sequence'
      USING ERRCODE='23514', CONSTRAINT='butler_calendar_override_floor_origin';
  END IF;
  IF NEW.sequence<=OLD.sequence THEN
    RAISE EXCEPTION 'Calendar override sequence must strictly increase' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_override_transition';
  END IF;
  IF OLD.state='deleted' AND NEW.state='deleted' AND NEW.deleted_at IS DISTINCT FROM OLD.deleted_at THEN
    RAISE EXCEPTION 'A floor-raising delete preserves deleted_at' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_override_transition';
  END IF;
  IF NEW.state='active' AND ser.state<>'active' THEN
    RAISE EXCEPTION 'An active override needs an active series' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_override_series_active';
  END IF;
  IF OLD.state='deleted' AND NEW.state='active' THEN
    SELECT count(*) INTO active_n FROM public.calendar_overrides
      WHERE series_id=NEW.series_id AND state='active';
    IF active_n+1>100 THEN
      RAISE EXCEPTION 'Calendar override limit' USING ERRCODE='23514',
        CONSTRAINT='butler_calendar_override_limit';
    END IF;
  END IF;
  RETURN NEW;
END; $$;

CREATE FUNCTION public.butler_calendar_change_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE src public.calendar_sources; newest integer;
BEGIN
  IF TG_OP='INSERT' THEN
    SELECT * INTO src FROM public.calendar_sources WHERE id=NEW.source_id FOR UPDATE;
    SELECT COALESCE(max(seq),0) INTO newest FROM public.calendar_changes WHERE source_id=NEW.source_id;
    IF src.state IS DISTINCT FROM 'active' OR NEW.seq<>newest+1 THEN
      RAISE EXCEPTION 'Calendar change sequence must be gapless on an unforgotten source'
        USING ERRCODE='23514', CONSTRAINT='butler_calendar_change_seq';
    END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.source_id,NEW.owner_id,NEW.scope_key,NEW.seq,NEW.entity,NEW.series_id,
         NEW.override_id,NEW.operation,NEW.sequence,NEW.cascade_count,NEW.content_hash,NEW.actor_id,
         NEW.sync_run_id,NEW.cursor_after,NEW.applied_at)
    IS NOT DISTINCT FROM ROW(OLD.id,OLD.source_id,OLD.owner_id,OLD.scope_key,OLD.seq,OLD.entity,OLD.series_id,
         OLD.override_id,OLD.operation,OLD.sequence,OLD.cascade_count,OLD.content_hash,OLD.actor_id,
         OLD.sync_run_id,OLD.cursor_after,OLD.applied_at)
    AND NEW.snapshot IS NULL
    AND EXISTS (SELECT 1 FROM public.calendar_sources WHERE id=OLD.source_id AND state='forgotten') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Calendar change history is append-only' USING ERRCODE='23514',
    CONSTRAINT='butler_calendar_change_sealed';
END; $$;

CREATE FUNCTION public.butler_calendar_change_counter() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE applied integer;
BEGIN
  SELECT applied_seq INTO applied FROM public.calendar_sync_state WHERE source_id=NEW.source_id;
  IF applied IS DISTINCT FROM
    (SELECT COALESCE(max(seq),0) FROM public.calendar_changes WHERE source_id=NEW.source_id) THEN
    RAISE EXCEPTION 'Change rows and applied_seq must commit together' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_change_counter';
  END IF;
  RETURN NULL;
END; $$;

CREATE FUNCTION public.butler_calendar_sync_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE src public.calendar_sources; newest integer;
BEGIN
  SELECT * INTO src FROM public.calendar_sources WHERE id=NEW.source_id;
  IF TG_OP='INSERT' THEN
    IF src.state IS DISTINCT FROM 'active' OR NEW.status<>'never' OR NEW.cursor IS NOT NULL
      OR NEW.applied_seq<>0 OR NEW.claim_token IS NOT NULL OR NEW.attempts<>0
      OR NEW.next_attempt_at IS NOT NULL OR NEW.last_attempt_at IS NOT NULL
      OR NEW.last_success_at IS NOT NULL OR NEW.last_error_code IS NOT NULL
      OR NEW.revision<>1 THEN
      RAISE EXCEPTION 'Invalid new calendar sync state' USING ERRCODE='23514',
        CONSTRAINT='butler_calendar_sync_insert';
    END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.source_id,NEW.owner_id,NEW.scope_key)
    IS DISTINCT FROM ROW(OLD.source_id,OLD.owner_id,OLD.scope_key) THEN
    RAISE EXCEPTION 'Calendar sync identity is immutable' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_sync_identity';
  END IF;
  IF OLD.status='blocked' AND OLD.blocked_reason='source_forgotten' THEN
    RAISE EXCEPTION 'A terminal calendar sync state is immutable' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_sync_terminal';
  END IF;
  IF NEW.revision<>OLD.revision+1 OR NEW.updated_at<OLD.updated_at THEN
    RAISE EXCEPTION 'Calendar sync revision must advance by one' USING ERRCODE='23514',
      CONSTRAINT='butler_calendar_sync_revision';
  END IF;
  IF NEW.blocked_reason IS NOT DISTINCT FROM 'source_forgotten' THEN
    -- the forgetting transition: exactly the terminal state, nothing else changed
    IF src.state IS DISTINCT FROM 'forgotten' OR NEW.status<>'blocked'
      OR NEW.cursor IS NOT NULL OR NEW.claim_token IS NOT NULL OR NEW.claim_expires_at IS NOT NULL
      OR NEW.blocked_detail IS NOT NULL OR NEW.next_attempt_at IS NOT NULL
      OR ROW(NEW.applied_seq,NEW.attempts,NEW.last_attempt_at,NEW.last_success_at,NEW.last_error_code)
        IS DISTINCT FROM ROW(OLD.applied_seq,OLD.attempts,OLD.last_attempt_at,OLD.last_success_at,OLD.last_error_code) THEN
      RAISE EXCEPTION 'Invalid forgetting transition of the calendar sync state'
        USING ERRCODE='23514', CONSTRAINT='butler_calendar_sync_forget';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.cursor IS NULL AND OLD.cursor IS NOT NULL THEN
    RAISE EXCEPTION 'The cursor becomes NULL only in the forgetting transition'
      USING ERRCODE='23514', CONSTRAINT='butler_calendar_sync_cursor';
  END IF;
  SELECT COALESCE(max(seq),0) INTO newest FROM public.calendar_changes WHERE source_id=NEW.source_id;
  IF NEW.applied_seq<>newest OR NEW.applied_seq<OLD.applied_seq THEN
    RAISE EXCEPTION 'applied_seq must equal the highest change seq and never decrease'
      USING ERRCODE='23514', CONSTRAINT='butler_calendar_sync_applied_seq';
  END IF;
  IF (NEW.cursor IS DISTINCT FROM OLD.cursor
      OR NEW.last_success_at IS DISTINCT FROM OLD.last_success_at)
    AND NOT (OLD.claim_token IS NOT NULL AND NEW.claim_token IS NULL
      AND NEW.last_success_at IS NOT NULL
      AND (OLD.last_success_at IS NULL OR NEW.last_success_at>OLD.last_success_at)) THEN
    RAISE EXCEPTION 'A cursor or last_success_at change must release a claim and advance last_success_at'
      USING ERRCODE='23514', CONSTRAINT='butler_calendar_sync_cursor';
  END IF;
  IF NEW.attempts<OLD.attempts
    AND NOT (NEW.last_success_at IS DISTINCT FROM OLD.last_success_at
      OR (OLD.status='failed' AND NEW.attempts=0 AND NEW.claim_token IS NOT NULL)) THEN
    RAISE EXCEPTION 'attempts reset only on success or an explicit claim of a failed source'
      USING ERRCODE='23514', CONSTRAINT='butler_calendar_sync_attempts';
  END IF;
  RETURN NEW;
END; $$;

CREATE FUNCTION public.butler_calendar_provider_exclusive() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.calendar_provider_links WHERE source_id=OLD.id) THEN
    RETURN NEW;
  END IF;
  IF OLD.state='active' AND NEW.state='forgotten' AND NEW.data IS NULL
    AND NEW.revision=OLD.revision+1 AND NEW.updated_at>=OLD.updated_at
    AND ROW(NEW.id,NEW.owner_id,NEW.scope_key,NEW.created_at)
      IS NOT DISTINCT FROM ROW(OLD.id,OLD.owner_id,OLD.scope_key,OLD.created_at) THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'A provider-mode calendar source accepts only the forgetting transition'
    USING ERRCODE='23514', CONSTRAINT='butler_calendar_provider_exclusive';
END; $$;

CREATE FUNCTION public.butler_calendar_provider_scrubbed() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.calendar_provider_links WHERE source_id=NEW.id) THEN
    RETURN NULL;
  END IF;
  IF EXISTS (SELECT 1 FROM public.calendar_series WHERE source_id=NEW.id AND (state<>'forgotten' OR uid IS NOT NULL))
    OR EXISTS (SELECT 1 FROM public.calendar_overrides WHERE source_id=NEW.id AND state<>'forgotten')
    OR EXISTS (SELECT 1 FROM public.calendar_changes WHERE source_id=NEW.id AND snapshot IS NOT NULL)
    OR EXISTS (SELECT 1 FROM public.calendar_provider_links WHERE source_id=NEW.id AND provider_ref IS NOT NULL)
    OR NOT EXISTS (SELECT 1 FROM public.calendar_sync_state
      WHERE source_id=NEW.id AND status='blocked' AND blocked_reason='source_forgotten'
        AND cursor IS NULL AND claim_token IS NULL AND claim_expires_at IS NULL
        AND blocked_detail IS NULL AND next_attempt_at IS NULL) THEN
    RAISE EXCEPTION 'A forgotten provider-mode source must be completely scrubbed'
      USING ERRCODE='23514', CONSTRAINT='butler_calendar_provider_scrubbed';
  END IF;
  RETURN NULL;
END; $$;
"""

TRIGGERS = """
CREATE TRIGGER butler_calendar_link_guard BEFORE INSERT OR UPDATE ON public.calendar_provider_links
  FOR EACH ROW EXECUTE FUNCTION public.butler_calendar_link_guard();
CREATE TRIGGER butler_calendar_series_guard BEFORE INSERT OR UPDATE ON public.calendar_series
  FOR EACH ROW EXECUTE FUNCTION public.butler_calendar_series_guard();
CREATE CONSTRAINT TRIGGER butler_calendar_series_orphans AFTER INSERT OR UPDATE ON public.calendar_series
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.state<>'active')
  EXECUTE FUNCTION public.butler_calendar_series_orphans();
CREATE TRIGGER butler_calendar_override_guard BEFORE INSERT OR UPDATE ON public.calendar_overrides
  FOR EACH ROW EXECUTE FUNCTION public.butler_calendar_override_guard();
CREATE TRIGGER butler_calendar_change_guard BEFORE INSERT OR UPDATE ON public.calendar_changes
  FOR EACH ROW EXECUTE FUNCTION public.butler_calendar_change_guard();
CREATE CONSTRAINT TRIGGER butler_calendar_change_counter AFTER INSERT ON public.calendar_changes
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.butler_calendar_change_counter();
CREATE TRIGGER butler_calendar_sync_guard BEFORE INSERT OR UPDATE ON public.calendar_sync_state
  FOR EACH ROW EXECUTE FUNCTION public.butler_calendar_sync_guard();
CREATE TRIGGER butler_calendar_provider_exclusive BEFORE UPDATE ON public.calendar_sources
  FOR EACH ROW EXECUTE FUNCTION public.butler_calendar_provider_exclusive();
CREATE CONSTRAINT TRIGGER butler_calendar_provider_scrubbed AFTER UPDATE ON public.calendar_sources
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
  WHEN (NEW.state='forgotten' AND OLD.state IS DISTINCT FROM 'forgotten')
  EXECUTE FUNCTION public.butler_calendar_provider_scrubbed();
"""

SEALED_TABLES = (
    "calendar_provider_links",
    "calendar_series",
    "calendar_overrides",
    "calendar_changes",
    "calendar_sync_state",
)


def upgrade():
    op.execute(TABLES)
    op.execute(FUNCTIONS)
    op.execute(TRIGGERS)
    for table in SEALED_TABLES:
        op.execute(f"""
        CREATE TRIGGER butler_{table}_sealed BEFORE DELETE ON public.{table}
          FOR EACH ROW EXECUTE FUNCTION public.butler_calendar_provider_sealed();
        CREATE TRIGGER butler_{table}_truncate BEFORE TRUNCATE ON public.{table}
          FOR EACH STATEMENT EXECUTE FUNCTION public.butler_calendar_provider_sealed();
        """)


def downgrade():
    op.execute("DROP TRIGGER butler_calendar_provider_scrubbed ON public.calendar_sources")
    op.execute("DROP TRIGGER butler_calendar_provider_exclusive ON public.calendar_sources")
    op.execute("DROP TABLE public.calendar_changes")
    op.execute("DROP TABLE public.calendar_sync_state")
    op.execute("DROP TABLE public.calendar_overrides")
    op.execute("DROP TABLE public.calendar_series")
    op.execute("DROP TABLE public.calendar_provider_links")
    for function in (
        "butler_calendar_provider_sealed",
        "butler_calendar_link_guard",
        "butler_calendar_series_guard",
        "butler_calendar_series_orphans",
        "butler_calendar_override_guard",
        "butler_calendar_change_guard",
        "butler_calendar_change_counter",
        "butler_calendar_sync_guard",
        "butler_calendar_provider_exclusive",
        "butler_calendar_provider_scrubbed",
    ):
        op.execute(f"DROP FUNCTION public.{function}()")
    op.execute("DROP INDEX public.uq_calendar_source_identity")
