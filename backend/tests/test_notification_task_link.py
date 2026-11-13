"""Spec 071 review: the notification query releases the related task id only when verified."""

from sqlalchemy import select
from test_approvals import signin
from test_notifications import clock, delivered_reminder, rows  # noqa: F401

from app import notification_worker
from app import notifications as notes
from app.models import TaskReminder

QUERY = "/api/v1/notifications/query"
BODY = {"scope": "household_shared", "state": "all"}


def delivered(client, store, clock, h):  # noqa: F811
    task = delivered_reminder(client, store, clock, h)
    notification_worker.run_once(notes.SyntheticChannel(), store)
    return task


def test_item_carries_the_verified_task_id_and_nothing_else_new(auth_client, auth_store, clock):  # noqa: F811
    h = signin(auth_client)
    task = delivered(auth_client, auth_store, clock, h)
    (item,) = auth_client.post(QUERY, headers=h, json=BODY).json()["items"]
    assert item["task_id"] == task["id"]
    assert set(item) == {
        "id", "reminder_id", "task_id", "owner_id", "scope", "channel", "state", "revision",
        "cycle", "attempts", "next_attempt_at", "resolved_at", "reason", "created_at", "updated_at",
    }  # fmt: skip
    # No task text or details are added to the list.
    assert task["title"] not in str(item) and "details" not in item
    # Sealed history snapshots are unchanged: the link is a response field only.
    history = auth_client.post(
        "/api/v1/notifications/history",
        headers=h,
        json={"scope": "household_shared", "delivery_id": item["id"]},
    ).json()
    assert "task_id" not in str(history)


def test_a_mismatched_reminder_releases_no_task_id(auth_client, auth_store, clock):  # noqa: F811
    h = signin(auth_client)
    delivered(auth_client, auth_store, clock, h)
    with auth_store() as db:
        reminder = db.scalar(select(TaskReminder))
        reminder.scope_key = "member_a_private"
        db.commit()
    (item,) = auth_client.post(QUERY, headers=h, json=BODY).json()["items"]
    assert item["task_id"] is None and item["state"] == "delivered"


def test_other_members_and_scopes_never_see_the_link(auth_client, auth_store, clock):  # noqa: F811
    h = signin(auth_client)
    delivered(auth_client, auth_store, clock, h)
    denied = auth_client.post(QUERY, headers=h, json={"scope": "member_b_private"})
    assert denied.status_code in {401, 403} and "task_id" not in denied.text
    anonymous = auth_client.post(QUERY, json=BODY)
    assert anonymous.status_code in {401, 403} and "task_id" not in anonymous.text
    assert len(rows(auth_store)) == 1
