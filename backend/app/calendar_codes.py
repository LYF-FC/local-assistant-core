"""Shared constants, canonical code lists and digests for calendar provider mode (Batch 3).

One module is imported by the recurrence engine, the sync worker, the migration check (as a
copy of the lists, asserted equal by a test) and the tests, so the lists cannot drift.
"""

import hashlib
import struct

# Duration contract shared by the expander, the contract checks and the database checks.
MAX_TIMED_DURATION = 2_678_400  # seconds, 31 days
MAX_ALLDAY_DAYS = 31
GAP_ALLOWANCE_DAYS = 2  # largest offset change between a wall time and its instant, with margin

# Expansion limits (proposal section 9).
MAX_OCCURRENCES = 366
SCAN_LIMIT = 5000
QUERY_HORIZON_DAYS = 400
BRIEFING_HORIZON_DAYS = 7

# Rule and value limits (sections 5 and 9).
RULE_MAX_BYTES = 4096
RULE_TEXT_MAX = 256
EXDATE_MAX = 100
RDATE_MAX = 100
COUNT_MAX = 1000
INTERVAL_MAX = 999

# Per-source and per-series limits (section 9).
ACTIVE_SERIES_MAX = 200
TOTAL_SERIES_MAX = 400
ACTIVE_OVERRIDES_MAX = 100
TOTAL_OVERRIDES_MAX = 200
CHANGE_ROWS_MAX = 5000
PAGE_ITEMS_MAX = 100
PAGE_BYTES_MAX = 64 * 1024
CURSOR_MAX = 512
PAGES_PER_PASS = 10
SOURCES_PER_PASS = 100
LEASE_SECONDS = 120
RETRY_ATTEMPTS_MAX = 5
# Delay after failure n (1-based); the fifth failure is terminal and has no interval.
BACKOFF_SECONDS = (30, 120, 600, 3600)

# Blocked reasons (section 7.3.3): a page or source is refused, no automatic retry.
GRAMMAR_CODES = (
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
)
RELATION_CODES = ("override_unmatched", "override_orphan", "sequence_conflict")
LIMIT_CODES = (
    "series_limit",
    "override_limit",
    "tombstone_limit",
    "change_log_full",
    "page_too_large",
)
CURSOR_CODES = ("cursor_malformed", "cursor_no_progress", "cursor_invalid", "cursor_expired")
TERMINAL_CODES = ("source_forgotten",)
BLOCKED_REASONS = GRAMMAR_CODES + RELATION_CODES + LIMIT_CODES + CURSOR_CODES + TERMINAL_CODES
# Retryable provider failures.
LAST_ERROR_CODES = ("provider_unavailable", "provider_timeout")

# Fixed hash of every delete change row (section 6.4); independent of any content.
TOMBSTONE_HASH = hashlib.sha256(b"butler.calendar.tombstone.v1").hexdigest()


def digest(*fields):
    """First 12 hex characters of SHA-256 over a length-prefixed UTF-8 encoding.

    Each field is a 4-byte big-endian length followed by its UTF-8 bytes, so no two different
    field tuples can produce the same input (raw concatenation is never used).
    """
    encoded = b"".join(
        struct.pack(">I", len(raw)) + raw for raw in (str(f).encode("utf-8") for f in fields)
    )
    return hashlib.sha256(encoded).hexdigest()[:12]


def uid_digest(source_id, uid):
    return digest(source_id, uid)


def recurrence_digest(source_id, uid, recurrence_id):
    return digest(source_id, uid, recurrence_id)
