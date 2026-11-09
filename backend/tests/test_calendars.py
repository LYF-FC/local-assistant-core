from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_manual_tasks import create as task

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
