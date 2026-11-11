"""Restricted synthetic delivery: exact-once claims, sealed history and least privilege."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from test_manual_tasks import create
from test_task_reminders import schedule
from test_task_reminders_postgres import only_pass, setup

from app import identity, notification_worker
from app import notifications as notes
from app.models import NotificationDelivery, NotificationDeliveryEvent

pytestmark = pytest.mark.integration


def enqueued(runtime_engine, scenario, monkeypatch, limit=5):
    _, _, admin, uid, _, row = setup(scenario, monkeypatch, limit=limit)
    assert only_pass(runtime_engine, row) == "delivered"
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with maker.begin() as db:
        assert notification_worker.enqueue_pass(db, 100) >= 1
    with maker.begin() as db:
        delivery = db.execute(
            select(
                NotificationDelivery.id,
                NotificationDelivery.owner_id,
                NotificationDelivery.scope_key,
            ).where(NotificationDelivery.reminder_id == UUID(row["id"]))
        ).one()
    return maker, admin, uid, row, delivery


def test_runtime_delivers_once_and_records_sealed_history(scenario, runtime_engine, monkeypatch):
    maker, admin, _, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)
    channel = notes.SyntheticChannel()
    assert notification_worker.process(maker, delivery, channel) == "delivered"
    assert notification_worker.process(maker, delivery, channel) == "skipped"
    assert channel.sent == 1
    with admin() as db:
        events = list(
            db.scalars(
                select(NotificationDeliveryEvent)
                .where(NotificationDeliveryEvent.delivery_id == delivery.id)
                .order_by(NotificationDeliveryEvent.revision)
            )
        )
    assert [e.operation for e in events] == ["enqueued", "attempted", "delivered"]


def test_concurrent_workers_send_a_cycle_once(scenario, runtime_engine, monkeypatch):
    maker, admin, _, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)
    channel = notes.SyntheticChannel()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: notification_worker.process(maker, delivery, channel), range(2))
        )
    assert sorted(results) == ["delivered", "skipped"]
    assert channel.sent == 1


def test_enqueue_is_idempotent_across_passes(scenario, runtime_engine, monkeypatch):
    maker, admin, _, row, _ = enqueued(runtime_engine, scenario, monkeypatch)
    with maker.begin() as db:
        notification_worker.enqueue_pass(db, 100)
    with admin() as db:
        count = db.scalar(
            text("SELECT count(*) FROM notification_deliveries WHERE reminder_id=:id"),
            {"id": UUID(row["id"])},
        )
    assert count == 1


def test_claim_commits_before_send_so_crash_never_resends(scenario, runtime_engine, monkeypatch):
    maker, admin, _, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)

    class Boom(notes.SyntheticChannel):
        def send(self, key, recipient):
            with admin() as db:  # the claim is already visible to another connection
                state = db.get(NotificationDelivery, delivery.id)
                assert state.attempts == 1 and state.attempt_started_at is not None
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        notification_worker.process(maker, delivery, Boom())
    channel = notes.SyntheticChannel()
    assert notification_worker.process(maker, delivery, channel) == "skipped"
    assert channel.sent == 0
    with admin.begin() as db:
        row = db.get(NotificationDelivery, delivery.id)
        # Age the claim beyond the in-flight deadline: it must turn unknown, never resend.
        db.execute(
            text("ALTER TABLE notification_deliveries DISABLE TRIGGER butler_notification_guard")
        )
        row.attempt_started_at = (
            identity.now_utc() - notes.IN_FLIGHT_DEADLINE - timedelta(seconds=1)
        )
        db.flush()
        db.execute(
            text("ALTER TABLE notification_deliveries ENABLE TRIGGER butler_notification_guard")
        )
    assert notification_worker.process(maker, delivery, channel) == "unknown"
    assert channel.sent == 0


MUTATIONS = [
    "owner_id=:other,revision=revision+1",
    "scope_key='member_a_private',revision=revision+1",
    "reminder_id=:other,revision=revision+1",
    "cycle=cycle+1,revision=revision+1",
    "channel='email',revision=revision+1",
    "recipient_ref='synthetic:forged',revision=revision+1",
    "created_at=created_at+interval '1s',revision=revision+1",
    "revision=revision+2",
    "attempts=attempts+2,revision=revision+1",
    "state='delivered',next_attempt_at=NULL,resolved_at=updated_at+interval '1s',revision=revision+1",
    "state='failed',next_attempt_at=NULL,resolved_at=updated_at,reason=NULL,revision=revision+1",
    "state='cancelled',next_attempt_at=NULL,resolved_at=updated_at,reason=NULL,revision=revision+1",
    "state='delivered',next_attempt_at=NULL,resolved_at=updated_at,reason='rejected',revision=revision+1",
    "attempts=4,revision=revision+1",
]


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_raw_state_identity_and_revision_guards(scenario, runtime_engine, monkeypatch, mutation):
    _, _, _, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(f"UPDATE notification_deliveries SET {mutation} WHERE id=:id"),
            {"id": delivery.id, "other": uuid4()},
        )


def test_terminal_state_cannot_be_revived(scenario, runtime_engine, monkeypatch):
    maker, _, _, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)
    assert notification_worker.process(maker, delivery, notes.SyntheticChannel()) == "delivered"
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "UPDATE notification_deliveries SET state='pending',next_attempt_at=now(),"
                "resolved_at=NULL,revision=revision+1 WHERE id=:id"
            ),
            {"id": delivery.id},
        )


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM notification_deliveries WHERE id=:id",
        "TRUNCATE notification_deliveries CASCADE",
        "UPDATE notification_delivery_events SET snapshot='{}' WHERE delivery_id=:id",
        "DELETE FROM notification_delivery_events WHERE delivery_id=:id",
        "TRUNCATE notification_delivery_events",
        "SELECT metadata_json FROM audit_events",
    ],
)
def test_runtime_history_and_least_privilege(scenario, runtime_engine, monkeypatch, statement):
    _, _, _, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(statement), {"id": delivery.id})


INSERT = (
    "INSERT INTO notification_deliveries(id,reminder_id,owner_id,scope_key,cycle,channel,"
    "recipient_ref,revision,state,attempts,next_attempt_at,created_at,updated_at) "
    "VALUES(:new,:reminder,:owner,'household_shared',:cycle,:channel,'synthetic:x',1,"
    "'pending',0,now(),now(),now())"
)


def test_duplicate_cycle_unknown_channel_and_unsent_reminder_are_refused(
    scenario, runtime_engine, monkeypatch
):
    client, h, _, uid, _, row = setup(scenario, monkeypatch)
    # Scheduled but not yet delivered: a delivery may not exist for it.
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(INSERT),
            {
                "new": uuid4(),
                "reminder": UUID(row["id"]),
                "owner": uid,
                "cycle": 1,
                "channel": "synthetic",
            },
        )
    assert only_pass(runtime_engine, row) == "delivered"
    args = {"new": uuid4(), "reminder": UUID(row["id"]), "owner": uid, "cycle": 1}
    with runtime_engine.begin() as db:
        db.execute(text(INSERT), {**args, "channel": "synthetic"})
    # The legitimate insert above lacks its enqueued event, so remove nothing: only refusals follow.
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(INSERT), {**args, "new": uuid4(), "channel": "synthetic"})
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(INSERT), {**args, "new": uuid4(), "cycle": 2, "channel": "synthetic"})
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(INSERT), {**args, "new": uuid4(), "channel": "email"})


def test_forged_history_snapshot_is_refused(scenario, runtime_engine, monkeypatch):
    _, _, uid, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)
    for operation, snapshot in (
        ("delivered", "{}"),
        ("attempted", '{"id":"x"}'),
        ("enqueued", "{}"),
    ):
        with runtime_engine.begin() as db, pytest.raises(DBAPIError):
            db.execute(
                text(
                    "INSERT INTO notification_delivery_events(id,delivery_id,owner_id,revision,"
                    "operation,recorded_at,snapshot) "
                    "VALUES(:new,:id,:owner,2,:op,now(),CAST(:snap AS jsonb))"
                ),
                {
                    "new": uuid4(),
                    "id": delivery.id,
                    "owner": uid,
                    "op": operation,
                    "snap": snapshot,
                },
            )


def test_schedule_task_helper_is_available(scenario):
    # Guards the shared fixture shape these tests rely on.
    assert callable(create) and callable(schedule)
