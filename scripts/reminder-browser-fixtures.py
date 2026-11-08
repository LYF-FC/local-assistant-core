"""Disposable real-worker browser sentinel. Contains synthetic task text only."""

import sys
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from app import identity, manual_tasks as tasks, task_reminders as reminders
from app.config import settings
from app.db import SessionLocal
from app.models import ManualTask, ReminderPreferences, TaskReminder, TaskReminderEvent, User

# Container CI uses butler as its migration owner; native disposable PG uses postgres.
# The runtime account remains forbidden, and the environment/database guards are exact.
assert (
    settings.env == "test"
    and settings.postgres_db == "butler_test_container"
    and settings.postgres_user in {"postgres", "butler"}
)
phase = sys.argv[1]
assert phase in {"seed", "check"}
with SessionLocal.begin() as db:
    owner = db.scalar(select(User).where(User.slug == "browser-reminders-flow"))
    assert owner
    identifier = uuid5(NAMESPACE_URL, "butler-synthetic-due-reminder-browser")
    if phase == "seed":
        now = identity.now_utc()
        past = now - timedelta(minutes=2)
        db.add(
            ReminderPreferences(
                owner_id=owner.id,
                revision=1,
                enabled=True,
                timezone="UTC",
                quiet_start=0,
                quiet_end=0,
                daily_limit=5,
                created_at=past,
                updated_at=past,
            )
        )
        task = ManualTask(
            id=identifier,
            owner_id=owner.id,
            scope_key="household_shared",
            state="active",
            status="open",
            revision=1,
            title="Synthetic delivered reminder",
            details="Synthetic in-app delivery only",
            source_reference="Synthetic reminder browser fixture",
            created_at=past,
            updated_at=past,
        )
        db.add(task)
        db.flush()
        tasks.snapshot(db, owner, task, "created")
        tasks.audit(db, owner, task, "created")
        row = TaskReminder(
            task_id=task.id,
            owner_id=owner.id,
            scope_key=task.scope_key,
            revision=1,
            cycle=1,
            task_revision=1,
            policy_revision=1,
            state="scheduled",
            scheduled_at=now - timedelta(minutes=1),
            next_attempt_at=now - timedelta(minutes=1),
            created_at=past,
            updated_at=past,
        )
        db.add(row)
        reminders.record_event(db, owner, row, "scheduled")
    else:
        row = db.scalar(select(TaskReminder).where(TaskReminder.task_id == identifier))
        assert row.state == "delivered" and row.revision == 2
        events = list(
            db.scalars(
                select(TaskReminderEvent)
                .where(TaskReminderEvent.reminder_id == row.id)
                .order_by(TaskReminderEvent.revision)
            )
        )
        assert [r.operation for r in events] == ["scheduled", "delivered"]
        assert events[1].actor_id is None and "Synthetic" not in str(events[1].snapshot)
print(
    "Synthetic reminder browser fixture seeded"
    if phase == "seed"
    else "Synthetic real-worker in-app delivery and repeated-pass deduplication verified"
)
