"""Bounded, metadata-only observations; never a monitoring or activation authority."""

import re
from collections import Counter
from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version
from platform import python_version
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select, text

from app import identity
from app import queue_eligibility as eligible
from app.config import settings
from app.manual_tasks import authority, stamp
from app.models import (
    DurableJob,
    FilingExecution,
    JobOutbox,
    NotificationDelivery,
    ReminderPreferences,
    TaskReminder,
)

COMPONENTS = (
    "api",
    "database",
    "archive",
    "pdf_parser",
    "local_answers",
    "workers",
    "storage_capacity",
    "backup_restore",
    "certificates",
    "independent_observer",
    "remote_hardware",
)
PACKAGES = ("fastapi", "sqlalchemy", "psycopg", "pydantic")
JOB_STATES = ("queued", "running", "succeeded", "dead_letter")


class Read(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    scope: Literal["technical_admin"]


AUDIT_CATEGORIES = (
    "sign_in",
    "denied_access",
    "access_change",
    "recovery_admin",
    "other_admin",
    "operations_read",
    "other_security",
)
AUDIT_OUTCOMES = ("success", "denied", "other")
AUDIT_WINDOWS = {"24h": 24, "7d": 168}
AUDIT_EXCLUDES = ("content_domain_events", "overdue_jobs", "capacity", "per_event_detail")


class AuditSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    scope: Literal["technical_admin"]
    window: Literal["24h", "7d"]


# Spec 073: queue-level overdue/stalled observation. States only; never counts, ages, owners,
# scopes, ids, payloads, recipients, destinations, reasons or attempts.
WORK_GRACE = timedelta(seconds=120)
WORK_LOCK_TIMEOUT = "2s"
WORK_STATEMENT_TIMEOUT = "5s"
WORK_QUEUES = ("approved_jobs", "reminders", "notifications", "filing")
WORK_STATES = ("none_observed", "overdue", "stalled")
WORK_NOT_OBSERVED = ("calendar_sync", "routines", "work")
WORK_EXCLUDES = (
    "counts",
    "ages",
    "owners_and_scopes",
    "items",
    "worker_liveness",
    "capacity",
    "backups",
    "restore",
)


class WorkStatusRead(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    scope: Literal["technical_admin"]


def safe_version(value):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}", value)
        else None
    )


def installed_version(package):
    try:
        return safe_version(version(package))
    except PackageNotFoundError:
        return None


def inventory():
    return [
        {"key": key, "version": value, "source": source, "assessment": "not_assessed"}
        for key, value, source in (
            ("api_build", safe_version(settings.app_version), "declared_build"),
            ("python", safe_version(python_version()), "runtime_metadata"),
            *((name, installed_version(name), "runtime_metadata") for name in PACKAGES),
        )
    ]


def components():
    configured = {
        "archive": settings.document_archive_directory is not None,
        "pdf_parser": settings.pdf_socket_directory is not None,
        "local_answers": settings.document_answers_enabled,
    }
    return [
        {
            "key": key,
            "state": "observed"
            if key in {"api", "database"}
            else "configured_unverified"
            if configured.get(key)
            else "disabled"
            if key == "local_answers"
            else "unknown",
        }
        for key in COMPONENTS
    ]


def read(db, token, csrf, body):
    current = authority(
        db, token, csrf, body.scope, event_prefix="operations", scope_lock="installation"
    )
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    checked = identity.now_utc()
    start = checked - timedelta(hours=24)
    # An authenticated transaction query is the only database reachability probe.
    db.execute(text("SELECT 1"))
    statuses = list(
        db.scalars(
            select(DurableJob.status)
            .where(
                DurableJob.scope_key == "technical_admin",
                DurableJob.requested_by == user.id,
                DurableJob.created_at >= start,
                DurableJob.created_at <= checked,
            )
            .order_by(DurableJob.created_at.desc(), DurableJob.id.desc())
            .limit(26)
        )
    )
    # A long query/lock wait must not revive an expired session or stale receipt.
    now = identity.now_utc()
    if identity.resolve(db, token, refresh_session=True) is None or now >= checked + timedelta(
        seconds=60
    ):
        return identity.denied(db, 401, "operations.session_denied", user=user)
    counts = Counter(s if s in JOB_STATES else "other" for s in statuses[:25])
    payload = {
        "schema_version": 1,
        "scope": "technical_admin",
        "actor_id": str(user.id),
        "checked_at": stamp(checked),
        "valid_until": stamp(checked + timedelta(seconds=60)),
        "window_start": stamp(start),
        "window_end": stamp(checked),
        "components": components(),
        "software": inventory(),
        "activity": {"state": "not_available"},
        "jobs": {
            "sampled": min(len(statuses), 25),
            "has_more": len(statuses) > 25,
            "counts": {key: counts[key] for key in (*JOB_STATES, "other")},
        },
    }
    identity.audit(
        db,
        "operations.read",
        "success",
        user=user,
        scope="technical_admin",
        metadata={"jobs_sampled": min(len(statuses), 25)},
    )
    return identity.Result(200, payload)


def audit_summary(db, token, csrf, body):
    """Count-only security/administrative audit summary through the reviewed projection.

    The runtime role has no audit SELECT; the only read path is the SECURITY DEFINER function
    from migration 0037, which returns aggregates for a closed catalogue and nothing else.
    """
    current = authority(
        db, token, csrf, body.scope, event_prefix="operations", scope_lock="installation"
    )
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    if db.get_bind().dialect.name != "postgresql":
        # The projection exists only in PostgreSQL; never fabricate counts elsewhere.
        return identity.Result(503, {"detail": "Audit summary is unavailable"})
    db.execute(text("SET LOCAL lock_timeout='2s'"))
    db.execute(text("SET LOCAL statement_timeout='5s'"))
    checked = identity.now_utc()
    hours = AUDIT_WINDOWS[body.window]
    rows = db.execute(
        text(
            "SELECT category_key, outcome_key, event_count FROM public.butler_audit_summary(:a,:e,:h)"
        ),
        {"a": token, "e": checked, "h": hours},
    ).all()
    counts = {(category, outcome): 0 for category in AUDIT_CATEGORIES for outcome in AUDIT_OUTCOMES}
    for category, outcome, number in rows:
        if (category, outcome) not in counts or not isinstance(number, int) or number < 0:
            raise RuntimeError("Unexpected audit summary row")
        counts[(category, outcome)] = number
    now = identity.now_utc()
    if identity.resolve(db, token, refresh_session=True) is None or now >= checked + timedelta(
        seconds=60
    ):
        return identity.denied(db, 401, "operations.session_denied", user=user)
    payload = {
        "schema_version": 1,
        "scope": "technical_admin",
        "actor_id": str(user.id),
        "checked_at": stamp(checked),
        "valid_until": stamp(checked + timedelta(seconds=60)),
        "window": body.window,
        "window_start": stamp(checked - timedelta(hours=hours)),
        "window_end": stamp(checked),
        "categories": [
            {
                "key": category,
                **{outcome: counts[(category, outcome)] for outcome in AUDIT_OUTCOMES},
            }
            for category in AUDIT_CATEGORIES
        ],
        "totals": {
            outcome: sum(counts[(category, outcome)] for category in AUDIT_CATEGORIES)
            for outcome in AUDIT_OUTCOMES
        },
        "excludes": list(AUDIT_EXCLUDES),
    }
    identity.audit(
        db,
        "operations.audit_summary",
        "success",
        user=user,
        scope="technical_admin",
        metadata={"window": body.window},
    )
    return identity.Result(200, payload)


def work_queries(c):
    """Observer rules at cutoff ``c = now - WORK_GRACE`` (spec 073 §1.4).

    Each queue maps to its stalled and overdue existence queries. They reuse the workers' own
    eligibility rules E1–E8 and add observer-only eligible-since guards: the row's eligibility
    inputs (and, where preferences decide eligibility, the owner's preferences) must not have
    changed since ``c``. These guards exist only here; workers never use them, so the grace
    period cannot delay or reorder worker selection. The inference assumes a non-decreasing
    application clock (spec 073 §1.4.1).
    """
    unchanged_preferences = or_(
        ReminderPreferences.owner_id.is_(None), ReminderPreferences.updated_at <= c
    )
    return {
        "approved_jobs": {
            "stalled": [select(JobOutbox.id).where(eligible.job_lease_expired(c))],
            "overdue": [select(JobOutbox.id).where(eligible.job_pending(c))],
        },
        "reminders": {
            # Reminder processing has no lease or in-flight marker: never stalled.
            "stalled": [],
            "overdue": [
                select(TaskReminder.id)
                .outerjoin(ReminderPreferences, eligible.preferences_on_reminder())
                .where(
                    eligible.reminder_due(c),
                    TaskReminder.updated_at <= c,
                    unchanged_preferences,
                )
            ],
        },
        "notifications": {
            "stalled": [
                select(NotificationDelivery.id)
                .outerjoin(ReminderPreferences, eligible.preferences_on_delivery())
                .where(eligible.notification_in_flight_expired(c))
            ],
            "overdue": [
                # Stage 1 (enqueue) only: eligibility to enqueue is not permission to send.
                select(TaskReminder.id)
                .outerjoin(NotificationDelivery, eligible.enqueue_on())
                .where(eligible.notification_enqueue_eligible(), TaskReminder.delivered_at <= c),
                select(NotificationDelivery.id)
                .outerjoin(ReminderPreferences, eligible.preferences_on_delivery())
                .where(
                    eligible.notification_due(c),
                    NotificationDelivery.updated_at <= c,
                    # A resumed paused delivery became eligible when preferences changed.
                    or_(
                        NotificationDelivery.reason.is_distinct_from("paused"),
                        ReminderPreferences.updated_at <= c,
                    ),
                ),
            ],
        },
        "filing": {
            "stalled": [select(FilingExecution.id).where(eligible.filing_in_flight_expired(c))],
            "overdue": [
                select(FilingExecution.id).where(
                    eligible.filing_due(c), FilingExecution.updated_at <= c
                )
            ],
        },
    }


def observe_work(db, c):
    """Return one state per queue in WORK_QUEUES order: stalled, else overdue, else none."""
    rules = work_queries(c)
    states = []
    for key in WORK_QUEUES:
        if any(db.scalar(select(query.exists())) for query in rules[key]["stalled"]):
            state = "stalled"
        elif any(db.scalar(select(query.exists())) for query in rules[key]["overdue"]):
            state = "overdue"
        else:
            state = "none_observed"
        states.append({"key": key, "state": state})
    return states


def work_status(db, token, csrf, body):
    """Queue-level overdue/stalled work observation for a technical administrator (spec 073).

    Household-wide and derived from members' private records, so it returns one state per
    queue and nothing else (owner decision D1). It is not a worker-health check.
    """
    current = authority(
        db, token, csrf, body.scope, event_prefix="operations", scope_lock="installation"
    )
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    if db.get_bind().dialect.name == "postgresql":
        # Transaction-local, bound values (equivalent to SET LOCAL).
        db.execute(text("SELECT set_config('lock_timeout', :v, true)"), {"v": WORK_LOCK_TIMEOUT})
        db.execute(
            text("SELECT set_config('statement_timeout', :v, true)"),
            {"v": WORK_STATEMENT_TIMEOUT},
        )
    checked = identity.now_utc()
    queues = observe_work(db, checked - WORK_GRACE)
    now = identity.now_utc()
    if identity.resolve(db, token, refresh_session=True) is None or now >= checked + timedelta(
        seconds=60
    ):
        return identity.denied(db, 401, "operations.session_denied", user=user)
    payload = {
        "schema_version": 1,
        "scope": "technical_admin",
        "actor_id": str(user.id),
        "checked_at": stamp(checked),
        "valid_until": stamp(checked + timedelta(seconds=60)),
        "queues": queues,
        "not_observed": list(WORK_NOT_OBSERVED),
        "excludes": list(WORK_EXCLUDES),
    }
    # Metadata stays empty: no queue state is persisted, so no cross-member signal is kept.
    identity.audit(db, "operations.work_status", "success", user=user, scope="technical_admin")
    return identity.Result(200, payload)
