from copy import deepcopy
from datetime import date, timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_manual_tasks import create as task

from app import calendar_contracts as contract
from app import identity
from app.manage import set_scope
from app.models import AuditEvent, CalendarRevision, CalendarSource, MemoryRecord, User


def occurrence(**changes):
    return {
        "kind": "timed",
        "uid": "synthetic-event",
        "recurrence_id": "",
        "sequence": 0,
        "title": "Synthetic appointment",
        "description": "Synthetic details",
        "status": "confirmed",
        "timezone": "Europe/Paris",
        "start": "2026-10-25T09:00:00+01:00",
        "end": "2026-10-25T10:00:00+01:00",
        **changes,
    }


def window(**changes):
    return {
        "complete": True,
        "cursor": "synthetic-cursor-1",
        "fetched_at": (identity.now_utc() - timedelta(seconds=5)).isoformat(),
        "timezone": "Europe/Paris",
        "start_date": "2026-10-24",
        "end_date": "2026-10-27",
        "events": [occurrence()],
        **changes,
    }


def create(client, h, **changes):
    return client.post(
        "/api/v1/calendars",
        headers=h,
        json={"scope": "household_shared", "label": "Synthetic calendar", **changes},
    )


def call(client, h, row, operation, **changes):
    body = {"scope": row["scope"]}
    if operation in {"import", "unavailable", "forget"}:
        body["expected_revision"] = row["revision"]
    return client.post(
        f"/api/v1/calendars/{row['id']}/{operation}", headers=h, json={**body, **changes}
    )


def briefing(client, h, **changes):
    return client.post(
        "/api/v1/calendars/briefing",
        headers=h,
        json={
            "scope": "household_shared",
            "day": "2026-10-25",
            "timezone": "Europe/Paris",
            **changes,
        },
    )


def test_reconcile_replay_moved_recurrence_omission_cancel_and_history(auth_client):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    first = window(
        events=[
            occurrence(recurrence_id="2026-10-25T09:00:00+01:00"),
            occurrence(uid="synthetic-other"),
        ]
    )
    row = call(auth_client, h, row, "import", window=first).json()
    assert row["revision"] == 2 and row["data"]["changes"]["added"] == 2
    initial = briefing(auth_client, h).json()
    assert len(initial["events"]) == 2 and all(e["possible_conflict"] for e in initial["events"])
    replay = call(auth_client, h, {**row, "revision": 1}, "import", window=first)
    assert replay.status_code == 200 and replay.json()["revision"] == 2
    second = window(
        cursor="synthetic-cursor-2",
        fetched_at=(identity.now_utc() - timedelta(seconds=2)).isoformat(),
        events=[
            occurrence(
                recurrence_id="2026-10-25T09:00:00+01:00",
                sequence=1,
                start="2026-10-25T11:00:00+01:00",
                end="2026-10-25T12:00:00+01:00",
            )
        ],
    )
    row = call(auth_client, h, row, "import", window=second).json()
    assert row["data"]["changes"] == {
        "added": 0,
        "updated": 1,
        "removed_in_coverage": 1,
        "outside_coverage_unknown": 0,
    }
    after = briefing(auth_client, h).json()["events"]
    assert len(after) == 1 and after[0]["id"] == next(
        e["id"] for e in initial["events"] if e["recurrence_id"]
    )
    third = {
        **second,
        "cursor": "synthetic-cursor-3",
        "fetched_at": identity.now_utc().isoformat(),
        "events": [{**second["events"][0], "sequence": 2, "status": "cancelled"}],
    }
    row = call(auth_client, h, row, "import", window=third).json()
    assert briefing(auth_client, h).json()["events"] == []
    history = call(auth_client, h, row, "history").json()
    assert [r["revision"] for r in history["items"]] == [1, 2, 3, 4]
    assert (
        history["items"][1]["snapshot"]["window"]["events"][0]["start"]
        == "2026-10-25T08:00:00+00:00"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"complete": False},
        {"complete": 1},
        {"events": [occurrence(), occurrence()]},
        {"timezone": "Not/AZone"},
        {"start_date": "2026-10-25T00:00:00"},
        {"start_date": 0},
        {"end_date": "2027-01-01"},
        {"cursor": ""},
        {"events": [occurrence(sequence=True)]},
        {"events": [occurrence(start="2026-10-25T09:00:00")]},
        {"events": [occurrence(start="2026-10-25T09:00:00+02:00")]},
        {
            "events": [
                occurrence(start="2026-03-29T02:30:00+01:00", end="2026-03-29T04:00:00+02:00")
            ]
        },
        {"events": [occurrence(uid=str(i)) for i in range(101)]},
        {"events": [occurrence(uid=str(i), description="界" * 512) for i in range(100)]},
        {"events": [occurrence(end="2026-10-25T08:00:00+01:00")]},
        {"partial": True},
    ],
)
def test_invalid_windows_are_sanitized_without_state_change(auth_client, change):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    r = call(auth_client, h, row, "import", window=window(**change))
    assert r.status_code == 422 and r.json() == {"detail": "Invalid request"}
    assert call(auth_client, h, row, "read").json()["revision"] == 1


@pytest.mark.parametrize(
    "change",
    ["cursor", "sequence", "equal_sequence", "old_fetch", "future_fetch", "stale_revision"],
)
def test_conflicts_do_not_advance_cursor_or_history(auth_client, change):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    first = window(events=[occurrence(sequence=2)])
    row = call(auth_client, h, row, "import", window=first).json()
    second = deepcopy(first)
    second.update(cursor="synthetic-next", fetched_at=identity.now_utc().isoformat())
    if change == "cursor":
        second["cursor"] = first["cursor"]
    if change == "sequence":
        second["events"][0]["sequence"] = 1
    if change == "equal_sequence":
        second["events"][0]["title"] = "Synthetic conflict"
    if change == "old_fetch":
        second["fetched_at"] = first["fetched_at"]
    if change == "future_fetch":
        second["fetched_at"] = (identity.now_utc() + timedelta(minutes=2)).isoformat()
    r = call(
        auth_client,
        h,
        {**row, "revision": 1} if change == "stale_revision" else row,
        "import",
        window=second,
    )
    assert r.status_code == 409
    assert call(auth_client, h, row, "read").json() == row
    assert len(call(auth_client, h, row, "history").json()["items"]) == 2


def test_dst_all_day_rolling_coverage_and_offline_keep_last_good(auth_client):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    all_day = {
        "kind": "all_day",
        "uid": "synthetic-all-day",
        "sequence": 0,
        "title": "Synthetic day",
        "timezone": "Europe/Paris",
        "start_date": "2026-10-25",
        "end_date": "2026-10-26",
    }
    row = call(auth_client, h, row, "import", window=window(events=[all_day, occurrence()])).json()
    day = briefing(auth_client, h).json()
    assert datetime_delta(day) == timedelta(hours=25)
    assert not day["events"][0]["possible_conflict"]
    row = call(auth_client, h, row, "unavailable", reason="offline").json()
    day = briefing(auth_client, h).json()
    assert len(day["events"]) == 2 and day["calendars"][0]["status"] == "offline"
    assert (
        call(auth_client, h, row, "import", window=row["data"]["window"]).json()["data"]["status"]
        == "offline"
    )
    row = call(
        auth_client,
        h,
        row,
        "import",
        window=window(
            cursor="synthetic-rolling",
            fetched_at=identity.now_utc().isoformat(),
            start_date="2026-10-27",
            end_date="2026-10-28",
            events=[],
        ),
    ).json()
    assert (
        row["data"]["changes"]["removed_in_coverage"] == 0
        and row["data"]["changes"]["outside_coverage_unknown"] == 2
    )
    assert not briefing(auth_client, h).json()["calendars"][0]["covers_day"]
    assert datetime_delta(briefing(auth_client, h, day="2026-03-29").json()) == timedelta(hours=23)


def datetime_delta(day):
    from datetime import datetime

    return datetime.fromisoformat(day["end_at"]) - datetime.fromisoformat(day["start_at"])


def test_forget_scrubs_export_history_and_audit_contains_no_content(auth_client, auth_store):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    row = call(auth_client, h, row, "import", window=window()).json()
    exported = call(auth_client, h, row, "export", acknowledge_copy_limits=True)
    assert exported.status_code == 200 and exported.json()["managed_copy"] is False
    assert call(auth_client, h, row, "export", acknowledge_copy_limits=1).status_code == 422
    row = call(auth_client, h, row, "forget").json()
    assert row["state"] == "forgotten" and row["data"] is None
    assert call(auth_client, h, row, "import", window=window()).status_code == 410
    assert all(r["snapshot"] is None for r in call(auth_client, h, row, "history").json()["items"])
    with auth_store() as db:
        audits = list(db.scalars(select(AuditEvent).where(AuditEvent.entity_id == row["id"])))
        assert audits and all("Synthetic" not in str(a.metadata_json) for a in audits)
        assert all(r.snapshot is None for r in db.scalars(select(CalendarRevision)))


def test_current_permissions_owner_private_admin_and_revocation(auth_client, auth_store):
    h = signin(auth_client)
    shared = create(auth_client, h).json()
    with auth_store.begin() as db:
        alice = db.scalar(select(User).where(User.slug == "alice"))
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, alice, "member_b_private", True)
        set_scope(db, bob, "household_shared", True)
        set_scope(db, bob, "technical_admin", True)
    private = create(auth_client, h, scope="member_b_private").json()
    bh = signin(auth_client, "bob")
    assert call(auth_client, bh, shared, "read").status_code == 200
    assert briefing(auth_client, bh, scope="member_b_private").json()["calendars"] == []
    for operation, payload in [
        ("read", {}),
        ("history", {}),
        ("export", {"acknowledge_copy_limits": True}),
        ("import", {"window": window()}),
        ("forget", {}),
    ]:
        assert call(auth_client, bh, private, operation, **payload).status_code == 404
        if operation != "read":
            assert call(auth_client, bh, shared, operation, **payload).status_code == 403
    assert briefing(auth_client, {}, scope="household_shared").status_code == 403
    assert briefing(auth_client, {**bh, "Origin": "https://other.invalid"}).status_code == 403
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "bob")), "household_shared", False)
    assert briefing(auth_client, bh).status_code == 403
    assert call(auth_client, bh, shared, "read").status_code == 403


def test_briefing_current_tasks_confirmed_memory_bounds_and_model_independence(
    auth_client, auth_store
):
    h = signin(auth_client)
    task(auth_client, h, due_at="2026-10-25T12:00:00Z", title="Synthetic today's task")
    task(auth_client, h, due_at="2026-10-24T12:00:00Z", title="Synthetic overdue task")
    task(auth_client, h, title="Synthetic undated task")
    task(auth_client, h, due_at="2026-10-26T12:00:00Z", title="Synthetic later task")
    with auth_store.begin() as db:
        alice = db.scalar(select(User).where(User.slug == "alice"))
        for i in range(12):
            db.add(
                MemoryRecord(
                    owner_id=alice.id,
                    scope_key="household_shared",
                    kind="preference",
                    title=f"Synthetic reference {i}",
                    content={"text": "Synthetic"},
                    source_type="manual",
                    source_reference="Synthetic source",
                    assessment="confirmed" if i < 11 else "tentative",
                )
            )
    r = briefing(auth_client, h).json()
    assert [t["overdue"] for t in r["tasks"]] == [True, False]
    assert len(r["memories"]) == 10 and r["truncated"]["memories"]
    assert r["calendars"] == [] and "unknown" in r["notice"]


def test_audit_failure_rolls_back_import_and_withholds_briefing(
    auth_client, auth_store, auth_engine
):
    h = signin(auth_client)
    row = create(auth_client, h).json()

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic audit failure")

    event.listen(auth_engine, "before_cursor_execute", fail)
    try:
        assert call(auth_client, h, row, "import", window=window()).status_code == 503
        assert briefing(auth_client, h).status_code == 503
    finally:
        event.remove(auth_engine, "before_cursor_execute", fail)
    with auth_store() as db:
        assert db.get(CalendarSource, UUID(row["id"])).revision == 1
        assert len(list(db.scalars(select(CalendarRevision)))) == 1


def test_source_quota_history_pages_and_limit_preserve_forget(auth_client):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    for i in range(99):
        row = call(auth_client, h, row, "unavailable", reason="offline").json()
    assert row["revision"] == 100
    assert call(auth_client, h, row, "unavailable", reason="failed").status_code == 429
    first = call(auth_client, h, row, "history").json()
    assert len(first["items"]) == 5 and first["next_cursor"] == 5
    second = call(auth_client, h, row, "history", after=5).json()
    assert second["items"][0]["revision"] == 6
    assert call(auth_client, h, row, "forget").json()["revision"] == 101
    for _ in range(9):
        assert create(auth_client, h).status_code == 201
    assert create(auth_client, h).status_code == 429


def test_briefing_section_caps_and_stale_coverage(auth_client):
    h = signin(auth_client)
    for i in range(2):
        row = create(auth_client, h, label=f"Synthetic bounded calendar {i}").json()
        assert (
            call(
                auth_client,
                h,
                row,
                "import",
                window=window(events=[occurrence(uid=f"synthetic-{j}") for j in range(100)]),
            ).status_code
            == 200
        )
    for i in range(26):
        task(auth_client, h, title=f"Synthetic deadline {i}", due_at="2026-10-25T12:00:00Z")
    result = briefing(auth_client, h).json()
    assert len(result["events"]) == 100 and result["truncated"]["events"]
    assert len(result["tasks"]) == 25 and result["truncated"]["tasks"]
    assert all(c["covers_day"] for c in result["calendars"])
    assert all(e["possible_conflict"] for e in result["events"])
    assert len({e["id"] for e in result["events"]}) == 100


def test_history_cursor_reuse_and_sequence_after_omission_refused(auth_client):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    first = window(events=[occurrence(sequence=2)])
    row = call(auth_client, h, row, "import", window=first).json()
    row = call(
        auth_client,
        h,
        row,
        "import",
        window=window(
            cursor="synthetic-empty",
            fetched_at=(identity.now_utc() - timedelta(seconds=2)).isoformat(),
            events=[],
        ),
    ).json()
    assert (
        call(
            auth_client,
            h,
            row,
            "import",
            window=window(
                cursor="synthetic-new",
                fetched_at=identity.now_utc().isoformat(),
                events=[occurrence(sequence=1)],
            ),
        ).status_code
        == 409
    )
    assert (
        call(
            auth_client,
            h,
            row,
            "import",
            window={**first, "fetched_at": identity.now_utc().isoformat()},
        ).status_code
        == 409
    )


# G1: an all-day event belongs to display date D iff start_date <= D < end_date, whatever the zones.


def all_day_event(**changes):
    return {
        "kind": "all_day",
        "uid": "synthetic-all-day",
        "recurrence_id": "",
        "sequence": 0,
        "title": "Synthetic all-day",
        "description": "",
        "status": "confirmed",
        "timezone": "Europe/Paris",
        "start_date": "2026-03-05",
        "end_date": "2026-03-06",
        **changes,
    }


def import_events(client, h, events, zone, first, last):
    row = create(client, h).json()
    response = call(
        client,
        h,
        row,
        "import",
        window=window(timezone=zone, start_date=first, end_date=last, events=events),
    )
    assert response.status_code == 200, response.text
    return response.json()


def agenda(client, h, day, zone):
    response = briefing(client, h, day=day, timezone=zone)
    assert response.status_code == 200, response.text
    return response.json()


def shown(client, h, day, zone):
    return [e["uid"] for e in agenda(client, h, day, zone)["events"]]


ZONE_PAIRS = [
    pytest.param("Pacific/Auckland", "Europe/Paris", id="event-ahead"),
    pytest.param("America/Los_Angeles", "Europe/Paris", id="event-behind"),
    pytest.param("Europe/Paris", "Europe/Paris", id="zones-equal"),
    pytest.param("Europe/Paris", "Pacific/Auckland", id="display-ahead"),
]


@pytest.mark.parametrize(("event_zone", "display_zone"), ZONE_PAIRS)
def test_all_day_event_is_placed_by_date_when_zones_differ(auth_client, event_zone, display_zone):
    h = signin(auth_client)
    events = [all_day_event(timezone=event_zone)]
    import_events(auth_client, h, events, display_zone, "2026-03-01", "2026-03-11")
    days = ("2026-03-04", "2026-03-05", "2026-03-06")
    assert {d: shown(auth_client, h, d, display_zone) for d in days} == {
        "2026-03-04": [],
        "2026-03-05": ["synthetic-all-day"],
        "2026-03-06": [],
    }


@pytest.mark.parametrize(("event_zone", "display_zone"), ZONE_PAIRS)
def test_multi_day_all_day_event_covers_each_date_and_nothing_else(
    auth_client, event_zone, display_zone
):
    h = signin(auth_client)
    events = [all_day_event(timezone=event_zone, start_date="2026-03-05", end_date="2026-03-08")]
    import_events(auth_client, h, events, display_zone, "2026-03-01", "2026-03-11")
    days = ("2026-03-04", "2026-03-05", "2026-03-06", "2026-03-07", "2026-03-08")
    assert {d: shown(auth_client, h, d, display_zone) for d in days} == {
        "2026-03-04": [],
        "2026-03-05": ["synthetic-all-day"],
        "2026-03-06": ["synthetic-all-day"],
        "2026-03-07": ["synthetic-all-day"],
        "2026-03-08": [],
    }


@pytest.mark.parametrize(("event_zone", "display_zone"), ZONE_PAIRS[:3])
def test_all_day_end_date_is_exclusive(auth_client, event_zone, display_zone):
    h = signin(auth_client)
    events = [
        all_day_event(
            uid="synthetic-ends-on-fifth",
            timezone=event_zone,
            start_date="2026-03-04",
            end_date="2026-03-05",
        ),
        all_day_event(
            uid="synthetic-ends-on-seventh",
            timezone=event_zone,
            start_date="2026-03-05",
            end_date="2026-03-07",
        ),
    ]
    import_events(auth_client, h, events, display_zone, "2026-03-01", "2026-03-11")
    days = ("2026-03-04", "2026-03-05", "2026-03-06", "2026-03-07")
    assert {d: shown(auth_client, h, d, display_zone) for d in days} == {
        "2026-03-04": ["synthetic-ends-on-fifth"],
        "2026-03-05": ["synthetic-ends-on-seventh"],
        "2026-03-06": ["synthetic-ends-on-seventh"],
        "2026-03-07": [],
    }


@pytest.mark.parametrize(
    ("event_zone", "display_zone", "day", "hours"),
    [
        pytest.param("Europe/Paris", "Europe/Paris", "2026-03-29", 23, id="paris-spring-forward"),
        pytest.param("Europe/Paris", "Europe/Paris", "2026-10-25", 25, id="paris-fall-back"),
        pytest.param("America/New_York", "Europe/Paris", "2026-03-08", 24, id="new-york-spring"),
        pytest.param("America/New_York", "Europe/Paris", "2026-11-01", 24, id="new-york-fall"),
    ],
)
def test_all_day_event_on_dst_change_day_stays_date_based(
    auth_client, event_zone, display_zone, day, hours
):
    h = signin(auth_client)
    first = date.fromisoformat(day)
    event = all_day_event(
        timezone=event_zone, start_date=day, end_date=(first + timedelta(days=1)).isoformat()
    )
    import_events(
        auth_client,
        h,
        [event],
        display_zone,
        (first - timedelta(days=4)).isoformat(),
        (first + timedelta(days=5)).isoformat(),
    )
    days = [(first + timedelta(days=n)).isoformat() for n in (-1, 0, 1)]
    assert {d: shown(auth_client, h, d, display_zone) for d in days} == {
        days[0]: [],
        days[1]: ["synthetic-all-day"],
        days[2]: [],
    }
    assert datetime_delta(agenda(auth_client, h, day, display_zone)) == timedelta(hours=hours)


def test_all_day_sorts_before_timed_and_timed_overlap_flags_are_unchanged(auth_client):
    h = signin(auth_client)
    # The Los Angeles all-day date starts (as an instant) after the early timed event, so only
    # an ordering by kind and calendar date, not by midnight instants, puts it first.
    events = [
        occurrence(
            uid="synthetic-t3", start="2026-10-25T11:00:00+01:00", end="2026-10-25T12:00:00+01:00"
        ),
        occurrence(
            uid="synthetic-t2", start="2026-10-25T09:30:00+01:00", end="2026-10-25T10:30:00+01:00"
        ),
        occurrence(uid="synthetic-t1"),
        occurrence(
            uid="synthetic-early",
            start="2026-10-25T00:30:00+02:00",
            end="2026-10-25T01:30:00+02:00",
        ),
        all_day_event(
            uid="synthetic-all-day-2",
            timezone="America/Los_Angeles",
            start_date="2026-10-25",
            end_date="2026-10-26",
        ),
        all_day_event(uid="synthetic-all-day-1", start_date="2026-10-24", end_date="2026-10-27"),
    ]
    import_events(auth_client, h, events, "Europe/Paris", "2026-10-20", "2026-10-30")
    result = agenda(auth_client, h, "2026-10-25", "Europe/Paris")["events"]
    assert [e["uid"] for e in result] == [
        "synthetic-all-day-1",
        "synthetic-all-day-2",
        "synthetic-early",
        "synthetic-t1",
        "synthetic-t2",
        "synthetic-t3",
    ]
    assert {e["uid"]: e["possible_conflict"] for e in result} == {
        "synthetic-all-day-1": False,
        "synthetic-all-day-2": False,
        "synthetic-early": False,
        "synthetic-t1": True,
        "synthetic-t2": True,
        "synthetic-t3": False,
    }


def test_timed_event_crossing_midnight_still_uses_instant_overlap(auth_client):
    h = signin(auth_client)
    events = [
        occurrence(
            uid="synthetic-midnight",
            start="2026-10-24T23:30:00+02:00",
            end="2026-10-25T00:30:00+02:00",
        ),
        occurrence(
            uid="synthetic-auckland",
            timezone="Pacific/Auckland",
            start="2026-10-25T00:30:00+13:00",
            end="2026-10-25T01:30:00+13:00",
        ),
    ]
    import_events(auth_client, h, events, "Europe/Paris", "2026-10-20", "2026-10-30")
    days = ("2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26")
    assert {d: shown(auth_client, h, d, "Europe/Paris") for d in days} == {
        "2026-10-23": [],
        "2026-10-24": ["synthetic-auckland", "synthetic-midnight"],
        "2026-10-25": ["synthetic-midnight"],
        "2026-10-26": [],
    }


def test_briefing_v1_response_keys_and_types_are_unchanged(auth_client):
    h = signin(auth_client)
    events = [
        all_day_event(),
        occurrence(
            uid="synthetic-timed",
            start="2026-03-05T09:00:00+01:00",
            end="2026-03-05T10:00:00+01:00",
        ),
    ]
    import_events(auth_client, h, events, "Europe/Paris", "2026-03-01", "2026-03-11")
    body = agenda(auth_client, h, "2026-03-05", "Europe/Paris")
    assert set(body) == {
        "schema_version",
        "scope",
        "day",
        "timezone",
        "checked_at",
        "valid_until",
        "start_at",
        "end_at",
        "calendars",
        "events",
        "tasks",
        "memories",
        "truncated",
        "notice",
    }
    assert body["schema_version"] == 1 and type(body["schema_version"]) is int
    for name in ("scope", "day", "timezone", "checked_at", "valid_until", "start_at", "end_at"):
        assert isinstance(body[name], str)
    assert isinstance(body["notice"], str)
    for name in ("calendars", "events", "tasks", "memories"):
        assert isinstance(body[name], list)
    assert set(body["truncated"]) == {"calendars", "events", "tasks", "memories"}
    assert all(type(v) is bool for v in body["truncated"].values())
    assert {"covers_day", "stale"} <= set(body["calendars"][0])
    shared = {
        "kind",
        "uid",
        "recurrence_id",
        "sequence",
        "title",
        "description",
        "status",
        "timezone",
        "id",
        "source_id",
        "source_revision",
        "source_label",
        "stale",
        "availability",
        "possible_conflict",
    }
    by_kind = {e["kind"]: e for e in body["events"]}
    assert set(by_kind) == {"all_day", "timed"}
    assert set(by_kind["all_day"]) == shared | {"start_date", "end_date"}
    assert set(by_kind["timed"]) == shared | {"start", "end"}
    for item in by_kind.values():
        for name in ("kind", "uid", "recurrence_id", "title", "id", "source_id", "source_label"):
            assert isinstance(item[name], str)
        assert type(item["source_revision"]) is int and type(item["sequence"]) is int
        assert type(item["stale"]) is bool and type(item["possible_conflict"]) is bool
        UUID(item["id"])
        UUID(item["source_id"])


@pytest.mark.parametrize(
    "event",
    [
        pytest.param(
            {
                "kind": "all_day",
                "start": "2026-03-05T00:00:00+01:00",
                "end": "2026-03-06T00:00:00+01:00",
            },
            id="timed-fields-on-all-day-kind",
        ),
        pytest.param({"kind": "all_day", "start_date": "2026-03-05"}, id="missing-end-date"),
        pytest.param({"kind": "all_day", "end_date": "2026-03-06"}, id="missing-start-date"),
        pytest.param(
            {"kind": "all_day", "start_date": "not-a-date", "end_date": "2026-03-06"},
            id="unparseable-date",
        ),
        pytest.param(
            {"kind": "all_day", "start_date": None, "end_date": "2026-03-06"}, id="null-date"
        ),
        pytest.param(
            {"kind": "all_day", "start_date": "2026-03-05T00:00:00", "end_date": "2026-03-06"},
            id="datetime-not-date",
        ),
        pytest.param(
            {"kind": "all_day", "start_date": "2026-03-06", "end_date": "2026-03-05"},
            id="reversed-dates",
        ),
        pytest.param(
            {"kind": "all_day", "start_date": "2026-03-05", "end_date": "2026-03-05"},
            id="empty-span",
        ),
        pytest.param(
            {"kind": "all_day", "start_date": "2026-03-05", "end_date": "2026-04-30"},
            id="span-over-31-days",
        ),
        pytest.param({"kind": "holiday"}, id="unknown-kind"),
        pytest.param({}, id="no-kind"),
    ],
)
def test_placement_rejects_malformed_occurrences_instead_of_reinterpreting(event):
    start = contract.midnight(date(2026, 3, 5), "Europe/Paris")
    end = contract.midnight(date(2026, 3, 6), "Europe/Paris")
    with pytest.raises(ValueError):
        contract.placed_on_day(event, date(2026, 3, 5), start, end)
