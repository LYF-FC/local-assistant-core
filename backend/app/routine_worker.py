"""Optional atomic local task generation from explicit routine intent."""

import argparse
import time
from datetime import datetime, timedelta
from uuid import uuid5

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app import identity, routines
from app import manual_tasks as tasks
from app import routine_contracts as contract
from app import task_reminders as reminders
from app.config import settings
from app.db import SessionLocal
from app.models import (
    ManualTask,
    ReminderPreferences,
    Routine,
    RoutineOccurrence,
    TaskReminder,
    User,
)


def process(db, candidate):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout='2s'"))
        db.execute(text("SET LOCAL statement_timeout='5s'"))
    user = db.scalar(
        select(User)
        .where(User.id == candidate.owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        return "skipped"
    granted = (
        db.scalar(
            text("SELECT public.butler_lock_task_scope(:actor,:scope)"),
            {"actor": user.id, "scope": candidate.scope_key},
        )
        if db.get_bind().dialect.name == "postgresql"
        else candidate.scope_key in identity.memberships(db, user)
    )
    row = db.scalar(
        select(Routine)
        .where(
            Routine.id == candidate.id,
            Routine.owner_id == user.id,
            Routine.scope_key == candidate.scope_key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = identity.now_utc()
    if row is None or row.state != "active" or identity.aware(row.next_at) > now:
        return "skipped"
    existing = {
        r.local_date
        for r in db.scalars(select(RoutineOccurrence).where(RoutineOccurrence.routine_id == row.id))
    }
    reason = (
        "owner_unavailable"
        if not user.is_active
        else "scope_unavailable"
        if not granted
        else "occurrence_limit"
        if len(existing) >= 400
        else "revision_limit"
        if row.revision >= 997
        else None
    )
    if reason:
        row.state, row.next_at = "blocked", None
        row.revision += 1
        row.updated_at = now
        routines.record(db, user, row, "blocked", system=True, metadata={"reason": reason})
        return "blocked"
    plan = row.data["plan"]
    end, latest = row.position, None
    while end < len(plan):
        due = datetime.fromisoformat(plan[end]["due_at"]) if plan[end]["due_at"] else None
        if due and due > now:
            break
        if due:
            latest = end
        end += 1
    # Leave following future gap slots unconsumed so a correction can replace them.
    end = latest + 1
    created, missed = None, 0
    blocked = False
    position = row.position
    for index in range(row.position, end):
        item = plan[index]
        if item["day"] in existing:
            position = index + 1
            continue
        if len(existing) >= 400:
            blocked = True
            break
        due = datetime.fromisoformat(item["due_at"]) if item["due_at"] else None
        outcome = (
            "dst_gap"
            if due is None
            else "created"
            if index == latest and now - due <= timedelta(hours=24)
            else "missed"
        )
        task = None
        if outcome == "created":
            values = row.data["values"]
            task = ManualTask(
                id=uuid5(row.id, item["day"]),
                owner_id=user.id,
                scope_key=row.scope_key,
                state="active",
                revision=1,
                title=values["title"],
                details=values["details"],
                source_reference=f"Routine {row.id} · revision {row.revision}",
                status="open",
                assignee_id=user.id,
                due_at=due,
                created_at=now,
                updated_at=now,
            )
            db.add(task)
            db.flush()
            tasks.snapshot(db, user, task, "created")
            if values["remind"]:
                policy = db.get(ReminderPreferences, user.id)
                when = now + timedelta(seconds=1)
                reminder = TaskReminder(
                    task_id=task.id,
                    owner_id=user.id,
                    scope_key=row.scope_key,
                    revision=1,
                    cycle=1,
                    policy_revision=policy.revision if policy else 0,
                    task_revision=1,
                    state="scheduled",
                    scheduled_at=when,
                    next_attempt_at=when,
                    created_at=now,
                    updated_at=now,
                )
                db.add(reminder)
                reminders.record_event(
                    db, user, reminder, "scheduled", system=True, routine_schedule=True
                )
            created = str(task.id)
        elif outcome == "missed":
            missed += 1
        db.add(
            RoutineOccurrence(
                id=uuid5(row.id, "receipt:" + item["day"]),
                routine_id=row.id,
                routine_revision=row.revision,
                local_date=item["day"],
                due_at=due,
                task_id=task.id if task else None,
                outcome=outcome,
                recorded_at=now,
            )
        )
        existing.add(item["day"])
        position = index + 1
    db.flush()  # Receipt/task/history must commit against the still-active parent version.
    if blocked:
        row.state = "blocked"
    row.position = position
    row.next_at = contract.next_at(row.data, position) if row.state == "active" else None
    if row.next_at is None and row.state == "active":
        row.state = "finished"
    row.revision += 1
    row.updated_at = now
    routines.record(
        db, user, row, "processed", system=True, metadata={"task_id": created, "missed": missed}
    )
    return "generated" if created else "advanced"


def run_once(maker=SessionLocal, limit=100):
    if not 1 <= limit <= 100:
        raise ValueError("Bounded routine pass required")
    with maker.begin() as db:
        batch = list(
            db.execute(
                select(Routine.id, Routine.owner_id, Routine.scope_key)
                .where(Routine.state == "active", Routine.next_at <= identity.now_utc())
                .order_by(Routine.next_at, Routine.id)
                .limit(limit)
            )
        )
    result = {
        "checked": len(batch),
        "generated": 0,
        "advanced": 0,
        "blocked": 0,
        "skipped": 0,
        "failed": 0,
    }
    for candidate in batch:
        try:
            with maker.begin() as db:
                outcome = process(db, candidate)
            result[outcome] += 1
        except (SQLAlchemyError, ValueError):
            result["failed"] += 1
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Restricted local routine worker; no external delivery"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true")
    group.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    if (
        settings.env not in {"development", "test"}
        or settings.postgres_user != "butler_runtime"
        or (settings.env == "test" and not settings.postgres_db.startswith("butler_test"))
    ):
        raise RuntimeError(
            "Routine worker requires restricted development/disposable-test credentials"
        )
    while True:
        try:
            result = run_once()
        except SQLAlchemyError:
            result = {"failed": 1}
        print(
            "Local routine pass: " + ", ".join(f"{key}={value}" for key, value in result.items()),
            flush=True,
        )
        if args.once:
            if result.get("failed"):
                raise SystemExit(1)
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
