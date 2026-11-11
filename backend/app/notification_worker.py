"""Optional worker delivering delivered in-app reminders to a synthetic channel.

The send happens outside any database transaction. A claim commits first, so a crash or timeout
leaves the row marked in flight and it is reconciled by lookup, never blindly resent.
"""

import argparse
import time
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from app import identity
from app import notifications as notes
from app import task_reminders as reminders
from app.config import settings
from app.db import SessionLocal
from app.models import (
    NotificationDelivery,
    NotificationDeliveryEvent,
    ReminderPreferences,
    TaskReminder,
    User,
)
from app.reminder_worker import is_quiet, next_allowed

COUNTED = ("delivered", "reconciled")


def lock_owner(db, owner_id, scope):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout='2s'"))
        db.execute(text("SET LOCAL statement_timeout='5s'"))
    user = db.scalar(
        select(User)
        .where(User.id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        return None, False
    if db.get_bind().dialect.name == "postgresql":
        granted = db.scalar(
            text("SELECT public.butler_lock_task_scope(:actor,:scope)"),
            {"actor": user.id, "scope": scope},
        )
    else:
        granted = scope in identity.memberships(db, user)
    return user, bool(granted)


def lock_row(db, delivery_id):
    return db.scalar(
        select(NotificationDelivery)
        .where(NotificationDelivery.id == delivery_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def enqueue_pass(db, limit):
    """Create at most one delivery per delivered reminder cycle; unique key makes it idempotent."""
    now = identity.now_utc()
    due = list(
        db.scalars(
            select(TaskReminder)
            .outerjoin(
                NotificationDelivery,
                and_(
                    NotificationDelivery.reminder_id == TaskReminder.id,
                    NotificationDelivery.cycle == TaskReminder.cycle,
                ),
            )
            .where(TaskReminder.state == "delivered", NotificationDelivery.id.is_(None))
            .order_by(TaskReminder.id)
            .limit(limit)
            .with_for_update(of=TaskReminder)
            .execution_options(populate_existing=True)
        )
    )
    for reminder in due:
        notes.enqueue(db, reminder, now)
    return len(due)


def candidates(db, limit):
    now = identity.now_utc()
    stale = now - notes.IN_FLIGHT_DEADLINE
    return list(
        db.execute(
            select(
                NotificationDelivery.id,
                NotificationDelivery.owner_id,
                NotificationDelivery.scope_key,
            )
            .outerjoin(
                ReminderPreferences, ReminderPreferences.owner_id == NotificationDelivery.owner_id
            )
            .where(
                # A delivery parked as paused stays out of the due set until its owner resumes;
                # otherwise the oldest paused rows would fill every bounded pass.
                or_(
                    NotificationDelivery.reason.is_distinct_from("paused"),
                    ReminderPreferences.enabled.is_distinct_from(False),
                ),
                or_(
                    and_(
                        NotificationDelivery.state.in_(("pending", "unknown")),
                        NotificationDelivery.next_attempt_at <= now,
                        NotificationDelivery.attempt_started_at.is_(None),
                    ),
                    and_(
                        NotificationDelivery.state == "pending",
                        NotificationDelivery.attempt_started_at <= stale,
                    ),
                ),
            )
            .order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id)
            .limit(limit)
        )
    )


def eligibility(db, row, user, granted):
    """Return a cancellation reason when the delivery may no longer be sent."""
    reminder = db.scalar(
        select(TaskReminder)
        .where(TaskReminder.id == row.reminder_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if user is None or not user.is_active:
        return "owner_unavailable"
    if not granted:
        return "scope_unavailable"
    if reminder is None or reminder.state != "delivered" or reminder.cycle != row.cycle:
        return "reminder_closed"
    return None


def claim(db, candidate):
    """Phase 1: decide the action under locks. Returns (outcome, key) and commits claim state."""
    user, granted = lock_owner(db, candidate.owner_id, candidate.scope_key)
    row = lock_row(db, candidate.id)
    if row is None or row.state not in {"pending", "unknown"}:
        return "skipped", None
    now = identity.now_utc()
    in_flight = row.state == "pending" and row.attempt_started_at is not None
    if in_flight and identity.aware(row.attempt_started_at) > now - notes.IN_FLIGHT_DEADLINE:
        return "skipped", None
    if not in_flight and (row.next_attempt_at is None or identity.aware(row.next_attempt_at) > now):
        return "skipped", None
    reason = eligibility(db, row, user, granted)
    if reason:
        notes.change(db, row, "cancelled", now, **notes.resolve(row, "cancelled", now, reason))
        return "cancelled", None
    if in_flight:
        # A prior claim never reported back: its outcome is unknown, so reconcile, never resend.
        notes.change(
            db,
            row,
            "unknown",
            now,
            state="unknown",
            reason="ambiguous_outcome",
            attempt_started_at=None,
            next_attempt_at=now + notes.RECONCILE_INTERVAL,
        )
        return "unknown", None
    if row.state == "unknown":
        return "reconcile", row
    policy = reminders.policy_document(db.get(ReminderPreferences, user.id))
    if not policy["enabled"]:
        if row.reason == "paused":
            return "skipped", None
        # Park once, recording why; the row stays pending (not cancelled) and is selected again
        # only after the owner resumes.
        notes.change(db, row, "deferred", now, reason="paused", next_attempt_at=now)
        return "deferred", None
    reason = "quiet_hours" if is_quiet(now, policy) else None
    if not reason:
        zone = ZoneInfo(policy["timezone"])
        day = now.astimezone(zone).date()
        counted = db.scalars(
            select(NotificationDeliveryEvent.recorded_at).where(
                NotificationDeliveryEvent.owner_id == user.id,
                NotificationDeliveryEvent.operation.in_(COUNTED),
                NotificationDeliveryEvent.recorded_at >= now - timedelta(hours=48),
            )
        ).all()
        if (
            sum(identity.aware(at).astimezone(zone).date() == day for at in counted)
            >= policy["daily_limit"]
        ):
            reason = "daily_limit"
    if reason:
        notes.change(
            db,
            row,
            "deferred",
            now,
            reason=reason,
            next_attempt_at=next_allowed(now, policy, next_day=reason == "daily_limit"),
        )
        return "deferred", None
    notes.change(
        db,
        row,
        "attempted",
        now,
        attempts=row.attempts + 1,
        attempt_started_at=now,
        reason=None,
    )
    return "send", row


def finish_send(db, candidate, outcome):
    # Same order as claim (recipient, then delivery): the event insert needs a key-share on the
    # user, so locking the row first would deadlock against a concurrent claim.
    lock_owner(db, candidate.owner_id, candidate.scope_key)
    row = lock_row(db, candidate.id)
    if row is None or row.state != "pending" or row.attempt_started_at is None:
        return "skipped"
    now = identity.now_utc()
    if outcome == notes.Outcome.ACCEPTED:
        notes.change(db, row, "delivered", now, **notes.resolve(row, "delivered", now))
        return "delivered"
    if outcome == notes.Outcome.REJECTED:
        notes.change(db, row, "failed", now, **notes.resolve(row, "failed", now, "rejected"))
        return "failed"
    if outcome == notes.Outcome.TIMEOUT:
        notes.change(
            db,
            row,
            "unknown",
            now,
            state="unknown",
            reason="ambiguous_outcome",
            attempt_started_at=None,
            next_attempt_at=now + notes.RECONCILE_INTERVAL,
        )
        return "unknown"
    if row.attempts >= notes.MAX_ATTEMPTS:
        reason = "attempts_exhausted"
        notes.change(db, row, "failed", now, **notes.resolve(row, "failed", now, reason))
        return "failed"
    notes.change(
        db,
        row,
        "retry_scheduled",
        now,
        reason="transient_error",
        attempt_started_at=None,
        next_attempt_at=now + notes.BACKOFF[row.attempts - 1],
    )
    return "retried"


def reconcile(db, candidate, found):
    lock_owner(db, candidate.owner_id, candidate.scope_key)
    row = lock_row(db, candidate.id)
    if row is None or row.state != "unknown":
        return "skipped"
    now = identity.now_utc()
    if found == notes.Lookup.DELIVERED:
        notes.change(db, row, "reconciled", now, **notes.resolve(row, "delivered", now))
        return "delivered"
    if found == notes.Lookup.UNAVAILABLE:
        # Keep the ambiguity visible; poll slowly rather than guessing or resending.
        notes.change(
            db,
            row,
            "unknown",
            now,
            reason="ambiguous_outcome",
            next_attempt_at=now + notes.BACKOFF[-1],
        )
        return "unknown"
    if row.attempts >= notes.MAX_ATTEMPTS:
        notes.change(
            db, row, "failed", now, **notes.resolve(row, "failed", now, "attempts_exhausted")
        )
        return "failed"
    notes.change(
        db,
        row,
        "reconciled",
        now,
        state="pending",
        reason="reconciled_absent",
        attempt_started_at=None,
        next_attempt_at=now,
    )
    return "retried"


def process(maker, candidate, channel):
    with maker.begin() as db:
        action, row = claim(db, candidate)
        key = str(row.id) if row else None
        recipient = row.recipient_ref if row else None
    if action == "send":
        try:
            outcome = channel.send(key, recipient)
        except Exception:  # noqa: BLE001 - unknown channel failure is an ambiguous outcome
            outcome = notes.Outcome.TIMEOUT
        with maker.begin() as db:
            return finish_send(db, candidate, outcome)
    if action == "reconcile":
        try:
            found = channel.lookup(key)
        except Exception:  # noqa: BLE001 - lookup failure keeps the ambiguity
            found = notes.Lookup.UNAVAILABLE
        with maker.begin() as db:
            return reconcile(db, candidate, found)
    return action


def run_once(channel, maker=SessionLocal, limit=100):
    if not 1 <= limit <= 100:
        raise ValueError("A bounded pass is required")
    result = {
        "enqueued": 0,
        "checked": 0,
        "delivered": 0,
        "retried": 0,
        "deferred": 0,
        "unknown": 0,
        "failed": 0,
        "cancelled": 0,
        "skipped": 0,
        "errors": 0,
    }
    try:
        with maker.begin() as db:
            result["enqueued"] = enqueue_pass(db, limit)
        with maker.begin() as db:
            batch = candidates(db, limit)
    except SQLAlchemyError:
        result["errors"] += 1
        return result
    result["checked"] = len(batch)
    for item in batch:
        try:
            outcome = process(maker, item, channel)
        except (SQLAlchemyError, ValueError, ZoneInfoNotFoundError):
            # Failed transactions roll back; an uncommitted claim never started a send.
            result["errors"] += 1
            continue
        result[outcome] += 1
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Restricted notification worker; synthetic channel only, no provider"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true")
    group.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    if settings.env not in {"development", "test"} or settings.postgres_user != "butler_runtime":
        raise RuntimeError(
            "Notification worker requires development/test restricted runtime credentials"
        )
    if settings.env == "test" and not settings.postgres_db.startswith("butler_test"):
        raise RuntimeError("Disposable test database required")
    channel = notes.SyntheticChannel()
    while True:
        result = run_once(channel)
        print(
            "Synthetic notification pass: "
            + ", ".join(f"{key}={value}" for key, value in result.items()),
            flush=True,
        )
        if args.once:
            if result.get("errors"):
                raise SystemExit(1)
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
