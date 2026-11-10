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
