"""Synthetic intent and actual-worker receipts for the isolated browser phase."""

import sys
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text

from app import identity, routines
from app import routine_contracts as contract
from app.config import settings
from app.db import SessionLocal
from app.models import ManualTask, Routine, RoutineOccurrence, TaskReminder, User

assert settings.env == "test" and settings.postgres_db == "butler_test_container"
phase = sys.argv[1]
assert phase in {"seed", "check"}
identifier = uuid5(NAMESPACE_URL, "butler-synthetic-routine-browser")
with SessionLocal.begin() as db:
    # CI and local disposable stacks can use different migration-owner names.
    # Require actual table ownership; the restricted runtime cannot seed intent.
    assert db.scalar(
        text(
            "SELECT pg_get_userbyid(relowner)=current_user FROM pg_class WHERE oid='public.routines'::regclass"
        )
    ), "Synthetic routine fixtures require the migration table owner"
    owner = db.scalar(select(User).where(User.slug == "browser-routines-flow"))
    assert owner
    if phase == "seed":
        now = identity.now_utc()
        due = now - timedelta(minutes=2)
        before = due - timedelta(minutes=2)
        values = contract.Values(
            scope="member_a_private",
            title="Synthetic generated routine",
            details="Synthetic generated details",
            source_reference="Synthetic fixture",
            timezone="UTC",
            local_time=due.strftime("%H:%M"),
            frequency="daily",
            interval=1,
            weekdays=[],
            starts_on=due.date(),
            ends_on=due.date() + timedelta(days=2),
            remind=True,
        )
        data = contract.resolve(values, before)
        row = Routine(
            id=identifier,
            owner_id=owner.id,
            scope_key=values.scope,
            state="active",
            revision=1,
            changes=0,
            position=0,
            next_at=contract.next_at(data),
            data=data,
            created_at=before,
            updated_at=before,
        )
        db.add(row)
        routines.record(db, owner, row, "created")
    else:
        row = db.get(Routine, identifier)
        receipts = list(
            db.scalars(select(RoutineOccurrence).where(RoutineOccurrence.routine_id == identifier))
        )
        assert row.revision == 2 and len(receipts) == 1 and receipts[0].outcome == "created"
        task = db.get(ManualTask, receipts[0].task_id)
        reminder = db.scalar(select(TaskReminder).where(TaskReminder.task_id == task.id))
        assert (
            task.owner_id == owner.id
            and task.scope_key == "member_a_private"
            and task.status == "open"
        )
        assert (
            reminder.owner_id == owner.id
            and reminder.state == "scheduled"
            and reminder.scheduled_at > reminder.created_at
        )
print("Synthetic routine actual-worker task/private-reminder and replay fixture verified")
