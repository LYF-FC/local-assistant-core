"""Restricted synthetic delivery: exact-once claims, sealed history and least privilege."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from conftest import SYNTHETIC_PASSWORD, client_for
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from test_manual_tasks import create
from test_task_reminders import policy, schedule
from test_task_reminders_postgres import only_pass, setup

from app import identity, notification_worker
from app import notifications as notes
from app.manage import provision
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
    maker, _, _, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)
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
    _, _, _, uid, _, row = setup(scenario, monkeypatch)
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


# --- Corrective regression tests (audit of spec 068) ---------------------------------------


@pytest.fixture
def second_owner(postgres_engine, runtime_engine):
    """An independent signed-in owner whose notifications must never wait behind another's."""
    admin = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    slug = "synthetic-" + uuid4().hex
    with admin.begin() as db:
        provision(db, slug, "Synthetic Other Owner", SYNTHETIC_PASSWORD, {"household_shared"})
    with client_for(sessionmaker(bind=runtime_engine, expire_on_commit=False)) as client:
        login = client.post(
            "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
        )
        assert login.status_code == 200
        yield client, {"X-CSRF-Token": login.json()["csrf_token"]}


def deliver_reminder(client, headers, runtime_engine, clock):
    task = create(client, headers, title="Synthetic reminder " + uuid4().hex).json()
    response = schedule(client, headers, task, clock["now"] + timedelta(seconds=1))
    assert response.status_code == 200, response.json()
    clock["now"] += timedelta(seconds=2)
    assert only_pass(runtime_engine, response.json()) == "delivered"
    return response.json()


def drain(maker, channel):
    """Settle ambient synthetic deliveries that other tests left committed and due."""
    for _ in range(30):
        if notification_worker.run_once(channel, maker)["checked"] == 0:
            return
    raise AssertionError("ambient deliveries never settled")


def delivery_ids(admin, reminder_ids):
    with admin() as db:
        return {
            row.reminder_id: row
            for row in db.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.reminder_id.in_([UUID(i) for i in reminder_ids])
                )
            )
        }


def test_paused_deliveries_are_parked_once_and_never_starve_other_owners(
    scenario, second_owner, runtime_engine, monkeypatch
):
    client, h, _, admin, _ = scenario
    other, other_h = second_owner
    clock = {"now": identity.now_utc()}
    monkeypatch.setattr(identity, "now_utc", lambda: clock["now"])
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    channel = notes.SyntheticChannel()
    assert policy(client, h, daily_limit=10).status_code == 200
    assert policy(other, other_h, daily_limit=10).status_code == 200
    paused = [deliver_reminder(client, h, runtime_engine, clock) for _ in range(3)]
    assert policy(client, h, expected_revision=1, enabled=False, daily_limit=10).status_code == 200
    clock["now"] += timedelta(seconds=5)
    # Owner A's three deliveries are due and paused when they are first enqueued: they must be
    # parked once, with the reason recorded, rather than reselected on every pass.
    first = notification_worker.run_once(channel, maker)
    assert first["enqueued"] >= 3 and first["deferred"] >= 3
    parked = delivery_ids(admin, [r["id"] for r in paused])
    assert len(parked) == 3
    assert {d.state for d in parked.values()} == {"pending"}
    assert {d.reason for d in parked.values()} == {"paused"}
    revisions = {k: d.revision for k, d in parked.items()}
    drain(maker, channel)
    clock["now"] += timedelta(minutes=1)
    mine = deliver_reminder(other, other_h, runtime_engine, clock)
    with maker.begin() as db:
        selected = {c.id for c in notification_worker.candidates(db, 100)}
    assert not selected & {d.id for d in parked.values()}
    result = notification_worker.run_once(channel, maker, limit=2)
    assert result["delivered"] >= 1
    assert delivery_ids(admin, [mine["id"]])[UUID(mine["id"])].state == "delivered"
    # Further passes neither reselect nor rewrite parked deliveries.
    for _ in range(2):
        clock["now"] += timedelta(minutes=5)
        notification_worker.run_once(channel, maker)
    again = delivery_ids(admin, [r["id"] for r in paused])
    assert {k: d.revision for k, d in again.items()} == revisions
    assert {d.state for d in again.values()} == {"pending"}
    # Resuming keeps them eligible (paused is not cancelled) and they are delivered.
    assert policy(client, h, expected_revision=2, enabled=True, daily_limit=10).status_code == 200
    for _ in range(3):
        notification_worker.run_once(channel, maker)
    resumed = delivery_ids(admin, [r["id"] for r in paused])
    assert {d.state for d in resumed.values()} == {"delivered"}


def test_bounded_pass_reaches_second_owner_behind_older_paused_deliveries(
    scenario, second_owner, runtime_engine, monkeypatch
):
    client, h, _, admin, _ = scenario
    other, other_h = second_owner
    clock = {"now": identity.now_utc()}
    monkeypatch.setattr(identity, "now_utc", lambda: clock["now"])
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    channel = notes.SyntheticChannel()
    assert policy(client, h, daily_limit=10).status_code == 200
    assert policy(other, other_h, daily_limit=10).status_code == 200
    older = [deliver_reminder(client, h, runtime_engine, clock) for _ in range(3)]
    assert policy(client, h, expected_revision=1, enabled=False, daily_limit=10).status_code == 200
    clock["now"] += timedelta(seconds=5)
    notification_worker.run_once(channel, maker)
    drain(maker, channel)
    clock["now"] += timedelta(minutes=1)
    newer = deliver_reminder(other, other_h, runtime_engine, clock)
    # Two slots, three older paused deliveries ahead in the queue: the newer owner must still go.
    assert notification_worker.run_once(channel, maker, limit=2)["delivered"] == 1
    assert delivery_ids(admin, [newer["id"]])[UUID(newer["id"])].state == "delivered"
    assert {d.state for d in delivery_ids(admin, [r["id"] for r in older]).values()} == {"pending"}


def test_paused_owner_still_reconciles_unknown_without_sending(
    scenario, runtime_engine, monkeypatch
):
    client, h, _, admin, uid = scenario
    clock = {"now": identity.now_utc()}
    monkeypatch.setattr(identity, "now_utc", lambda: clock["now"])
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    assert policy(client, h, daily_limit=10).status_code == 200
    drain(maker, notes.SyntheticChannel())
    channel = notes.SyntheticChannel({notes.recipient_ref(uid): ["timeout_applied"]})
    mine = deliver_reminder(client, h, runtime_engine, clock)
    notification_worker.run_once(channel, maker)
    assert delivery_ids(admin, [mine["id"]])[UUID(mine["id"])].state == "unknown"
    assert policy(client, h, expected_revision=1, enabled=False, daily_limit=10).status_code == 200
    clock["now"] += notes.RECONCILE_INTERVAL
    notification_worker.run_once(channel, maker)
    final = delivery_ids(admin, [mine["id"]])[UUID(mine["id"])]
    assert final.state == "delivered" and channel.sent == 1


def forged_event(runtime_engine, delivery, mutate):
    """Advance a delivery one valid step, then record history with a tampered snapshot."""
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with maker.begin() as db:
        row = db.get(NotificationDelivery, delivery.id)
        now = identity.now_utc()
        row.attempts += 1
        row.attempt_started_at = now
        row.revision += 1
        row.updated_at = now
        db.flush()
        snapshot = notes.document(row)
        mutate(snapshot)
        db.add(
            NotificationDeliveryEvent(
                delivery_id=row.id,
                owner_id=row.owner_id,
                revision=row.revision,
                operation="attempted",
                recorded_at=row.updated_at,
                snapshot=snapshot,
            )
        )
        db.flush()


FORGERIES = {
    "channel": lambda s: s.update(channel="email"),
    "next_attempt_at": lambda s: s.update(next_attempt_at="2099-01-01T00:00:00+00:00"),
    "next_attempt_at_hidden": lambda s: s.update(next_attempt_at=None),
    "resolved_at": lambda s: s.update(resolved_at="2026-01-01T00:00:00+00:00"),
    "created_at": lambda s: s.update(created_at="2001-01-01T00:00:00+00:00"),
    "updated_at": lambda s: s.update(updated_at="2001-01-01T00:00:00+00:00"),
    "updated_at_offset": lambda s: s.update(updated_at=s["updated_at"].replace("+00:00", "+02:00")),
    "missing_channel": lambda s: s.pop("channel"),
    "missing_resolved_at": lambda s: s.pop("resolved_at"),
    "revision_as_string": lambda s: s.update(revision=str(s["revision"])),
    "attempts_as_string": lambda s: s.update(attempts=str(s["attempts"])),
    "timestamp_as_number": lambda s: s.update(created_at=1),
    "extra_key": lambda s: s.update(task_title="leaked"),
}


@pytest.mark.parametrize("forgery", sorted(FORGERIES))
def test_history_snapshot_must_match_every_parent_field(
    scenario, runtime_engine, monkeypatch, forgery
):
    _, _, _, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)
    with pytest.raises(DBAPIError):
        forged_event(runtime_engine, delivery, FORGERIES[forgery])
    with sessionmaker(bind=runtime_engine)() as db:
        row = db.get(NotificationDelivery, delivery.id)
        assert row.revision == 1 and row.attempts == 0


def test_honest_snapshot_is_accepted_and_history_stays_append_only(
    scenario, runtime_engine, monkeypatch
):
    _, admin, _, _, delivery = enqueued(runtime_engine, scenario, monkeypatch)
    forged_event(runtime_engine, delivery, lambda s: None)
    with admin() as db:
        events = db.scalars(
            select(NotificationDeliveryEvent)
            .where(NotificationDeliveryEvent.delivery_id == delivery.id)
            .order_by(NotificationDeliveryEvent.revision)
        ).all()
        assert [e.operation for e in events] == ["enqueued", "attempted"]
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text("UPDATE notification_delivery_events SET snapshot='{}' WHERE delivery_id=:id"),
            {"id": delivery.id},
        )
