"""Bounded, metadata-only observations; never a monitoring or activation authority."""

import re
from collections import Counter
from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version
from platform import python_version
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text

from app import identity
from app.config import settings
from app.manual_tasks import authority, stamp
from app.models import DurableJob

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
