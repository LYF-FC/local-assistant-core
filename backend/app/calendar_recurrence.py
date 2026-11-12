"""Bounded RFC 5545 recurrence subset behind a project-owned interface (Batch 3, commit 2).

This module is the only importer of ``dateutil``. It uses ``dateutil.rrule.rrule`` built from
validated structured fields over naive wall times; it never uses ``rrulestr``,
``dateutil.parser`` or ``dateutil.tz``. ``COUNT`` and ``UNTIL`` are never passed to dateutil:
the driver below counts instances itself so that nonexistent generated local times are skipped
and do not consume ``COUNT`` (RFC 5545 section 3.3.10), while explicit DATE-TIME values
(``DTSTART``, ``RDATE``, override starts) use the section 3.3.5 interpretation.

Canonical identity: a recurring instance is identified by its original generated wall time in
the series zone (``YYYY-MM-DDTHH:MM:SS``), or ``YYYY-MM-DD`` for all-day series. A series that
is a single event (no rule, no ``RDATE``) keeps the repository's legacy non-recurring form
``""``, so occurrence ids stay ``uuid5(source.id, json.dumps([uid, recurrence_id]))``.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule

from app import calendar_codes as codes

WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
FREQS = {"DAILY": DAILY, "WEEKLY": WEEKLY, "MONTHLY": MONTHLY, "YEARLY": YEARLY}
STATUSES = ("confirmed", "tentative", "cancelled")

_NAMES = {"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY", "BYMONTHDAY", "BYMONTH", "WKST"}
_BY_UNSUPPORTED = {"BYSETPOS", "BYWEEKNO", "BYYEARDAY", "BYHOUR", "BYMINUTE", "BYSECOND"}
_RSCALE = {"RSCALE", "SKIP"}
_FREQ_UNSUPPORTED = {"SECONDLY", "MINUTELY", "HOURLY"}
_INT = re.compile(r"[1-9][0-9]{0,3}")
_ORDINAL = re.compile(r"[+-]?[0-9]+(MO|TU|WE|TH|FR|SA|SU)")
_DATE = re.compile(r"[0-9]{8}")
_DATETIME = re.compile(r"[0-9]{8}T[0-9]{6}")
_UTC = re.compile(r"[0-9]{8}T[0-9]{6}Z")
_WHITESPACE = re.compile(r"\s")

LOOKBACK = timedelta(seconds=codes.MAX_TIMED_DURATION) + timedelta(days=codes.GAP_ALLOWANCE_DAYS)
LOOKAHEAD = timedelta(days=codes.GAP_ALLOWANCE_DAYS)


class RecurrenceError(ValueError):
    """A typed, stable refusal: ``code`` is always a member of ``codes.BLOCKED_REASONS``."""

    def __init__(self, code):
        assert code in codes.BLOCKED_REASONS, code
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------------------------
# Strict boundary grammar (proposal section 5.7)
# ---------------------------------------------------------------------------------------------


def _integer(text, low, high, over):
    if not _INT.fullmatch(text):
        raise RecurrenceError("rrule_syntax")
    value = int(text)
    if value > high:
        raise RecurrenceError(over)
    if value < low:
        raise RecurrenceError("rrule_syntax")
    return value


def _items(text, *, limit=31):
    parts = text.split(",")
    if len(parts) > limit or any(not part for part in parts):
        raise RecurrenceError("rrule_syntax")
    if len(set(parts)) != len(parts):
        raise RecurrenceError("by_list_duplicate")
    return parts


def _until(text):
    if _DATE.fullmatch(text):
        try:
            return datetime.strptime(text, "%Y%m%d").date().isoformat()
        except ValueError:
            raise RecurrenceError("rrule_syntax") from None
    if _UTC.fullmatch(text):
        try:
            value = datetime.strptime(text, "%Y%m%dT%H%M%SZ")
        except ValueError:
            raise RecurrenceError("rrule_syntax") from None
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if _DATETIME.fullmatch(text):
        raise RecurrenceError("zone_floating")
    raise RecurrenceError("rrule_syntax")


def parse_rrule(text):
    """Parse the value of one RRULE property into the structured rule; typed errors only."""
    if (
        not isinstance(text, str)
        or not text
        or len(text) > codes.RULE_TEXT_MAX
        or not text.isascii()
        or _WHITESPACE.search(text)
    ):
        raise RecurrenceError("rrule_syntax")
    seen = {}
    for part in text.split(";"):
        if not part or "=" not in part:
            raise RecurrenceError("rrule_syntax")
        name, value = part.split("=", 1)
        name = name.upper()
        if not name or not value or "=" in value:
            raise RecurrenceError("rrule_syntax")
        if name in _BY_UNSUPPORTED:
            raise RecurrenceError("by_rule_unsupported")
        if name in _RSCALE:
            raise RecurrenceError("rscale_unsupported")
        if name not in _NAMES:
            raise RecurrenceError("rule_part_unknown")
        if name in seen:
            raise RecurrenceError("rule_part_duplicate")
        seen[name] = value
    if "FREQ" not in seen:
        raise RecurrenceError("rrule_syntax")
    freq = seen["FREQ"].upper()
    if freq in _FREQ_UNSUPPORTED:
        raise RecurrenceError("freq_unsupported")
    if freq not in FREQS:
        raise RecurrenceError("rrule_syntax")
    rule = {"freq": freq, "interval": 1, "wkst": "MO"}
    if "INTERVAL" in seen:
        rule["interval"] = _integer(seen["INTERVAL"], 1, codes.INTERVAL_MAX, "interval_limit")
    if "WKST" in seen:
        wkst = seen["WKST"].upper()
        if wkst not in WEEKDAYS:
            raise RecurrenceError("rrule_syntax")
        rule["wkst"] = wkst
    if "COUNT" in seen and "UNTIL" in seen:
        raise RecurrenceError("count_until_both")
    if "COUNT" in seen:
        rule["count"] = _integer(seen["COUNT"], 1, codes.COUNT_MAX, "count_limit")
    if "UNTIL" in seen:
        rule["until"] = _until(seen["UNTIL"])
    if "BYDAY" in seen:
        days = []
        for item in _items(seen["BYDAY"].upper()):
            if _ORDINAL.fullmatch(item):
                raise RecurrenceError("by_day_ordinal")
            if item not in WEEKDAYS:
                raise RecurrenceError("rrule_syntax")
            days.append(item)
        if freq != "WEEKLY":
            raise RecurrenceError("by_day_freq_unsupported")
        rule["by_day"] = sorted(days, key=WEEKDAYS.index)
    if "BYMONTHDAY" in seen:
        numbers = []
        for item in _items(seen["BYMONTHDAY"]):
            if item.startswith("-") and item[1:].isdigit():
                raise RecurrenceError("by_month_day_negative")
            numbers.append(_integer(item, 1, 31, "rrule_syntax"))
        if freq not in {"MONTHLY", "YEARLY"}:
            raise RecurrenceError("by_rule_freq_mismatch")
        rule["by_month_day"] = sorted(numbers)
    if "BYMONTH" in seen:
        months = [_integer(item, 1, 12, "rrule_syntax") for item in _items(seen["BYMONTH"])]
        if freq != "YEARLY":
            raise RecurrenceError("by_rule_freq_mismatch")
        rule["by_month"] = sorted(months)
    return rule


def serialize_rule(rule):
    """Canonical RRULE value text; ``parse_rrule(serialize_rule(rule)) == rule``."""
    parts = [f"FREQ={rule['freq']}", f"INTERVAL={rule['interval']}"]
    if "by_day" in rule:
        parts.append("BYDAY=" + ",".join(rule["by_day"]))
    if "by_month_day" in rule:
        parts.append("BYMONTHDAY=" + ",".join(str(n) for n in rule["by_month_day"]))
    if "by_month" in rule:
        parts.append("BYMONTH=" + ",".join(str(n) for n in rule["by_month"]))
    parts.append(f"WKST={rule['wkst']}")
    if "count" in rule:
        parts.append(f"COUNT={rule['count']}")
    if "until" in rule:
        parts.append("UNTIL=" + rule["until"].replace("-", "").replace(":", ""))
    return ";".join(parts)


# ---------------------------------------------------------------------------------------------
# Zones and local time (proposal sections 5.4 and 5.8)
# ---------------------------------------------------------------------------------------------


def zone_of(name):
    if not isinstance(name, str) or not name.isascii() or not 1 <= len(name) <= 64:
        raise RecurrenceError("zone_unknown")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise RecurrenceError("zone_unknown") from None


def localize(wall, zone):
    """Section 3.3.5: ambiguous -> first occurrence; nonexistent -> offset before the gap."""
    return wall.replace(tzinfo=zone, fold=0).astimezone(UTC)


def exists(wall, zone):
    return localize(wall, zone).astimezone(zone).replace(tzinfo=None) == wall


def wall_id(wall):
    return wall.strftime("%Y-%m-%dT%H:%M:%S")


def _wall(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")


def _wall_of(series, identity):
    """Naive wall datetime of a canonical identity (a date identity means midnight)."""
    return _wall(identity) if series.kind == "timed" else _wall(identity + "T00:00:00")


def _parse_datetime(text, pattern):
    try:
        return datetime.strptime(text, pattern)
    except ValueError:
        raise RecurrenceError("item_malformed") from None


def _parse_date(text):
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        raise RecurrenceError("item_malformed") from None


def _tzid(text):
    """Split ``TZID=<zone>:<value>``; return ``(zone_name | None, value)``."""
    if text.upper().startswith("TZID="):
        name, separator, value = text[5:].partition(":")
        if not separator or not name:
            raise RecurrenceError("item_malformed")
        return name, value
    return None, text


def parse_value(text, *, kind, zone, role):
    """Canonicalize one EXDATE / RDATE / RECURRENCE-ID value to its wall identity.

    ``kind`` is the series kind, ``zone`` the series ``ZoneInfo`` (None for all-day), ``role``
    one of ``exdate``, ``rdate``, ``override``. All-day values are DATE (``YYYYMMDD``); timed
    values are ``TZID=<series zone>:YYYYMMDDTHHMMSS`` or UTC ``YYYYMMDDTHHMMSSZ``. UTC values are
    accepted only if they survive the instant round trip of section 5.8.
    """
    mismatch = f"{role}_type_mismatch"
    if not isinstance(text, str) or not text.isascii() or _WHITESPACE.search(text) or not text:
        raise RecurrenceError("item_malformed")
    name, value = _tzid(text)
    if "/" in value:
        raise RecurrenceError("rdate_period" if role == "rdate" else "item_malformed")
    if kind == "all_day":
        if name is not None or not _DATE.fullmatch(value):
            if _DATETIME.fullmatch(value) or _UTC.fullmatch(value):
                raise RecurrenceError(mismatch)
            raise RecurrenceError("item_malformed")
        return _parse_date(value).isoformat()
    if _DATE.fullmatch(value) and name is None:
        raise RecurrenceError(mismatch)
    if _UTC.fullmatch(value):
        if name is not None:
            raise RecurrenceError("item_malformed")
        instant = _parse_datetime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        wall = instant.astimezone(zone).replace(tzinfo=None)
        if localize(wall, zone) != instant:
            raise RecurrenceError("utc_value_ambiguous")
        return wall_id(wall)
    if _DATETIME.fullmatch(value):
        if name is None:
            raise RecurrenceError("zone_floating")
        if zone_of(name) != zone:
            raise RecurrenceError("zone_mismatch")
        return wall_id(_parse_datetime(value, "%Y%m%dT%H%M%S"))
    raise RecurrenceError("item_malformed")


# ---------------------------------------------------------------------------------------------
# Normalized series and overrides (proposal sections 5.1 to 5.8)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Series:
    kind: str  # timed | all_day
    zone_name: str | None  # IANA name, None for all-day
    start: datetime | date  # naive wall time (timed) or date (all-day)
    duration: int  # seconds (timed) or days (all-day)
    rule: dict | None
    exdates: tuple
    rdates: tuple
    title: str
    status: str

    @property
    def zone(self):
        return ZoneInfo(self.zone_name) if self.zone_name else None

    @property
    def start_wall(self):
        return self.start if self.kind == "timed" else datetime.combine(self.start, time.min)

    @property
    def recurring(self):
        return self.rule is not None or bool(self.rdates)


@dataclass(frozen=True)
class Override:
    recurrence_id: str
    status: str
    start: str | None  # canonical wall identity of the replacement start, or None
    duration: int | None
    title: str | None


def _text(value, low, high):
    if not isinstance(value, str) or not low <= len(value) <= high or not value.strip():
        raise RecurrenceError("item_malformed")
    return value


def _count(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise RecurrenceError("item_malformed")
    return value


def parse_dtstart(text):
    """``YYYYMMDD`` (all-day), ``TZID=<zone>:YYYYMMDDTHHMMSS`` or UTC ``...Z`` (zone UTC)."""
    if not isinstance(text, str) or not text.isascii() or _WHITESPACE.search(text) or not text:
        raise RecurrenceError("item_malformed")
    name, value = _tzid(text)
    if _DATE.fullmatch(value) and name is None:
        return "all_day", None, _parse_date(value)
    if _UTC.fullmatch(value) and name is None:
        return "timed", "UTC", _parse_datetime(value, "%Y%m%dT%H%M%SZ")
    if _DATETIME.fullmatch(value):
        if name is None:
            raise RecurrenceError("zone_floating")
        zone_of(name)
        return "timed", name, _parse_datetime(value, "%Y%m%dT%H%M%S")
    raise RecurrenceError("item_malformed")


def _until_value(rule, series_kind, zone, start):
    """Validate UNTIL's type and position against DTSTART (sections 5.3 and 5.7)."""
    text = rule.get("until")
    if text is None:
        return
    is_date = len(text) == 10
    if is_date != (series_kind == "all_day"):
        raise RecurrenceError("until_type_mismatch")
    if is_date:
        if date.fromisoformat(text) < start:
            raise RecurrenceError("until_before_start")
    else:
        until = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        if until < localize(start, zone):
            raise RecurrenceError("until_before_start")


_BODY_KEYS = {
    "title",
    "status",
    "dtstart",
    "duration",
    "rrule",
    "exdates",
    "rdates",
    "version",
}


def normalize_series(body):
    """Validate one provider series body (untrusted) into a ``Series``; typed errors only."""
    if not isinstance(body, dict) or not set(body) <= _BODY_KEYS:
        raise RecurrenceError("item_malformed")
    title = _text(body.get("title"), 1, 160)
    status = body.get("status", "confirmed")
    if status not in STATUSES:
        raise RecurrenceError("item_malformed")
    kind, zone_name, start = parse_dtstart(body.get("dtstart"))
    if kind == "timed":
        duration = _count(body.get("duration"), 1, codes.MAX_TIMED_DURATION)
    else:
        duration = _count(body.get("duration"), 1, codes.MAX_ALLDAY_DAYS)
    zone = ZoneInfo(zone_name) if zone_name else None
    rule = None
    if body.get("rrule") is not None:
        rule = parse_rrule(body["rrule"])
        _until_value(rule, kind, zone, start)
    exdates = body.get("exdates", [])
    rdates = body.get("rdates", [])
    if not isinstance(exdates, list) or not isinstance(rdates, list):
        raise RecurrenceError("item_malformed")
    if len(exdates) > codes.EXDATE_MAX:
        raise RecurrenceError("exdate_limit")
    if len(rdates) > codes.RDATE_MAX:
        raise RecurrenceError("rdate_limit")
    exdates = tuple(sorted({parse_value(v, kind=kind, zone=zone, role="exdate") for v in exdates}))
    rdates = tuple(sorted({parse_value(v, kind=kind, zone=zone, role="rdate") for v in rdates}))
    series = Series(kind, zone_name, start, duration, rule, exdates, rdates, title, status)
    if rule is not None:
        if len(serialize_rule(rule).encode()) > codes.RULE_MAX_BYTES:
            raise RecurrenceError("rule_too_large")
        if not _synchronized(series):
            raise RecurrenceError("dtstart_not_synchronized")
    return series


_OVERRIDE_KEYS = {"recurrence_id", "status", "start", "duration", "title", "range"}


def normalize_override(body, series):
    """Validate one provider override body against its series' kind and zone."""
    if not isinstance(body, dict) or not set(body) <= _OVERRIDE_KEYS:
        raise RecurrenceError("item_malformed")
    if body.get("range") is not None:
        if isinstance(body["range"], str) and body["range"].upper() == "THISANDFUTURE":
            raise RecurrenceError("range_thisandfuture")
        raise RecurrenceError("item_malformed")
    status = body.get("status", "confirmed")
    if status not in STATUSES:
        raise RecurrenceError("item_malformed")
    zone = series.zone
    rid = parse_value(body.get("recurrence_id"), kind=series.kind, zone=zone, role="override")
    start = body.get("start")
    if start is not None:
        start = parse_value(start, kind=series.kind, zone=zone, role="override")
    duration = body.get("duration")
    if duration is not None:
        high = codes.MAX_TIMED_DURATION if series.kind == "timed" else codes.MAX_ALLDAY_DAYS
        duration = _count(duration, 1, high)
    title = body.get("title")
    if title is not None:
        title = _text(title, 1, 160)
    return Override(rid, status, start, duration, title)


# ---------------------------------------------------------------------------------------------
# Generation: naive wall times, bounded and position independent
# ---------------------------------------------------------------------------------------------


class Scan:
    """Counts candidate wall times examined, so work per series per call stays bounded."""

    def __init__(self, limit):
        self.limit = limit
        self.used = 0
        self.exceeded = False

    def tick(self):
        self.used += 1
        if self.used > self.limit:
            self.exceeded = True
        return not self.exceeded


def _weekday(name):
    return WEEKDAYS.index(name)


def _dateutil_args(series):
    rule = series.rule
    start = series.start_wall
    args = {
        "freq": FREQS[rule["freq"]],
        "interval": rule["interval"],
        "wkst": _weekday(rule["wkst"]),
    }
    if rule["freq"] == "WEEKLY":
        days = rule.get("by_day") or [WEEKDAYS[start.weekday()]]
        args["byweekday"] = [_weekday(d) for d in days]
    elif rule["freq"] == "MONTHLY":
        args["bymonthday"] = rule.get("by_month_day") or [start.day]
    elif rule["freq"] == "YEARLY":
        args["bymonth"] = rule.get("by_month") or [start.month]
        args["bymonthday"] = rule.get("by_month_day") or [start.day]
    return args


def _aligned_start(series, low):
    """First wall of the period at or before ``low``, aligned to the series' own periods.

    The true DTSTART is used while ``low`` is inside the first period; later periods start at
    the beginning of the period so no candidate of that period is dropped by dateutil's own
    DTSTART filter. This makes generation independent of how long ago the series started.
    """
    rule = series.rule
    start = series.start_wall
    interval = rule["interval"]
    clock = start.time()
    if low <= start:
        return start
    if rule["freq"] == "DAILY":
        steps = (low.date() - start.date()).days // interval
        return start + timedelta(days=steps * interval)
    if rule["freq"] == "WEEKLY":
        first = start.date() - timedelta(days=(start.weekday() - _weekday(rule["wkst"])) % 7)
        steps = ((low.date() - first).days // 7) // interval
        if steps == 0:
            return start
        return datetime.combine(first + timedelta(days=7 * interval * steps), clock)
    if rule["freq"] == "MONTHLY":
        months = (low.year * 12 + low.month) - (start.year * 12 + start.month)
        steps = months // interval
        if steps == 0:
            return start
        total = start.year * 12 + start.month - 1 + steps * interval
        return datetime.combine(date(total // 12, total % 12 + 1, 1), clock)
    steps = (low.year - start.year) // interval
    if steps == 0:
        return start
    return datetime.combine(date(start.year + steps * interval, 1, 1), clock)


def _until_cut(series):
    text = (series.rule or {}).get("until")
    if text is None:
        return None
    if series.kind == "all_day":
        return date.fromisoformat(text)
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _synchronized(series):
    """DTSTART itself must be generated by its own rule (never guessed, section 5.7)."""
    first = next(iter(rrule(dtstart=series.start_wall, **_dateutil_args(series))), None)
    return first == series.start_wall


def _generated(series, low, high, scan):
    """Walls generated by the rule within ``[low, high]``, applying COUNT and UNTIL ourselves.

    Yields in ascending order. DTSTART is always the first instance and always counts, even if
    its wall time does not exist; later nonexistent walls are skipped and never counted.
    """
    rule = series.rule
    if rule is None:
        return
    zone = series.zone
    cut = _until_cut(series)
    count = rule.get("count")
    start = series.start_wall
    if count is not None:
        generator = iter(rrule(dtstart=start, **_dateutil_args(series)))
    else:
        generator = iter(rrule(dtstart=_aligned_start(series, low), **_dateutil_args(series)))
    counted = 0
    for wall in generator:
        if not scan.tick():
            return
        first = wall == start
        if not first and series.kind == "timed" and not exists(wall, zone):
            continue
        if cut is not None:
            if series.kind == "all_day":
                if wall.date() > cut:
                    return
            elif localize(wall, zone) > cut:
                return
        counted += 1
        if count is not None and counted > count:
            return
        if wall > high:
            return
        if wall >= low:
            yield wall


def is_member(series, identity):
    """Whether ``identity`` (canonical wall id or date) is in the final instance set (5.8)."""
    wall = _wall_of(series, identity)
    if identity in series.exdates:
        return False
    if wall == series.start_wall or identity in series.rdates:
        return True
    return any(w == wall for w in _generated(series, wall, wall, Scan(codes.SCAN_LIMIT)))


# ---------------------------------------------------------------------------------------------
# Expansion
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryWindow:
    start: datetime  # aware instants of the display range
    end: datetime
    first_date: date  # display dates, end exclusive
    end_date: date


def window_for_days(first_date, days, zone_name):
    zone = ZoneInfo(zone_name)
    last = first_date + timedelta(days=days)
    return QueryWindow(
        datetime.combine(first_date, time.min, zone).astimezone(UTC),
        datetime.combine(last, time.min, zone).astimezone(UTC),
        first_date,
        last,
    )


@dataclass
class Expansion:
    occurrences: list
    cancelled_count: int = 0
    truncated: bool = False
    truncated_reason: str | None = None
    occurrences_at_least: int = 0


def _instant(series, wall, duration):
    zone = series.zone
    start = localize(wall, zone)
    return start, start + timedelta(seconds=duration)


def _occurrence(series, meta, identity, start, end, *, modified, title, status, all_day_zone):
    common = {
        "uid": meta["uid"],
        "recurrence_id": identity if series.recurring else "",
        "sequence": meta.get("sequence", 0),
        "title": title,
        "description": meta.get("description", ""),
        "status": status,
        "recurring": series.recurring,
        "exception": "modified" if modified else "none",
    }
    if series.kind == "timed":
        return {
            "kind": "timed",
            **common,
            "timezone": series.zone_name,
            "start": start.astimezone(UTC).isoformat(),
            "end": end.astimezone(UTC).isoformat(),
        }
    return {
        "kind": "all_day",
        **common,
        "timezone": all_day_zone,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }


def expand(
    series,
    overrides,
    window,
    *,
    meta,
    all_day_zone="UTC",
    max_occurrences=codes.MAX_OCCURRENCES,
    scan_limit=codes.SCAN_LIMIT,
):
    """Occurrences of one series overlapping ``window``; never a silent short result.

    ``overrides`` are the series' active ``Override`` objects (validated at apply time to be
    members of the final instance set). ``meta`` carries ``uid`` and optionally ``sequence`` and
    ``description``. Timed occurrences are placed by instant overlap; all-day occurrences by
    calendar dates (``start_date < window end_date`` and ``end_date > window first_date``).
    """
    result = Expansion([])
    if series.status == "cancelled":
        return result
    scan = Scan(scan_limit)
    timed = series.kind == "timed"
    if timed:
        zone = series.zone
        low = window.start.astimezone(zone).replace(tzinfo=None) - LOOKBACK
        high = window.end.astimezone(zone).replace(tzinfo=None) + LOOKAHEAD
    else:
        low = datetime.combine(window.first_date - timedelta(days=codes.MAX_ALLDAY_DAYS), time.min)
        high = datetime.combine(window.end_date, time.min)

    members = {}
    start_wall = series.start_wall
    if low <= start_wall <= high:
        members[start_wall] = True
    for wall in _generated(series, low, high, scan):
        members[wall] = True
    for text in series.rdates:
        wall = _wall_of(series, text)
        if low <= wall <= high:
            members[wall] = True
    by_id = {o.recurrence_id: o for o in overrides}

    def overlaps(start, end):
        if timed:
            return start < window.end and end > window.start
        return start < window.end_date and end > window.first_date

    def span(wall, duration):
        if timed:
            return _instant(series, wall, duration)
        first = wall.date()
        return first, first + timedelta(days=duration)

    def moved_span(wall, override):
        moved = _wall_of(series, override.start) if override.start else wall
        return span(moved, override.duration or series.duration)

    def modified(identity, override, start, end):
        return _occurrence(
            series,
            meta,
            identity,
            start,
            end,
            modified=True,
            title=override.title or series.title,
            status=override.status,
            all_day_zone=all_day_zone,
        )

    found = []
    for wall in members:
        identity = wall_id(wall) if timed else wall.date().isoformat()
        if identity in series.exdates:
            continue
        override = by_id.get(identity)
        base_start, base_end = span(wall, series.duration)
        if override is None:
            if overlaps(base_start, base_end):
                found.append(
                    _occurrence(
                        series,
                        meta,
                        identity,
                        base_start,
                        base_end,
                        modified=False,
                        title=series.title,
                        status=series.status,
                        all_day_zone=all_day_zone,
                    )
                )
        elif override.status == "cancelled":
            if overlaps(base_start, base_end):
                result.cancelled_count += 1
        else:
            start, end = moved_span(wall, override)
            if overlaps(start, end):
                found.append(modified(identity, override, start, end))
    # An override whose original instant lies outside the candidate range can still move in.
    for identity, override in by_id.items():
        wall = _wall_of(series, identity)
        if wall in members or identity in series.exdates or override.status == "cancelled":
            continue
        start, end = moved_span(wall, override)
        if overlaps(start, end):
            found.append(modified(identity, override, start, end))
    found.sort(key=lambda o: (o["start"] if timed else o["start_date"], o["recurrence_id"]))
    result.occurrences_at_least = len(found)
    if scan.exceeded:
        result.truncated, result.truncated_reason = True, "scan_limit"
    if len(found) > max_occurrences:
        found = found[:max_occurrences]
        result.truncated = True
        result.truncated_reason = result.truncated_reason or "occurrence_limit"
    result.occurrences = found
    return result
