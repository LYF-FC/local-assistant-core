"""Synthetic metadata-only reminders in the actual logical dump/restore drill."""

import sys
from datetime import timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, update
from app import identity, manual_tasks as tasks, task_reminders as reminders
from app.config import settings
from app.db import SessionLocal
from app.models import (
    ManualTask,
    ManualTaskRevision,
    ReminderPreferences,
    TaskReminder,
    TaskReminderEvent,
    User,
)

assert (
    settings.env == "test"
    and settings.postgres_db in {"butler_test", "butler_test_restore"}
    and settings.postgres_user == "postgres"
)
phase = sys.argv[1]
assert phase in {"seed", "check"}
with SessionLocal.begin() as db:
    owner = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
    assert owner and owner.slug == "synthetic-queue-restore"
    now = identity.now_utc()
    past = now - timedelta(minutes=2)
    if phase == "seed":
        db.add(
            ReminderPreferences(
                owner_id=owner.id,
                revision=1,
                enabled=False,
                timezone="Europe/Paris",
                quiet_start=1320,
                quiet_end=480,
                daily_limit=3,
                created_at=past,
                updated_at=past,
            )
        )
    else:
        preferences = db.get(ReminderPreferences, owner.id)
        assert (
            not preferences.enabled
            and preferences.timezone == "Europe/Paris"
            and preferences.daily_limit == 3
        )
    for name in ("pending", "delivered", "forgotten"):
        identifier = uuid5(NAMESPACE_URL, "butler-synthetic-reminder-restore-" + name)
        if phase == "seed":
            task = ManualTask(
                id=identifier,
                owner_id=owner.id,
                scope_key="household_shared",
                state="active",
                status="open",
                revision=1,
                title="Synthetic reminder restore",
                details="Synthetic restore detail",
                source_reference="Synthetic reminder restore source",
                created_at=past,
                updated_at=past,
            )
            db.add(task)
            db.flush()
            tasks.snapshot(db, owner, task, "created")
            tasks.audit(db, owner, task, "created")
            row = TaskReminder(
                task_id=identifier,
                owner_id=owner.id,
                scope_key=task.scope_key,
                revision=1,
                cycle=1,
                policy_revision=1,
                task_revision=1,
                state="scheduled",
                scheduled_at=past + timedelta(seconds=1),
                next_attempt_at=past + timedelta(seconds=1),
                created_at=past,
                updated_at=past,
            )
            db.add(row)
            reminders.record_event(db, owner, row, "scheduled")
            if name == "pending":
                reminders.change(
                    db,
                    owner,
                    row,
                    "deferred",
                    system=True,
                    next_attempt_at=now + timedelta(hours=1),
                    reason="quiet_hours",
                )
            else:
                delivered = identity.now_utc()
                reminders.change(
                    db,
                    owner,
                    row,
                    "delivered",
                    system=True,
                    recorded_now=delivered,
                    state="delivered",
                    next_attempt_at=None,
                    delivered_at=delivered,
                )
                if name == "forgotten":
                    task.state = "forgotten"
                    task.revision = 2
                    task.updated_at = identity.now_utc()
                    for key in (
                        "title",
                        "details",
                        "source_reference",
                        "status",
                        "assignee_id",
                        "due_at",
                        "completed_at",
                        "cancelled_at",
                    ):
                        setattr(task, key, None)
                    db.flush()
                    db.execute(
                        update(ManualTaskRevision)
                        .where(ManualTaskRevision.task_id == task.id)
                        .values(snapshot=None)
                    )
                    reminders.cancel_for_task(db, owner, task)
                    tasks.snapshot(db, owner, task, "forgotten")
                    tasks.audit(db, owner, task, "forgotten", 1)
        else:
            task = db.get(ManualTask, identifier)
            row = db.scalar(select(TaskReminder).where(TaskReminder.task_id == identifier))
            events = list(
                db.scalars(
                    select(TaskReminderEvent)
                    .where(TaskReminderEvent.reminder_id == row.id)
                    .order_by(TaskReminderEvent.revision)
                )
            )
            assert (
                row.owner_id == owner.id and row.scope_key == "household_shared" and row.cycle == 1
            )
            assert all(
                "Synthetic" not in str(e.snapshot) and "title" not in e.snapshot for e in events
            )
            if name == "pending":
                assert (
                    row.state == "scheduled"
                    and row.reason == "quiet_hours"
                    and row.next_attempt_at
                    and row.revision == 2
                )
            elif name == "delivered":
                assert row.state == "delivered" and row.delivered_at and len(events) == 2
            else:
                assert (
                    row.state == "cancelled"
                    and row.reason == "task_forgotten"
                    and task.title is None
                    and len(events) == 3
                )
print(
    "Synthetic pending/delivered/forgotten reminder history and paused preferences restored; no dispatch activated"
)
