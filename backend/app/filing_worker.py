"""Restricted worker applying approved filing requests to a synthetic destination.

The effect happens outside any database transaction. The attempt claim commits first, so a
crash or timeout leaves an in-flight mark that is reconciled by lookup and never re-applied.
Locks always run: owner, source and review (shared), then the filing row.
"""

import argparse
import time

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app import filing, identity
from app.config import settings
from app.db import SessionLocal
from app.models import DocumentRecord, FilingExecution
from app.models import InvoiceReview as Review
from app.notification_worker import lock_owner


def lock_row(db, execution_id):
    return db.scalar(
        select(FilingExecution)
        .where(FilingExecution.id == execution_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def candidates(db, limit):
    now = identity.now_utc()
    stale = now - filing.IN_FLIGHT_DEADLINE
    return list(
        db.execute(
            select(
                FilingExecution.id,
                FilingExecution.owner_id,
                FilingExecution.scope_key,
                FilingExecution.document_id,
            )
            .where(
                or_(
                    and_(
                        FilingExecution.state.in_(("pending", "unknown")),
                        FilingExecution.next_attempt_at <= now,
                        FilingExecution.attempt_started_at.is_(None),
                    ),
                    and_(
                        FilingExecution.state == "pending",
                        FilingExecution.attempt_started_at <= stale,
                    ),
                )
            )
            .order_by(FilingExecution.next_attempt_at, FilingExecution.id)
            .limit(limit)
        )
    )


def lock_plan(db, document_id):
    """Shared locks on the source and its review; always taken before the filing row."""
    source = db.scalar(
        select(DocumentRecord)
        .where(DocumentRecord.id == document_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    review = db.scalar(
        select(Review)
        .where(Review.document_id == document_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    return source, review


def inspect(row, user, granted, source, review):
    """Return (cancel_reason, effect) for the exact approved plan this row is bound to."""
    if user is None or not user.is_active:
        return "owner_unavailable", None
    if not granted:
        return "scope_unavailable", None
    plan = filing.current_plan(source, review)
    if (
        plan is None
        or review.revision != row.plan_revision
        or source.revision != row.source_revision
        or source.owner_id != row.owner_id
        or review.owner_id != row.owner_id
        or source.scope_key != row.scope_key
    ):
        return "plan_changed", None
    try:
        key = filing.destination_key(row.scope_key, plan["relative_path"])
        path = filing.canonical_path(plan["relative_path"])
    except ValueError:
        return "plan_changed", None
    if key != row.destination_key:
        return "plan_changed", None
    return None, (path, source.sha256, source.byte_size)


def claim(db, candidate):
    # Lock order everywhere: owner, source, review, filing row. Forgetting follows the same order.
    user, granted = lock_owner(db, candidate.owner_id, candidate.scope_key)
    source, review = lock_plan(db, candidate.document_id)
    row = lock_row(db, candidate.id)
    if row is None or row.state not in {"pending", "unknown"} or row.scrubbed_at is not None:
        return "skipped", None
    now = identity.now_utc()
    in_flight = row.state == "pending" and row.attempt_started_at is not None
    if in_flight and identity.aware(row.attempt_started_at) > now - filing.IN_FLIGHT_DEADLINE:
        return "skipped", None
    if not in_flight and (row.next_attempt_at is None or identity.aware(row.next_attempt_at) > now):
        return "skipped", None
    if in_flight:
        # A prior claim never reported back: its effect may exist, so reconcile, never re-apply.
        filing.change(
            db,
            row,
            "unknown",
            now,
            state="unknown",
            reason="ambiguous_outcome",
            attempt_started_at=None,
            next_attempt_at=now + filing.RECONCILE_INTERVAL,
        )
        return "unknown", None
    if row.state == "unknown":
        return "reconcile", str(row.id)
    reason, effect = inspect(row, user, granted, source, review)
    if reason:
        filing.change(db, row, "cancelled", now, **filing.resolve("cancelled", now, reason))
        return "cancelled", None
    filing.change(
        db,
        row,
        "attempted",
        now,
        attempts=row.attempts + 1,
        attempt_started_at=now,
        # The authorization is consumed by the first claim, in the same atomic update.
        authorization_consumed_at=row.authorization_consumed_at or now,
        reason=None,
    )
    return "apply", (str(row.id), *effect)


def finish(db, candidate, outcome):
    lock_owner(db, candidate.owner_id, candidate.scope_key)
    row = lock_row(db, candidate.id)
    if row is None or row.state != "pending" or row.attempt_started_at is None:
        return "skipped"
    now = identity.now_utc()
    if outcome == filing.Outcome.ACCEPTED:
        filing.change(db, row, "filed", now, **filing.resolve("filed", now))
        return "filed"
    if outcome == filing.Outcome.COLLISION:
        filing.change(db, row, "failed", now, **filing.resolve("failed", now, "collision"))
        return "failed"
    if outcome == filing.Outcome.TIMEOUT:
        filing.change(
            db,
            row,
            "unknown",
            now,
            state="unknown",
            reason="ambiguous_outcome",
            attempt_started_at=None,
            next_attempt_at=now + filing.RECONCILE_INTERVAL,
        )
        return "unknown"
    if row.attempts >= filing.MAX_ATTEMPTS:
        filing.change(db, row, "failed", now, **filing.resolve("failed", now, "attempts_exhausted"))
        return "failed"
    filing.change(
        db,
        row,
        "retry_scheduled",
        now,
        reason="transient_error",
        attempt_started_at=None,
        next_attempt_at=now + filing.BACKOFF[row.attempts - 1],
    )
    return "retried"


def reconcile(db, candidate, found):
    lock_owner(db, candidate.owner_id, candidate.scope_key)
    row = lock_row(db, candidate.id)
    if row is None or row.state != "unknown":
        return "skipped"
    now = identity.now_utc()
    if found == filing.Lookup.FILED:
        filing.change(db, row, "reconciled", now, **filing.resolve("filed", now))
        return "filed"
    if found == filing.Lookup.UNAVAILABLE:
        filing.change(
            db,
            row,
            "unknown",
            now,
            reason="ambiguous_outcome",
            next_attempt_at=now + filing.BACKOFF[-1],
        )
        return "unknown"
    if row.attempts >= filing.MAX_ATTEMPTS:
        filing.change(db, row, "failed", now, **filing.resolve("failed", now, "attempts_exhausted"))
        return "failed"
    filing.change(
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


def process(maker, candidate, destination):
    with maker.begin() as db:
        action, payload = claim(db, candidate)
    if action == "apply":
        key, path, sha256, size = payload
        try:
            outcome = destination.put(key, path, sha256, size)
        except Exception:  # noqa: BLE001 - an unknown destination failure is ambiguous
            outcome = filing.Outcome.TIMEOUT
        with maker.begin() as db:
            return finish(db, candidate, outcome)
    if action == "reconcile":
        try:
            found = destination.lookup(payload)
        except Exception:  # noqa: BLE001 - lookup failure keeps the ambiguity visible
            found = filing.Lookup.UNAVAILABLE
        with maker.begin() as db:
            return reconcile(db, candidate, found)
    return action


def run_once(destination, maker=SessionLocal, limit=100):
    if not 1 <= limit <= 100:
        raise ValueError("A bounded pass is required")
    result = {
        key: 0
        for key in (
            "checked",
            "filed",
            "retried",
            "unknown",
            "failed",
            "cancelled",
            "skipped",
            "errors",
        )
    }
    try:
        with maker.begin() as db:
            batch = candidates(db, limit)
    except SQLAlchemyError:
        result["errors"] += 1
        return result
    result["checked"] = len(batch)
    for item in batch:
        try:
            result[process(maker, item, destination)] += 1
        except (SQLAlchemyError, ValueError):
            # A failed transaction rolls back; an uncommitted claim never started an effect.
            result["errors"] += 1
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Restricted filing worker; synthetic destination only, no filesystem"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true")
    group.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    if settings.env not in {"development", "test"} or settings.postgres_user != "butler_runtime":
        raise RuntimeError("Filing worker requires development/test restricted runtime credentials")
    if settings.env == "test" and not settings.postgres_db.startswith("butler_test"):
        raise RuntimeError("Disposable test database required")
    destination = filing.SyntheticDestination()
    while True:
        result = run_once(destination)
        print(
            "Synthetic filing pass: " + ", ".join(f"{k}={v}" for k, v in result.items()),
            flush=True,
        )
        if args.once:
            if result.get("errors"):
                raise SystemExit(1)
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
