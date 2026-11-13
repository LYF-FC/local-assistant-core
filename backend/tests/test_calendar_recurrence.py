"""Recurrence engine tests: golden cases derived from RFC 5545 text (not from dateutil output)."""

import ast
import json
import random
import string
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo, available_timezones

import pytest

from app import calendar_codes as codes
from app import calendar_recurrence as rec
from app.calendar_recurrence import RecurrenceError

APP = Path(__file__).resolve().parents[1] / "app"


def series(dtstart, rrule=None, *, duration=3600, **extra):
    return rec.normalize_series(
        {"title": "Synthetic", "dtstart": dtstart, "duration": duration, "rrule": rrule, **extra}
    )


def paris(wall, rrule=None, **extra):
    return series(f"TZID=Europe/Paris:{wall}", rrule, **extra)


def expand(s, first, last, zone="Europe/Paris", overrides=(), **limits):
    days = (date.fromisoformat(last) - date.fromisoformat(first)).days
    window = rec.window_for_days(date.fromisoformat(first), days, zone)
    return rec.expand(
        s, list(overrides), window, meta={"uid": "synthetic-series", "sequence": 3}, **limits
    )


def ids(s, first, last, **kw):
    return [o["recurrence_id"] for o in expand(s, first, last, **kw).occurrences]


def starts(s, first, last, **kw):
    return [o["start"] for o in expand(s, first, last, **kw).occurrences]


def utc(text):
    return datetime.fromisoformat(text).astimezone(UTC).isoformat()


def refused(code, call, *args, **kwargs):
    with pytest.raises(RecurrenceError) as caught:
        call(*args, **kwargs)
    assert caught.value.code == code


# ---------------------------------------------------------------------------------------------
# Strict grammar (section 5.7): one case per rule, each asserting its specific code
# ---------------------------------------------------------------------------------------------

GRAMMAR = [
    ("", "rrule_syntax"),
    ("FREQ=DAILY;", "rrule_syntax"),
    (";FREQ=DAILY", "rrule_syntax"),
    ("FREQ=DAILY;;INTERVAL=2", "rrule_syntax"),
    ("FREQ=DAILY;INTERVAL=", "rrule_syntax"),
    ("FREQ=DAILY;INTERVAL", "rrule_syntax"),
    ("FREQ=DAILY; INTERVAL=2", "rrule_syntax"),
    ("FREQ=DAILY;INTERVAL=2\n", "rrule_syntax"),
    ("FREQ=DAILY;INTERVAL=２", "rrule_syntax"),
    ("FREQ=DAILY;INTERVAL=02", "rrule_syntax"),
    ("FREQ=DAILY;INTERVAL=+2", "rrule_syntax"),
    ("FREQ=DAILY;INTERVAL=-2", "rrule_syntax"),
    ("FREQ=DAILY;INTERVAL=0", "rrule_syntax"),
    ("FREQ=DAILY;INTERVAL=10000", "rrule_syntax"),
    ("FREQ=DAILY;INTERVAL=1000", "interval_limit"),
    ("FREQ=DAILY;COUNT=0", "rrule_syntax"),
    ("FREQ=DAILY;COUNT=1001", "count_limit"),
    ("FREQ=DAILY;FREQ=WEEKLY", "rule_part_duplicate"),
    ("freq=daily;Freq=daily", "rule_part_duplicate"),
    ("FREQ=DAILY;X-FOO=1", "rule_part_unknown"),
    ("FREQ=DAILY;BOGUS=1", "rule_part_unknown"),
    ("FREQ=DAILY;BYSETPOS=1", "by_rule_unsupported"),
    ("FREQ=DAILY;BYWEEKNO=1", "by_rule_unsupported"),
    ("FREQ=DAILY;BYYEARDAY=1", "by_rule_unsupported"),
    ("FREQ=DAILY;BYHOUR=1", "by_rule_unsupported"),
    ("FREQ=DAILY;BYMINUTE=1", "by_rule_unsupported"),
    ("FREQ=DAILY;BYSECOND=1", "by_rule_unsupported"),
    ("FREQ=DAILY;RSCALE=GREGORIAN", "rscale_unsupported"),
    ("FREQ=DAILY;SKIP=OMIT", "rscale_unsupported"),
    ("FREQ=SECONDLY", "freq_unsupported"),
    ("FREQ=MINUTELY", "freq_unsupported"),
    ("FREQ=HOURLY", "freq_unsupported"),
    ("FREQ=FORTNIGHTLY", "rrule_syntax"),
    ("INTERVAL=2", "rrule_syntax"),
    ("FREQ=DAILY;COUNT=3;UNTIL=20260301", "count_until_both"),
    ("FREQ=WEEKLY;BYDAY=1MO", "by_day_ordinal"),
    ("FREQ=WEEKLY;BYDAY=-1FR", "by_day_ordinal"),
    ("FREQ=WEEKLY;BYDAY=+1MO", "by_day_ordinal"),
    ("FREQ=WEEKLY;BYDAY=MO,MO", "by_list_duplicate"),
    ("FREQ=WEEKLY;BYDAY=MO,,TU", "rrule_syntax"),
    ("FREQ=WEEKLY;BYDAY=XX", "rrule_syntax"),
    ("FREQ=DAILY;BYDAY=MO", "by_day_freq_unsupported"),
    ("FREQ=MONTHLY;BYDAY=MO", "by_day_freq_unsupported"),
    ("FREQ=MONTHLY;BYMONTHDAY=-1", "by_month_day_negative"),
    ("FREQ=MONTHLY;BYMONTHDAY=0", "rrule_syntax"),
    ("FREQ=MONTHLY;BYMONTHDAY=32", "rrule_syntax"),
    ("FREQ=MONTHLY;BYMONTHDAY=+1", "rrule_syntax"),
    ("FREQ=MONTHLY;BYMONTHDAY=1,1", "by_list_duplicate"),
    ("FREQ=WEEKLY;BYMONTHDAY=1", "by_rule_freq_mismatch"),
    ("FREQ=DAILY;BYMONTHDAY=1", "by_rule_freq_mismatch"),
    ("FREQ=MONTHLY;BYMONTH=1", "by_rule_freq_mismatch"),
    ("FREQ=YEARLY;BYMONTH=13", "rrule_syntax"),
    ("FREQ=YEARLY;BYMONTH=0", "rrule_syntax"),
    ("FREQ=WEEKLY;WKST=XX", "rrule_syntax"),
    ("FREQ=WEEKLY;WKST=MO,TU", "rrule_syntax"),
    ("FREQ=DAILY;UNTIL=20261301", "rrule_syntax"),
    ("FREQ=DAILY;UNTIL=20260230", "rrule_syntax"),
    ("FREQ=DAILY;UNTIL=2026-01-01", "rrule_syntax"),
    ("FREQ=DAILY;UNTIL=20260101T000000", "zone_floating"),
    ("FREQ=DAILY;UNTIL=20260101T240000Z", "rrule_syntax"),
    ("FREQ=DAILY;UNTIL=20260101T000060Z", "rrule_syntax"),
    ("FREQ=DAILY;UNTIL=20260101T0000Z", "rrule_syntax"),
    ("FREQ=DAILY;" + "X" * 260, "rrule_syntax"),
    ("FREQ=DAILY;A=B=C", "rrule_syntax"),
    ("=DAILY", "rrule_syntax"),
]


@pytest.mark.parametrize(("text", "code"), GRAMMAR)
def test_grammar_rejects_with_the_specific_code(text, code):
    refused(code, rec.parse_rrule, text)


def test_grammar_rejects_lists_over_31_items_and_non_strings():
    refused("rrule_syntax", rec.parse_rrule, "FREQ=MONTHLY;BYMONTHDAY=" + ",".join(["1"] * 32))
    refused("rrule_syntax", rec.parse_rrule, None)
    refused("rrule_syntax", rec.parse_rrule, b"FREQ=DAILY")


def test_grammar_is_case_insensitive_and_normalizes():
    rule = rec.parse_rrule("freq=weekly;byday=we,mo;wkst=su;interval=2;until=20260430T100000Z")
    assert rule == {
        "freq": "WEEKLY",
        "interval": 2,
        "wkst": "SU",
        "by_day": ["MO", "WE"],
        "until": "2026-04-30T10:00:00Z",
    }
    assert rec.parse_rrule("FREQ=DAILY") == {"freq": "DAILY", "interval": 1, "wkst": "MO"}


VALID_RULES = [
    "FREQ=DAILY",
    "FREQ=DAILY;INTERVAL=999;COUNT=1000",
    "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;WKST=SU",
    "FREQ=MONTHLY;BYMONTHDAY=1,15,31;UNTIL=20301231",
    "FREQ=YEARLY;BYMONTH=1,12;BYMONTHDAY=31;UNTIL=20301231T235959Z",
    "FREQ=YEARLY;INTERVAL=2;COUNT=5",
]


@pytest.mark.parametrize("text", VALID_RULES)
def test_parse_serialize_round_trip(text):
    rule = rec.parse_rrule(text)
    assert rec.parse_rrule(rec.serialize_rule(rule)) == rule
    assert rec.serialize_rule(rule) == rec.serialize_rule(rec.parse_rrule(rec.serialize_rule(rule)))


def test_a_maximal_rule_stays_far_below_the_stored_size_bound():
    rule = rec.parse_rrule(
        "FREQ=YEARLY;INTERVAL=999;BYMONTH=1,2,3,4,5,6,7,8,9,10,11,12;"
        "BYMONTHDAY=" + ",".join(str(n) for n in range(1, 32)) + ";WKST=SU;UNTIL=20301231T235959Z"
    )
    assert len(json.dumps(rule).encode()) < codes.RULE_MAX_BYTES


def test_parser_is_total_under_a_bounded_fuzz():
    generator = random.Random(20261112)
    alphabet = string.ascii_letters + string.digits + ";=,-+ \t\n２é" + "FREQ=DAILY"
    for _ in range(3000):
        text = "".join(generator.choice(alphabet) for _ in range(generator.randint(0, 80)))
        try:
            rule = rec.parse_rrule(text)
        except RecurrenceError as error:
            assert error.code in codes.BLOCKED_REASONS
        else:
            assert rec.parse_rrule(rec.serialize_rule(rule)) == rule
    seeded = ["FREQ=DAILY;" + generator.choice(["COUNT=3", "UNTIL=20260101", "BYDAY=MO"])]
    for text in seeded * 50:
        try:
            rec.parse_rrule(text)
        except RecurrenceError as error:
            assert error.code in codes.BLOCKED_REASONS


# ---------------------------------------------------------------------------------------------
# Boundary rejections of a whole series or override body (section 5.3)
# ---------------------------------------------------------------------------------------------


def body(**changes):
    return {
        "title": "Synthetic",
        "dtstart": "TZID=Europe/Paris:20260315T023000",
        "duration": 3600,
        "rrule": "FREQ=WEEKLY;COUNT=4",
        **changes,
    }


SERIES_REFUSALS = [
    (body(rrule="FREQ=WEEKLY;UNTIL=20260320"), "until_type_mismatch"),
    (
        body(dtstart="20260315", duration=1, rrule="FREQ=WEEKLY;UNTIL=20260316T000000Z"),
        "until_type_mismatch",
    ),
    (body(rrule="FREQ=WEEKLY;UNTIL=20260301T000000Z"), "until_before_start"),
    (
        body(dtstart="20260315", duration=1, rrule="FREQ=WEEKLY;UNTIL=20260301"),
        "until_before_start",
    ),
    (body(rrule="FREQ=WEEKLY;BYDAY=MO"), "dtstart_not_synchronized"),
    (body(rrule="FREQ=MONTHLY;BYMONTHDAY=20"), "dtstart_not_synchronized"),
    (body(rrule="FREQ=YEARLY;BYMONTH=5"), "dtstart_not_synchronized"),
    (
        body(dtstart="TZID=Europe/Paris:20260315T023000", exdates=["20260322"]),
        "exdate_type_mismatch",
    ),
    (body(dtstart="20260315", duration=1, exdates=["20260322T023000Z"]), "exdate_type_mismatch"),
    (body(rdates=["20260322"]), "rdate_type_mismatch"),
    (body(rdates=["TZID=Europe/Paris:20260322T023000/PT1H"]), "rdate_period"),
    (body(exdates=["TZID=Asia/Tokyo:20260322T023000"]), "zone_mismatch"),
    (body(exdates=["20260322T023000"]), "zone_floating"),
    (body(dtstart="20260315T023000"), "zone_floating"),
    (body(dtstart="TZID=Mars/Olympus:20260315T023000"), "zone_unknown"),
    (body(exdates=["TZID=Mars/Olympus:20260322T023000"]), "zone_unknown"),
    (body(exdates=["20261025T013000Z"]), "utc_value_ambiguous"),
    (body(exdates=["20260230T023000Z"]), "item_malformed"),
    (body(exdates=["TZID=Europe/Paris:20260322"]), "item_malformed"),
    (body(exdates=[["nested"]]), "item_malformed"),
    (
        body(exdates=[f"TZID=Europe/Paris:2026{m:02d}01T020000" for m in range(1, 13)] * 9),
        "exdate_limit",
    ),
    (
        body(
            rdates=[
                f"TZID=Europe/Paris:2027{m:02d}{d:02d}T020000"
                for m in range(1, 13)
                for d in range(1, 10)
            ]
        ),
        "rdate_limit",
    ),
    (body(duration=0), "item_malformed"),
    (body(duration=codes.MAX_TIMED_DURATION + 1), "item_malformed"),
    (body(duration="3600"), "item_malformed"),
    (body(duration=True), "item_malformed"),
    (body(dtstart="20260315", duration=32), "item_malformed"),
    (body(title=""), "item_malformed"),
    (body(title="x" * 161), "item_malformed"),
    (body(status="maybe"), "item_malformed"),
    (body(unexpected="field"), "item_malformed"),
    (body(rrule="FREQ=HOURLY"), "freq_unsupported"),
    ("not-an-object", "item_malformed"),
    (None, "item_malformed"),
]


@pytest.mark.parametrize(("value", "code"), SERIES_REFUSALS)
def test_series_boundary_refuses_with_the_specific_code(value, code):
    refused(code, rec.normalize_series, value)


def test_override_boundary_refusals():
    s = paris("20260315T023000", "FREQ=WEEKLY;COUNT=4")
    ok = {"recurrence_id": "TZID=Europe/Paris:20260322T023000"}
    assert rec.normalize_override(ok, s).recurrence_id == "2026-03-22T02:30:00"
    cases = [
        ({**ok, "range": "THISANDFUTURE"}, "range_thisandfuture"),
        ({**ok, "range": "thisandfuture"}, "range_thisandfuture"),
        ({**ok, "range": "THISONLY"}, "item_malformed"),
        ({"recurrence_id": "20260322"}, "override_type_mismatch"),
        ({"recurrence_id": "20260322T023000"}, "zone_floating"),
        ({"recurrence_id": "TZID=Asia/Tokyo:20260322T023000"}, "zone_mismatch"),
        ({"recurrence_id": "20261025T013000Z"}, "utc_value_ambiguous"),
        ({**ok, "start": "20260322"}, "override_type_mismatch"),
        ({**ok, "status": "maybe"}, "item_malformed"),
        ({**ok, "duration": 0}, "item_malformed"),
        ({**ok, "title": " "}, "item_malformed"),
        ({**ok, "bogus": 1}, "item_malformed"),
        ({}, "item_malformed"),
        ("x", "item_malformed"),
    ]
    for value, code in cases:
        refused(code, rec.normalize_override, value, s)
    all_day = series("20260315", "FREQ=WEEKLY;COUNT=4", duration=1)
    refused(
        "override_type_mismatch",
        rec.normalize_override,
        {"recurrence_id": "TZID=Europe/Paris:20260322T023000"},
        all_day,
    )
    assert rec.normalize_override({"recurrence_id": "20260322"}, all_day).recurrence_id == (
        "2026-03-22"
    )


# ---------------------------------------------------------------------------------------------
# Golden cases per construct (RFC 5545 section 3.3.10 examples, adapted)
# ---------------------------------------------------------------------------------------------


def test_daily_interval_count():
    s = paris("20260301T090000", "FREQ=DAILY;INTERVAL=2;COUNT=4")
    assert ids(s, "2026-02-01", "2026-04-01") == [f"2026-03-0{n}T09:00:00" for n in (1, 3, 5, 7)]


def test_weekly_by_day_with_wkst_rfc_examples():
    # RFC 5545: DTSTART 1997-08-05, FREQ=WEEKLY;INTERVAL=2;COUNT=4;BYDAY=TU,SU
    base = series(
        "TZID=America/New_York:19970805T090000",
        "FREQ=WEEKLY;INTERVAL=2;COUNT=4;BYDAY=TU,SU;WKST=MO",
    )
    got = ids(base, "1997-08-01", "1997-10-01", zone="America/New_York")
    assert got == [f"1997-08-{d}T09:00:00" for d in ("05", "10", "19", "24")]
    base = series(
        "TZID=America/New_York:19970805T090000",
        "FREQ=WEEKLY;INTERVAL=2;COUNT=4;BYDAY=TU,SU;WKST=SU",
    )
    got = ids(base, "1997-08-01", "1997-10-01", zone="America/New_York")
    assert got == [f"1997-08-{d}T09:00:00" for d in ("05", "17", "19", "31")]


def test_weekly_without_byday_uses_the_dtstart_weekday():
    s = paris("20260303T090000", "FREQ=WEEKLY;COUNT=3")  # a Tuesday
    assert ids(s, "2026-03-01", "2026-04-30") == [
        "2026-03-03T09:00:00",
        "2026-03-10T09:00:00",
        "2026-03-17T09:00:00",
    ]


def test_monthly_by_month_day_and_implicit_day_skip_invalid_dates():
    s = series("20260131", "FREQ=MONTHLY;COUNT=4", duration=1)
    assert ids(s, "2026-01-01", "2026-12-31") == [
        "2026-01-31",
        "2026-03-31",
        "2026-05-31",
        "2026-07-31",
    ]
    s = series("20260101", "FREQ=MONTHLY;BYMONTHDAY=1,15,31;COUNT=7", duration=1)
    assert ids(s, "2026-01-01", "2026-12-31") == [
        "2026-01-01",
        "2026-01-15",
        "2026-01-31",
        "2026-02-01",
        "2026-02-15",
        "2026-03-01",
        "2026-03-15",
    ]


def test_yearly_by_month_rfc_example_and_february_29():
    # RFC 5545: every other year on January, February and March, 10 occurrences.
    s = series("19970310", "FREQ=YEARLY;INTERVAL=2;COUNT=10;BYMONTH=1,2,3", duration=1)
    assert ids(s, "1997-01-01", "2004-01-01") == [
        "1997-03-10",
        "1999-01-10",
        "1999-02-10",
        "1999-03-10",
        "2001-01-10",
        "2001-02-10",
        "2001-03-10",
        "2003-01-10",
        "2003-02-10",
        "2003-03-10",
    ]
    leap = series("20240229", "FREQ=YEARLY;COUNT=3", duration=1)
    assert ids(leap, "2024-01-01", "2036-01-01") == ["2024-02-29", "2028-02-29", "2032-02-29"]


def test_until_date_is_inclusive_and_utc_until_compares_instants():
    s = series("20260301", "FREQ=DAILY;UNTIL=20260303", duration=1)
    assert ids(s, "2026-03-01", "2026-03-10") == ["2026-03-01", "2026-03-02", "2026-03-03"]
    # 09:00 Paris is 08:00Z in March before the change: UNTIL is inclusive of an equal instant.
    inclusive = paris("20260301T090000", "FREQ=DAILY;UNTIL=20260303T080000Z")
    assert ids(inclusive, "2026-03-01", "2026-03-10")[-1] == "2026-03-03T09:00:00"
    exclusive = paris("20260301T090000", "FREQ=DAILY;UNTIL=20260303T075959Z")
    assert ids(exclusive, "2026-03-01", "2026-03-10")[-1] == "2026-03-02T09:00:00"


def test_open_ended_series_far_in_the_past_expands_in_a_bounded_window():
    s = paris("20000101T090000", "FREQ=DAILY;INTERVAL=3")
    result = expand(s, "2026-06-01", "2026-06-10")
    assert [o["recurrence_id"] for o in result.occurrences] == [
        "2026-06-01T09:00:00",
        "2026-06-04T09:00:00",
        "2026-06-07T09:00:00",
    ]
    assert not result.truncated


@pytest.mark.parametrize(
    ("start", "text"),
    [
        ("20200302", "FREQ=WEEKLY;BYDAY=MO,WE;INTERVAL=2;WKST=SU"),
        ("20200302", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR,SA,SU;INTERVAL=3;WKST=WE"),
        ("20200101", "FREQ=MONTHLY;BYMONTHDAY=1,31;INTERVAL=3"),
        ("20200131", "FREQ=MONTHLY;BYMONTHDAY=29,30,31;INTERVAL=2"),
        ("20200315", "FREQ=YEARLY;BYMONTH=3,9;BYMONTHDAY=15;INTERVAL=2"),
        ("20200302", "FREQ=DAILY;INTERVAL=7"),
    ],
)
def test_aligned_generation_equals_generation_from_the_original_dtstart(start, text):
    """The position-independent shortcut must give exactly the walls a full scan gives."""
    from dateutil.rrule import rrule

    s = series(start, text, duration=1)
    first, last = date(2026, 2, 1), date(2026, 12, 31)
    window = rec.window_for_days(first, (last - first).days, "UTC")
    short = [o["recurrence_id"] for o in rec.expand(s, [], window, meta={"uid": "u"}).occurrences]
    full = [
        w.date().isoformat()
        for w in rrule(dtstart=s.start_wall, **rec._dateutil_args(s))
        if first <= w.date() < last
    ]
    assert short == full and short


def test_exdate_and_rdate_set_algebra():
    s = paris(
        "20260301T090000",
        "FREQ=DAILY;COUNT=4",
        exdates=["TZID=Europe/Paris:20260302T090000"],
        rdates=["TZID=Europe/Paris:20260310T090000", "TZID=Europe/Paris:20260303T090000"],
    )
    # EXDATE removes one generated instance; RDATE adds one and duplicates collapse.
    assert ids(s, "2026-03-01", "2026-03-31") == [
        "2026-03-01T09:00:00",
        "2026-03-03T09:00:00",
        "2026-03-04T09:00:00",
        "2026-03-10T09:00:00",
    ]
    # EXDATE wins over RDATE.
    both = paris(
        "20260301T090000",
        None,
        exdates=["TZID=Europe/Paris:20260310T090000"],
        rdates=["TZID=Europe/Paris:20260310T090000"],
    )
    assert ids(both, "2026-03-01", "2026-03-31") == ["2026-03-01T09:00:00"]
    # An EXDATE that matches nothing is harmless.
    stray = paris("20260301T090000", "FREQ=DAILY;COUNT=2", exdates=["20261231T000000Z"])
    assert len(ids(stray, "2026-03-01", "2026-03-31")) == 2


def test_exdate_of_dtstart_still_counts_as_the_first_instance():
    s = paris(
        "20260301T090000", "FREQ=DAILY;COUNT=3", exdates=["TZID=Europe/Paris:20260301T090000"]
    )
    assert ids(s, "2026-03-01", "2026-03-31") == ["2026-03-02T09:00:00", "2026-03-03T09:00:00"]


def test_rdate_never_consumes_count():
    s = paris("20260301T090000", "FREQ=DAILY;COUNT=2", rdates=["TZID=Europe/Paris:20260320T090000"])
    assert ids(s, "2026-03-01", "2026-03-31") == [
        "2026-03-01T09:00:00",
        "2026-03-02T09:00:00",
        "2026-03-20T09:00:00",
    ]


def test_all_day_series_use_date_values_only():
    s = series(
        "20260305", "FREQ=DAILY;COUNT=3", duration=2, exdates=["20260306"], rdates=["20260320"]
    )
    result = expand(s, "2026-03-01", "2026-03-31", zone="Europe/Paris")
    assert [(o["start_date"], o["end_date"]) for o in result.occurrences] == [
        ("2026-03-05", "2026-03-07"),
        ("2026-03-07", "2026-03-09"),
        ("2026-03-20", "2026-03-22"),
    ]
    assert all(o["kind"] == "all_day" and o["timezone"] == "UTC" for o in result.occurrences)


# ---------------------------------------------------------------------------------------------
# Section 5.4 worked examples as executable tests
# ---------------------------------------------------------------------------------------------


def test_example_1_generated_instance_in_the_gap_is_skipped_and_not_counted():
    s = paris("20260315T023000", "FREQ=WEEKLY;COUNT=4")
    result = expand(s, "2026-03-01", "2026-05-01")
    assert [o["recurrence_id"] for o in result.occurrences] == [
        "2026-03-15T02:30:00",
        "2026-03-22T02:30:00",
        "2026-04-05T02:30:00",
        "2026-04-12T02:30:00",
    ]
    assert [o["start"] for o in result.occurrences] == [
        "2026-03-15T01:30:00+00:00",
        "2026-03-22T01:30:00+00:00",
        "2026-04-05T00:30:00+00:00",
        "2026-04-12T00:30:00+00:00",
    ]
    # The wrong behaviours: a shifted 03:30 instance on 29 March, or a consumed COUNT.
    assert "2026-03-29T02:30:00" not in ids(s, "2026-03-01", "2026-05-01")
    assert not any(o["start"].startswith("2026-03-29") for o in result.occurrences)
    assert len(result.occurrences) == 4


def test_example_2_explicit_dtstart_in_the_gap_counts_and_uses_the_pre_gap_offset():
    s = paris("20260329T023000", "FREQ=WEEKLY;COUNT=3")
    result = expand(s, "2026-03-01", "2026-05-01")
    assert [o["recurrence_id"] for o in result.occurrences] == [
        "2026-03-29T02:30:00",
        "2026-04-05T02:30:00",
        "2026-04-12T02:30:00",
    ]
    assert result.occurrences[0]["start"] == "2026-03-29T01:30:00+00:00"
    assert result.occurrences[0]["end"] == "2026-03-29T02:30:00+00:00"


def test_example_3_ambiguous_generated_time_takes_the_first_occurrence():
    s = paris("20261018T023000", "FREQ=WEEKLY;COUNT=3")
    assert starts(s, "2026-10-01", "2026-11-30") == [
        "2026-10-18T00:30:00+00:00",
        "2026-10-25T00:30:00+00:00",
        "2026-11-01T01:30:00+00:00",
    ]


def test_example_4_rdate_in_the_gap_uses_the_explicit_interpretation_and_is_not_counted():
    s = paris(
        "20260315T023000",
        "FREQ=WEEKLY;COUNT=4",
        rdates=["TZID=Europe/Paris:20260329T023000"],
    )
    result = expand(s, "2026-03-01", "2026-05-01")
    got = {o["recurrence_id"]: o["start"] for o in result.occurrences}
    assert got["2026-03-29T02:30:00"] == "2026-03-29T01:30:00+00:00"
    assert len(got) == 5  # four counted instances (the gap one skipped) plus the RDATE


def test_example_5_override_moved_into_the_gap_and_naming_the_skipped_instance():
    s = paris("20260315T023000", "FREQ=WEEKLY;COUNT=4")
    moved = rec.normalize_override(
        {
            "recurrence_id": "TZID=Europe/Paris:20260405T023000",
            "start": "TZID=Europe/Paris:20260329T023000",
        },
        s,
    )
    got = {
        o["recurrence_id"]: o
        for o in expand(s, "2026-03-01", "2026-05-01", overrides=[moved]).occurrences
    }
    assert got["2026-04-05T02:30:00"]["start"] == "2026-03-29T01:30:00+00:00"
    assert got["2026-04-05T02:30:00"]["exception"] == "modified"
    # The identity of the moved instance is still its original wall time, and the skipped
    # generated instance is not a member, so an override naming it can never match.
    assert rec.is_member(s, "2026-04-05T02:30:00")
    assert not rec.is_member(s, "2026-03-29T02:30:00")


# ---------------------------------------------------------------------------------------------
# DST matrix: nonexistent, ambiguous, crossing, all-day and duration across the change
# ---------------------------------------------------------------------------------------------

MATRIX = [
    # zone, gap wall, instant of the gap wall (pre-gap offset), fold wall, first instant
    (
        "Europe/Paris",
        "2026-03-29T02:30:00",
        "2026-03-29T01:30:00+00:00",
        "2026-10-25T02:30:00",
        "2026-10-25T00:30:00+00:00",
    ),
    (
        "America/New_York",
        "2026-03-08T02:30:00",
        "2026-03-08T07:30:00+00:00",
        "2026-11-01T01:30:00",
        "2026-11-01T05:30:00+00:00",
    ),
    (
        "Australia/Lord_Howe",
        "2026-10-04T02:15:00",
        "2026-10-03T15:45:00+00:00",
        "2026-04-05T01:45:00",
        "2026-04-04T14:45:00+00:00",
    ),
]


@pytest.mark.parametrize(("zone", "gap", "gap_instant", "fold", "fold_instant"), MATRIX)
def test_dst_matrix_explicit_gap_and_ambiguous_values(zone, gap, gap_instant, fold, fold_instant):
    compact = lambda w: w.replace("-", "").replace(":", "")
    gap_series = series(f"TZID={zone}:{compact(gap)}", None)
    only = expand(
        gap_series,
        gap[:10],
        (date.fromisoformat(gap[:10]) + timedelta(days=2)).isoformat(),
        zone=zone,
    )
    assert [o["start"] for o in only.occurrences] == [gap_instant]
    assert [o["recurrence_id"] for o in only.occurrences] == [""]  # single event, legacy form
    fold_series = series(f"TZID={zone}:{compact(fold)}", None)
    first = expand(
        fold_series,
        fold[:10],
        (date.fromisoformat(fold[:10]) + timedelta(days=2)).isoformat(),
        zone=zone,
    )
    assert [o["start"] for o in first.occurrences] == [fold_instant]


@pytest.mark.parametrize(
    ("zone", "start", "count", "skipped"),
    [
        ("Europe/Paris", "20260322T023000", 3, "2026-03-29T02:30:00"),
        ("America/New_York", "20260301T023000", 8, "2026-03-08T02:30:00"),
    ],
)
def test_dst_matrix_weekly_series_across_the_gap_skip_without_consuming_count(
    zone, start, count, skipped
):
    s = series(f"TZID={zone}:{start}", f"FREQ=WEEKLY;COUNT={count}")
    got = ids(s, "2026-02-25", "2026-06-01", zone=zone)
    assert skipped not in got and len(got) == count


def test_dst_matrix_lord_howe_half_hour_gap_and_fold():
    zone = "Australia/Lord_Howe"
    gap = series(f"TZID={zone}:20260927T021500", "FREQ=WEEKLY;COUNT=3")
    got = {
        o["recurrence_id"]: o["start"]
        for o in expand(gap, "2026-09-20", "2026-11-01", zone=zone).occurrences
    }
    assert "2026-10-04T02:15:00" not in got and len(got) == 3
    assert got["2026-10-11T02:15:00"] == "2026-10-10T15:15:00+00:00"  # +11:00 after the change
    fold = series(f"TZID={zone}:20260329T014500", "FREQ=WEEKLY;COUNT=3")
    got = [o["start"] for o in expand(fold, "2026-03-25", "2026-04-20", zone=zone).occurrences]
    assert got[1] == "2026-04-04T14:45:00+00:00"  # first occurrence of the repeated 01:45


def test_dst_matrix_apia_skipped_day_is_not_generated():
    zone = "Pacific/Apia"
    s = series(f"TZID={zone}:20111228T100000", "FREQ=DAILY;COUNT=5")
    got = ids(s, "2011-12-26", "2012-01-10", zone=zone)
    assert got == [
        "2011-12-28T10:00:00",
        "2011-12-29T10:00:00",
        "2011-12-31T10:00:00",
        "2012-01-01T10:00:00",
        "2012-01-02T10:00:00",
    ]


def test_timed_series_crossing_the_change_keeps_wall_time_and_exact_duration():
    s = paris("20260327T090000", "FREQ=DAILY;COUNT=4", duration=5400)
    got = expand(s, "2026-03-26", "2026-04-05").occurrences
    assert [(o["start"], o["end"]) for o in got] == [
        ("2026-03-27T08:00:00+00:00", "2026-03-27T09:30:00+00:00"),
        ("2026-03-28T08:00:00+00:00", "2026-03-28T09:30:00+00:00"),
        ("2026-03-29T07:00:00+00:00", "2026-03-29T08:30:00+00:00"),
        ("2026-03-30T07:00:00+00:00", "2026-03-30T08:30:00+00:00"),
    ]


def test_duration_is_exact_seconds_across_the_change():
    s = paris("20260328T220000", None, duration=4 * 3600)
    (o,) = expand(s, "2026-03-28", "2026-03-31").occurrences
    assert o["start"] == "2026-03-28T21:00:00+00:00" and o["end"] == "2026-03-29T01:00:00+00:00"


def test_all_day_series_ignore_the_change_and_zones():
    s = series("20260328", "FREQ=DAILY;COUNT=4", duration=1)
    for zone in ("Europe/Paris", "Pacific/Auckland", "America/Los_Angeles"):
        got = expand(s, "2026-03-27", "2026-04-02", zone=zone).occurrences
        assert [o["start_date"] for o in got] == [
            "2026-03-28",
            "2026-03-29",
            "2026-03-30",
            "2026-03-31",
        ]


@pytest.mark.parametrize(
    ("kind", "dtstart", "rule"),
    [
        ("timed", "TZID=Europe/Paris:20260131T090000", "FREQ=MONTHLY;COUNT=4"),
        ("all_day", "20260131", "FREQ=MONTHLY;COUNT=4"),
        ("all_day", "20240229", "FREQ=YEARLY;COUNT=2"),
    ],
)
def test_invalid_generated_dates_are_ignored_not_counted_and_never_clamped(kind, dtstart, rule):
    s = series(dtstart, rule, duration=1 if kind == "all_day" else 3600)
    got = ids(s, "2024-01-01", "2034-01-01")
    assert len(got) == int(rule[-1])
    assert not any(i[:10] in {"2026-02-28", "2026-04-30", "2026-06-30", "2025-02-28"} for i in got)


# ---------------------------------------------------------------------------------------------
# Overrides, UTC values, lookback
# ---------------------------------------------------------------------------------------------


def test_overrides_move_cancel_and_inherit():
    s = paris("20260302T090000", "FREQ=DAILY;COUNT=5", duration=3600)
    moved = rec.normalize_override(
        {
            "recurrence_id": "TZID=Europe/Paris:20260303T090000",
            "start": "TZID=Europe/Paris:20260303T140000",
            "duration": 1800,
            "title": "Moved",
        },
        s,
    )
    cancelled = rec.normalize_override(
        {"recurrence_id": "TZID=Europe/Paris:20260304T090000", "status": "cancelled"}, s
    )
    result = expand(s, "2026-03-01", "2026-03-31", overrides=[moved, cancelled])
    assert result.cancelled_count == 1
    by_id = {o["recurrence_id"]: o for o in result.occurrences}
    assert "2026-03-04T09:00:00" not in by_id
    assert by_id["2026-03-03T09:00:00"]["title"] == "Moved"
    assert by_id["2026-03-03T09:00:00"]["start"] == "2026-03-03T13:00:00+00:00"
    assert by_id["2026-03-03T09:00:00"]["end"] == "2026-03-03T13:30:00+00:00"
    assert by_id["2026-03-03T09:00:00"]["exception"] == "modified"
    assert by_id["2026-03-02T09:00:00"]["exception"] == "none"
    assert by_id["2026-03-02T09:00:00"]["title"] == "Synthetic"


def test_override_moved_into_the_window_from_outside_and_out_of_it():
    s = paris("20260302T090000", "FREQ=DAILY;COUNT=60")
    into = rec.normalize_override(
        {
            "recurrence_id": "TZID=Europe/Paris:20260420T090000",
            "start": "TZID=Europe/Paris:20260305T090000",
        },
        s,
    )
    out = rec.normalize_override(
        {
            "recurrence_id": "TZID=Europe/Paris:20260303T090000",
            "start": "TZID=Europe/Paris:20260601T090000",
        },
        s,
    )
    got = {
        o["recurrence_id"]
        for o in expand(s, "2026-03-01", "2026-03-08", overrides=[into, out]).occurrences
    }
    assert "2026-04-20T09:00:00" in got  # moved in: appears with its original identity
    assert "2026-03-03T09:00:00" not in got  # moved out of the window
    far = {
        o["recurrence_id"]
        for o in expand(s, "2026-05-30", "2026-06-03", overrides=[into, out]).occurrences
    }
    assert "2026-03-03T09:00:00" in far


@pytest.mark.parametrize(
    ("value", "outcome"),
    [
        ("20261025T003000Z", "2026-10-25T02:30:00"),  # first 02:30 (CEST)
        ("20261025T013000Z", "utc_value_ambiguous"),  # second 02:30 (CET)
        ("20261025T100000Z", "2026-10-25T11:00:00"),
        ("20260329T013000Z", "2026-03-29T03:30:00"),  # just after the spring gap
    ],
)
@pytest.mark.parametrize("role", ["exdate", "rdate", "override"])
def test_utc_values_in_a_fold_keep_instants_or_are_refused(value, outcome, role):
    zone = ZoneInfo("Europe/Paris")
    if outcome == "utc_value_ambiguous":
        refused(outcome, rec.parse_value, value, kind="timed", zone=zone, role=role)
    else:
        assert rec.parse_value(value, kind="timed", zone=zone, role=role) == outcome


def test_local_and_utc_forms_of_one_instant_stay_two_occurrences():
    s = paris(
        "20260301T090000",
        None,
        rdates=["TZID=Europe/Paris:20260329T023000", "20260329T013000Z"],
    )
    got = expand(s, "2026-03-28", "2026-03-31").occurrences
    assert [o["recurrence_id"] for o in got] == ["2026-03-29T02:30:00", "2026-03-29T03:30:00"]
    assert {o["start"] for o in got} == {"2026-03-29T01:30:00+00:00"}
    assert len({uuid5(UUID(int=1), json.dumps(["u", o["recurrence_id"]])) for o in got}) == 2


def test_lookback_boundary_timed_end_exclusive():
    day = 86400
    for offset, shown in ((0, False), (-1, False), (1, True), (day, True)):
        # The instance starts 31 days (+ offset seconds) before the query start.
        wall = datetime(2026, 6, 2) + timedelta(seconds=offset)
        text = wall.strftime("%Y%m%dT%H%M%S")
        s = series(f"TZID=UTC:{text}", "FREQ=YEARLY", duration=codes.MAX_TIMED_DURATION)
        s = rec.normalize_series(
            {
                "title": "x",
                "dtstart": f"TZID=UTC:{(wall.replace(year=2025)).strftime('%Y%m%dT%H%M%S')}",
                "duration": codes.MAX_TIMED_DURATION,
                "rrule": "FREQ=YEARLY",
            }
        )
        assert bool(ids(s, "2026-07-03", "2026-07-05", zone="UTC")) is shown, offset


def test_lookback_boundary_all_day():
    for start, shown in (("20250602", False), ("20250603", True)):
        s = series(start, "FREQ=YEARLY", duration=codes.MAX_ALLDAY_DAYS)
        assert bool(ids(s, "2026-07-03", "2026-07-05", zone="UTC")) is shown, start


def test_lookback_across_a_dst_change():
    s = paris("20250301T000000", "FREQ=YEARLY", duration=codes.MAX_TIMED_DURATION)
    assert ids(s, "2026-04-01", "2026-04-03")  # ends 2026-03-31T23:00Z, after midnight CEST
    assert not ids(s, "2026-04-02", "2026-04-04")


def test_offset_changes_never_exceed_the_gap_allowance_in_any_zone():
    for name in sorted(available_timezones()):
        zone = ZoneInfo(name)
        offsets = [
            datetime(year, month, 15, tzinfo=zone).utcoffset()
            for year in range(1970, 2101)
            for month in range(1, 13)
        ]
        assert max(offsets) - min(offsets) <= timedelta(days=codes.GAP_ALLOWANCE_DAYS), name


def test_expander_uses_the_shared_duration_constants():
    tree = ast.parse((APP / "calendar_recurrence.py").read_text())
    assigned = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert not assigned & {
        "MAX_TIMED_DURATION",
        "MAX_ALLDAY_DAYS",
        "GAP_ALLOWANCE_DAYS",
        "SCAN_LIMIT",
    }
    assert rec.LOOKBACK == timedelta(
        seconds=codes.MAX_TIMED_DURATION, days=codes.GAP_ALLOWANCE_DAYS
    )


# ---------------------------------------------------------------------------------------------
# Limits and stable identity
# ---------------------------------------------------------------------------------------------


def test_occurrence_limit_counts_after_exclusions_overrides_and_reports_truncation():
    s = paris("20250101T090000", "FREQ=DAILY")
    result = expand(s, "2026-01-01", "2027-02-04")  # 399 days
    assert result.truncated and result.truncated_reason == "occurrence_limit"
    assert len(result.occurrences) == codes.MAX_OCCURRENCES
    assert result.occurrences_at_least == 399
    assert result.occurrences[0]["recurrence_id"] == "2026-01-01T09:00:00"
    # Exclusions and cancellations do not count toward the limit.
    ex = [
        f"TZID=Europe/Paris:{d.strftime('%Y%m%d')}T090000"
        for d in (date(2026, 1, 1) + timedelta(days=n) for n in range(40))
    ]
    trimmed = paris("20250101T090000", "FREQ=DAILY", exdates=ex)
    result = expand(trimmed, "2026-01-01", "2027-02-04")
    assert result.occurrences_at_least == 359 and not result.truncated
    cancels = [
        rec.normalize_override(
            {"recurrence_id": e, "status": "cancelled"},
            s,
        )
        for e in ex[:5]
    ]
    result = expand(s, "2026-01-01", "2027-01-01", overrides=cancels)
    assert (
        result.cancelled_count == 5 and result.occurrences_at_least == 360 and not result.truncated
    )


def test_scan_limit_reports_truncation_never_a_silent_short_result():
    s = paris("20250101T090000", "FREQ=DAILY")
    result = expand(s, "2026-01-01", "2026-03-01", scan_limit=10)
    assert result.truncated and result.truncated_reason == "scan_limit"
    assert len(result.occurrences) < 59


def test_scan_limit_applies_to_count_series_scanned_from_the_start():
    s = paris("20200101T090000", "FREQ=DAILY;COUNT=1000")
    assert expand(s, "2026-01-01", "2026-01-05", scan_limit=100).truncated_reason == "scan_limit"


def test_occurrence_ids_are_stable_across_windows_moves_and_restarts():
    s = paris("20260302T090000", "FREQ=DAILY;COUNT=10")
    namespace = UUID(int=7)

    def ident(o):
        return uuid5(namespace, json.dumps([o["uid"], o["recurrence_id"]], ensure_ascii=False))

    base = {o["recurrence_id"]: ident(o) for o in expand(s, "2026-03-01", "2026-04-01").occurrences}
    again = {
        o["recurrence_id"]: ident(o) for o in expand(s, "2026-03-04", "2026-03-08").occurrences
    }
    assert all(base[k] == v for k, v in again.items())
    moved = rec.normalize_override(
        {
            "recurrence_id": "TZID=Europe/Paris:20260305T090000",
            "start": "TZID=Europe/Paris:20260305T180000",
        },
        s,
    )
    after = {
        o["recurrence_id"]: ident(o)
        for o in expand(s, "2026-03-01", "2026-04-01", overrides=[moved]).occurrences
    }
    assert after == base


def test_single_event_keeps_the_legacy_non_recurring_identity():
    (o,) = expand(paris("20260302T090000"), "2026-03-01", "2026-03-04").occurrences
    assert o["recurrence_id"] == "" and o["recurring"] is False
    (o,) = expand(
        paris("20260302T090000", rdates=["TZID=Europe/Paris:20260310T090000"]),
        "2026-03-01",
        "2026-03-04",
    ).occurrences
    assert o["recurrence_id"] == "2026-03-02T09:00:00" and o["recurring"] is True


def test_cancelled_series_emits_nothing():
    assert (
        expand(paris("20260302T090000", status="cancelled"), "2026-03-01", "2026-03-04").occurrences
        == []
    )


def test_is_member_applies_count_until_exdate_and_rdate():
    s = paris(
        "20260301T090000",
        "FREQ=DAILY;COUNT=3",
        exdates=["TZID=Europe/Paris:20260302T090000"],
        rdates=["TZID=Europe/Paris:20260320T090000"],
    )
    assert rec.is_member(s, "2026-03-01T09:00:00")
    assert not rec.is_member(s, "2026-03-02T09:00:00")  # excluded
    assert rec.is_member(s, "2026-03-03T09:00:00")
    assert not rec.is_member(s, "2026-03-04T09:00:00")  # beyond COUNT
    assert rec.is_member(s, "2026-03-20T09:00:00")  # RDATE
    assert not rec.is_member(s, "2026-03-05T10:00:00")  # not on the rule


# ---------------------------------------------------------------------------------------------
# Static tests (section 13)
# ---------------------------------------------------------------------------------------------


def _imports(path):
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_dateutil_is_imported_only_by_the_recurrence_module():
    for path in APP.glob("*.py"):
        modules = _imports(path)
        uses = {m for m in modules if m.split(".")[0] == "dateutil"}
        if path.name == "calendar_recurrence.py":
            assert uses <= {
                "dateutil.rrule",
                "dateutil.rrule.DAILY",
                "dateutil.rrule.MONTHLY",
                "dateutil.rrule.WEEKLY",
                "dateutil.rrule.YEARLY",
                "dateutil.rrule.rrule",
            }
        else:
            assert not uses, path.name
        assert not any("rrulestr" in m or m in {"dateutil.parser", "dateutil.tz"} for m in modules)
    names = {
        getattr(node, "id", None) or getattr(node, "attr", None)
        for node in ast.walk(ast.parse((APP / "calendar_recurrence.py").read_text()))
    }
    assert not names & {"rrulestr", "parser", "tz"}


def test_the_recurrence_module_never_hands_count_or_until_to_dateutil():
    source = (APP / "calendar_recurrence.py").read_text()
    args = source[source.index("def _dateutil_args") : source.index("def _aligned_start")]
    assert "count" not in args and "until" not in args
