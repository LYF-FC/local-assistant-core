"""Briefing v2, per-source states, explicit limits, corrupt stored data, provider routes (SQLite)."""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm import sessionmaker
from test_approvals import signin
from test_calendar_sync import (
    RID,
    make_world,
    override_item,
    series_item,
)
from test_calendars import briefing, call, create, import_events, occurrence

from app import identity
from app.config import settings
from app.models import CalendarSeries, CalendarSource, CalendarSyncState

DAILY = "FREQ=DAILY;COUNT=10"


@pytest.fixture
def world(auth_store, tmp_path, monkeypatch):
    return make_world(auth_store, tmp_path, monkeypatch)


def v2(client, h, day="2026-03-15", days=3, zone="Europe/Paris"):
    response = briefing(client, h, day=day, timezone=zone, horizon_days=days)
    assert response.status_code == 200, response.text
    return response.json()


def source_entry(body, source):
    return next(c for c in body["calendars"] if c["id"] == str(source))


def test_a_provider_series_is_expanded_on_read_with_markers_and_counts(auth_client, world):
    h = signin(auth_client)
    source = world.source()
    world.writer.append([series_item(rrule=DAILY), override_item(rid=RID.replace("0322", "0316"))])
    assert world.sync(source)["outcome"] == "ok"
    body = v2(auth_client, h)
    assert body["schema_version"] == 2 and body["horizon_days"] == 3
    assert [d["day"] for d in body["days"]] == ["2026-03-15", "2026-03-16", "2026-03-17"]
    assert [e["days"] for e in body["events"]] == [["2026-03-15"], ["2026-03-17"]]
    assert all(e["recurring"] and e["exception"] in {"none", "modified"} for e in body["events"])
    assert all(e["source_state"] == "available" and e["as_of"] for e in body["events"])
    assert body["cancelled_count"] == 1  # the cancelled instance is counted, not shown
    entry = source_entry(body, source)
    assert (entry["mode"], entry["source_state"], entry["unreadable"]) == (
        "provider",
        "available",
        0,
    )
    assert body["limits"]["events"] == {"shown": 2, "truncated": False, "omitted_at_least": 0}
    assert body["limits"]["unreadable_items"] == 0
    assert body["truncated"]["events"] is False


def test_v1_request_keeps_the_v1_shape_and_never_carries_v2_fields(auth_client, world):
    h = signin(auth_client)
    source = world.source()
    world.writer.append([series_item(rrule=DAILY)])
    world.sync(source)
    body = briefing(auth_client, h, day="2026-03-15", timezone="Europe/Paris").json()
    assert body["schema_version"] == 1
    assert "limits" not in body and "days" not in body and "mode" not in body["calendars"][0]
    assert [e["uid"] for e in body["events"]] == ["s1"]


@pytest.mark.parametrize("days", [0, 8, -1])
def test_a_horizon_outside_one_to_seven_is_refused_with_a_stable_code(auth_client, days):
    h = signin(auth_client)
    response = briefing(
        auth_client, h, day="2026-03-15", timezone="Europe/Paris", horizon_days=days
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Access denied"}  # the stable code is in the audit event


def test_source_states_cover_never_blocked_stale_and_unavailable(auth_client, world):
    h = signin(auth_client)
    fresh, never, blocked, stale, down = (world.source(label=n) for n in "abcde")
    world.writer.append([series_item(rrule=DAILY)])
    world.sync(fresh)
    world.sync(stale)
    with world.maker.begin() as db:
        db.get(CalendarSyncState, stale).last_success_at = identity.now_utc() - timedelta(days=2)
        row = db.get(CalendarSyncState, blocked)
        row.status, row.blocked_reason = "blocked", "series_limit"
        row.blocked_detail = {"entity": "page"}
        down_row = db.get(CalendarSyncState, down)
        down_row.status, down_row.last_error_code = "retry_wait", "provider_timeout"
        down_row.last_success_at = identity.now_utc()
    body = v2(auth_client, h)
    states = {c["id"]: c["source_state"] for c in body["calendars"]}
    assert states[str(fresh)] == "available"
    assert states[str(never)] == "unknown_coverage"
    assert states[str(blocked)] == "limit_reached"
    assert states[str(stale)] == "stale"
    assert states[str(down)] == "unavailable"
    assert source_entry(body, blocked)["blocked_reason"] == "series_limit"


def test_a_grammar_block_shows_blocked_and_keeps_the_last_data_visible(auth_client, world):
    h = signin(auth_client)
    source = world.source()
    world.writer.append([series_item(rrule=DAILY)])
    world.sync(source)
    with world.maker.begin() as db:
        row = db.get(CalendarSyncState, source)
        row.status, row.blocked_reason = "blocked", "freq_unsupported"
    body = v2(auth_client, h)
    assert source_entry(body, source)["source_state"] == "blocked"
    assert body["events"], "last stored data stays visible"


def test_unreadable_stored_series_is_counted_and_reported_never_dropped_silently(
    auth_client, world
):
    h = signin(auth_client)
    source = world.source()
    world.writer.append([series_item(rrule=DAILY), series_item(uid="s2", rrule=DAILY)])
    world.sync(source)
    with world.maker.begin() as db:
        row = db.query(CalendarSeries).filter_by(uid="s2").one()
        row.rule = "garbage"
    body = v2(auth_client, h)
    entry = source_entry(body, source)
    assert entry["unreadable"] == 1 and entry["source_state"] == "unknown_coverage"
    assert body["limits"]["unreadable_items"] == 1
    assert {e["uid"] for e in body["events"]} == {"s1"}


def test_a_malformed_stored_manual_event_is_counted_not_a_server_error(auth_client):
    h = signin(auth_client)
    import_events(
        auth_client,
        h,
        [occurrence(uid="ok", start="2026-03-15T09:00:00+01:00", end="2026-03-15T10:00:00+01:00")],
        "Europe/Paris",
        "2026-03-10",
        "2026-03-20",
    )
    row = auth_client.post(
        "/api/v1/calendars/query", headers=h, json={"scope": "household_shared"}
    ).json()["items"][0]

    assert row["id"]  # the stored row exists; corruption is injected below
    maker = _maker(auth_client)
    with maker.begin() as db:
        source = db.get(CalendarSource, UUID(row["id"]))
        data = dict(source.data)
        window = dict(data["window"])
        window["events"] = [
            window["events"][0],
            {"kind": "timed", "uid": "bad", "status": "confirmed"},
        ]
        data["window"] = window
        source.data = data
    for horizon in (None, 3):
        extra = {} if horizon is None else {"horizon_days": horizon}
        response = auth_client.post(
            "/api/v1/calendars/briefing",
            headers=h,
            json={
                "scope": "household_shared",
                "day": "2026-03-15",
                "timezone": "Europe/Paris",
                **extra,
            },
        )
        assert response.status_code == 200, response.text
        assert [e["uid"] for e in response.json()["events"]] == ["ok"]
        if horizon:
            body = response.json()
            assert body["limits"]["unreadable_items"] == 1
            assert body["calendars"][0]["source_state"] == "unknown_coverage"


def _maker(client):
    from app.auth_routes import get_db

    override = client.app.dependency_overrides[get_db]
    generator = override()
    db = next(generator)
    maker = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    generator.close()
    return maker


def test_event_and_source_limits_are_explicit_counts(auth_client, world):
    h = signin(auth_client)
    source = world.source()
    items = [series_item(uid=f"d{i}", rrule="FREQ=DAILY;COUNT=2") for i in range(60)]
    for start in range(0, 60, 30):
        world.writer.append(items[start : start + 30])
    for _ in range(3):
        world.sync(source)
    body = v2(auth_client, h, day="2026-03-15", days=2)
    assert len(body["events"]) == 100
    assert body["limits"]["events"]["shown"] == 100
    assert body["limits"]["events"]["truncated"] is True
    assert body["limits"]["events"]["omitted_at_least"] >= 20
    assert body["truncated"]["events"] is True
    v1 = briefing(auth_client, h, day="2026-03-15", timezone="Europe/Paris").json()
    assert v1["truncated"]["events"] is False  # one day of 60 events


def test_possible_duplicates_are_flagged_across_sources_and_never_merged(auth_client):
    h = signin(auth_client)
    same = {"start": "2026-03-15T09:00:00+01:00", "end": "2026-03-15T10:00:00+01:00"}
    import_events(
        auth_client,
        h,
        [occurrence(uid="a", title="Dentist", **same)],
        "Europe/Paris",
        "2026-03-10",
        "2026-03-20",
    )
    import_events(
        auth_client,
        h,
        [occurrence(uid="b", title="dentist ", **same)],
        "Europe/Paris",
        "2026-03-10",
        "2026-03-20",
    )
    body = v2(auth_client, h)
    assert len(body["events"]) == 2
    first, second = body["events"]
    assert first["possible_duplicate_of"] == [second["id"]]
    assert second["possible_duplicate_of"] == [first["id"]]
    assert first["possible_conflict"] and second["possible_conflict"]


def test_an_all_day_provider_series_is_placed_by_date_in_any_display_zone(auth_client, world):
    h = signin(auth_client)
    source = world.source()
    world.writer.append(
        [
            {
                "entity": "series",
                "operation": "upsert",
                "uid": "ad",
                "sequence": 1,
                "body": {
                    "title": "Holiday",
                    "dtstart": "20260316",
                    "duration": 2,
                    "rrule": "FREQ=WEEKLY;COUNT=2",
                },
            }
        ]
    )
    result = world.sync(source)
    assert result["outcome"] == "ok", (result, world.state(source).blocked_detail)
    for zone in ("Pacific/Auckland", "America/Los_Angeles", "Europe/Paris"):
        body = v2(auth_client, h, day="2026-03-15", days=4, zone=zone)
        assert [e["days"] for e in body["events"]] == [["2026-03-16", "2026-03-17"]], zone
        assert body["events"][0]["continues"] is True


def test_query_expands_provider_sources_over_a_bounded_range(auth_client, world):
    h = signin(auth_client)
    source = world.source()
    world.writer.append([series_item(rrule=DAILY)])
    world.sync(source)
    request = {
        "scope": "household_shared",
        "day": "2026-03-15",
        "days": 4,
        "timezone": "Europe/Paris",
    }
    body = auth_client.post("/api/v1/calendars/query", headers=h, json=request).json()
    item = next(i for i in body["items"] if i["id"] == str(source))
    assert item["mode"] == "provider" and len(item["occurrences"]) == 4
    assert item["truncated"] is False and item["unreadable"] == 0
    refused = auth_client.post("/api/v1/calendars/query", headers=h, json={**request, "days": 401})
    assert refused.status_code == 422
    partial = auth_client.post(
        "/api/v1/calendars/query", headers=h, json={"scope": "household_shared", "days": 3}
    )
    assert partial.status_code == 422


def test_provider_routes_answer_one_404_unless_the_synthetic_store_is_configured(
    auth_client, monkeypatch
):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    monkeypatch.setattr(settings, "calendar_synthetic_directory", None)
    unknown = UUID(int=9)
    results = [
        auth_client.post(f"/api/v1/calendars/{target}/{route}", headers=h, json=body)
        for target in (row["id"], unknown)
        for route, body in (
            ("provider", {"scope": "household_shared", "provider_ref": "household"}),
            ("sync", {"scope": "household_shared"}),
            ("sync-status", {"scope": "household_shared"}),
        )
    ]
    assert {r.status_code for r in results} == {404}
    assert len({r.text for r in results}) == 1


def test_owner_can_declare_sync_and_read_status_through_the_routes(auth_client, world):
    h = signin(auth_client)
    row = create(auth_client, h).json()
    base = {"scope": "household_shared"}
    declared = auth_client.post(
        f"/api/v1/calendars/{row['id']}/provider",
        headers=h,
        json={**base, "provider_ref": "household"},
    )
    assert declared.status_code == 200, declared.text
    world.writer.append([series_item(rrule=DAILY)])
    synced = auth_client.post(f"/api/v1/calendars/{row['id']}/sync", headers=h, json=base)
    assert synced.status_code == 200, synced.text
    body = synced.json()
    assert body["sync"]["outcome"] == "ok" and body["provider"]["status"] == "ok"
    assert "cursor" not in str(body)
    status = auth_client.post(f"/api/v1/calendars/{row['id']}/sync-status", headers=h, json=base)
    assert status.status_code == 200 and status.json()["provider"]["applied_seq"] == 1
    assert v2(auth_client, h)["events"]
    forgotten = call(auth_client, h, row, "forget")
    assert forgotten.status_code == 200
    again = auth_client.post(f"/api/v1/calendars/{row['id']}/sync", headers=h, json=base)
    assert again.status_code == 404
