"""Deterministic local inbox delivery. Optional worker; never sends to a provider."""

import argparse
import time
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from app import identity
from app import task_reminders as reminders
from app.config import settings
from app.db import SessionLocal
from app.models import ManualTask, ReminderPreferences, TaskReminder, TaskReminderEvent, User


def is_quiet(moment, policy):
    start, end = policy["quiet_start"], policy["quiet_end"]
    minute = (
        moment.astimezone(ZoneInfo(policy["timezone"])).hour * 60
        + moment.astimezone(ZoneInfo(policy["timezone"])).minute
    )
    return (
        False
        if start == end
        else start <= minute < end
        if start < end
        else minute >= start or minute < end
    )


def next_allowed(now, policy, next_day=False):
    """Walk real UTC minutes so nonexistent/ambiguous local clock values are never fabricated."""
    day = now.astimezone(ZoneInfo(policy["timezone"])).date()
    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(48 * 60):
        if (
            not next_day or candidate.astimezone(ZoneInfo(policy["timezone"])).date() > day
        ) and not is_quiet(candidate, policy):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("No allowed local delivery window")


def candidates(db, limit):
    now = identity.now_utc()
    return list(
        db.execute(
            select(
                TaskReminder.id, TaskReminder.owner_id, TaskReminder.task_id, TaskReminder.scope_key
            )
            .outerjoin(ReminderPreferences, ReminderPreferences.owner_id == TaskReminder.owner_id)
            .where(
                TaskReminder.state == "scheduled",
                TaskReminder.scheduled_at <= now,
                or_(ReminderPreferences.owner_id.is_(None), ReminderPreferences.enabled.is_(True)),
                or_(
                    TaskReminder.next_attempt_at <= now,
                    TaskReminder.policy_revision != func.coalesce(ReminderPreferences.revision, 0),
                ),
            )
            .order_by(TaskReminder.next_attempt_at, TaskReminder.id)
            .limit(limit)
        )
    )


def process(db, candidate):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout='2s'"))
        db.execute(text("SET LOCAL statement_timeout='5s'"))
    # Exclusive recipient lock serializes delivery counts across every scope/worker.
    user = db.scalar(
        select(User)
        .where(User.id == candidate.owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        return "skipped"
    if db.get_bind().dialect.name == "postgresql":
        granted = db.scalar(
            text("SELECT public.butler_lock_task_scope(:actor,:scope)"),
            {"actor": user.id, "scope": candidate.scope_key},
        )
    else:
        granted = candidate.scope_key in identity.memberships(db, user)
    task = db.execute(
        select(
            ManualTask.id,
            ManualTask.owner_id,
            ManualTask.scope_key,
            ManualTask.state,
            ManualTask.status,
            ManualTask.revision,
        )
        .where(
            ManualTask.id == candidate.task_id,
            ManualTask.owner_id == user.id,
            ManualTask.scope_key == candidate.scope_key,
        )
        .with_for_update()
    ).one_or_none()
    if task is None:
        return "skipped"
    row = db.scalar(
        select(TaskReminder)
        .where(
            TaskReminder.id == candidate.id,
            TaskReminder.owner_id == user.id,
            TaskReminder.task_id == task.id,
            TaskReminder.scope_key == task.scope_key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or row.state != "scheduled":
        return "skipped"
    now = identity.now_utc()
    policy = reminders.policy_document(db.get(ReminderPreferences, user.id))
    if (
        identity.aware(row.scheduled_at) > now
        or not policy["enabled"]
        or (row.policy_revision == policy["revision"] and identity.aware(row.next_attempt_at) > now)
    ):
        return "skipped"
    reason = (
        "owner_unavailable"
        if not user.is_active
        else "scope_unavailable"
        if not granted
        else "task_forgotten"
        if task.state == "forgotten"
        else "task_closed"
        if task.status != "open"
        else None
    )
    if reason:
        reminders.change(
            db,
            user,
            row,
            "cancelled",
            system=True,
            recorded_now=now,
            state="cancelled",
            next_attempt_at=None,
            reason=reason,
            task_revision=task.revision,
            policy_revision=policy["revision"],
        )
        return "cancelled"
    reason = "quiet_hours" if is_quiet(now, policy) else None
    if not reason:
        zone = ZoneInfo(policy["timezone"])
        day = now.astimezone(zone).date()
        deliveries = db.scalars(
            select(TaskReminderEvent.recorded_at).where(
                TaskReminderEvent.owner_id == user.id,
                TaskReminderEvent.operation == "delivered",
                TaskReminderEvent.recorded_at >= now - timedelta(hours=48),
            )
        ).all()
        count = sum(identity.aware(at).astimezone(zone).date() == day for at in deliveries)
        if count >= policy["daily_limit"]:
            reason = "daily_limit"
    if reason:
        reminders.change(
            db,
            user,
            row,
            "deferred",
            system=True,
            recorded_now=now,
            next_attempt_at=next_allowed(now, policy, next_day=reason == "daily_limit"),
            reason=reason,
            task_revision=task.revision,
            policy_revision=policy["revision"],
        )
        return "deferred"
    reminders.change(
        db,
        user,
        row,
        "delivered",
        system=True,
        recorded_now=now,
        state="delivered",
        delivered_at=now,
        next_attempt_at=None,
        reason=None,
        task_revision=task.revision,
        policy_revision=policy["revision"],
    )
    return "delivered"


def run_once(maker=SessionLocal, limit=100):
    if not 1 <= limit <= 100:
        raise ValueError("A bounded pass is required")
    with maker.begin() as db:
        batch = candidates(db, limit)
    result = {
        "checked": len(batch),
        "delivered": 0,
        "deferred": 0,
        "cancelled": 0,
        "skipped": 0,
        "failed": 0,
    }
    for item in batch:
        try:
            with maker.begin() as db:
                outcome = process(db, item)
            result[outcome] += 1
        except (SQLAlchemyError, ValueError, ZoneInfoNotFoundError):
            # No body/SQL/credentials are printed; failed transaction rolls back and can retry.
            result["failed"] += 1
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Restricted local reminder worker; no external delivery"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true")
    group.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    if settings.env not in {"development", "test"} or settings.postgres_user != "butler_runtime":
        raise RuntimeError(
            "Reminder worker requires development/test restricted runtime credentials"
        )
    if settings.env == "test" and not settings.postgres_db.startswith("butler_test"):
        raise RuntimeError("Disposable test database required")
    while True:
        try:
            result = run_once()
        except SQLAlchemyError:
            result = {"failed": 1}
        print(
            "Local reminder pass: " + ", ".join(f"{key}={value}" for key, value in result.items()),
            flush=True,
        )
        if args.once:
            if result.get("failed"):
                raise SystemExit(1)
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
