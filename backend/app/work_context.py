"""Explicit ephemeral confirmed-note context; no dispatch or persistent bundle."""

import hmac
import json
from datetime import timedelta
from uuid import UUID

from pydantic import Field, ValidationError, model_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import identity, work_access, work_authority, work_lifecycle, work_read, work_review
from app.config import settings
from app.models import WorkWorkspace


class Selection(work_review.Preview):
    id: UUID
    expected_revision: int = Field(strict=True, ge=1, le=100)


class Preview(work_review.Preview):
    selections: list[Selection] = Field(min_length=1, max_length=10)
    max_bytes: int = Field(strict=True, ge=256, le=16384, default=8192)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({item.id for item in self.selections}) != len(self.selections):
            raise ValueError("Duplicate selection")
        return self


def local_target():
    return settings.env in {"development", "test"} and (
        settings.env != "test" or settings.postgres_db.startswith("butler_test")
    )


def get_context_engines():
    return (
        work_read.get_work_engines()
        if settings.work_context_preview_enabled and local_target()
        else None
    )


def preview(db, token, csrf, workspace_id, body, engines):
    authority = work_authority.resolve(db, token)
    if isinstance(authority, identity.Result):
        return authority
    user = authority.user
    if (
        not csrf
        or len(csrf) > 128
        or not hmac.compare_digest(authority.session.csrf_hash, identity.digest(csrf))
    ):
        return identity.denied(db, 403, "work.context_csrf_denied", user=user)
    if db.scalar(work_access.assigned(user).where(WorkWorkspace.id == workspace_id)) is None:
        return identity.denied(db, 404, "work.context_denied", user=user)
    try:
        if engines is None or not local_target():
            raise work_read.BrokerUnavailable("Synthetic context unavailable")
        ids = [item.id for item in body.selections]
        with engines.lease(workspace_id) as engine:
            if engine is None:
                raise work_read.BrokerUnavailable("Synthetic context unavailable")
            work_read.same_target(db, engine)
            oid = db.scalar(text("SELECT oid FROM pg_database WHERE datname=current_database()"))
            with engine.connect() as connection, connection.begin():
                connection.execute(text("SET LOCAL lock_timeout='2s'"))
                connection.execute(text("SET LOCAL statement_timeout='5s'"))
                try:
                    work_read.restricted_identity(connection, oid, workspace_id)
                except work_read.BrokerUnavailable:
                    connection.invalidate()
                    raise
                work_review._clock(authority)
                rows = connection.execute(
                    text(
                        "SELECT snapshot FROM work.drafts WHERE workspace_id=:workspace AND id=ANY(:ids) AND state='confirmed' AND retain_until>clock_timestamp() ORDER BY id FOR SHARE"
                    ),
                    {"workspace": workspace_id, "ids": ids},
                ).all()
                if len(rows) != len(ids):
                    raise work_review.Rejected(404)
                records = {
                    item.id: item
                    for item in (work_lifecycle.Record.model_validate(row.snapshot) for row in rows)
                }
                ordered = [records[item.id] for item in body.selections]
                if any(
                    item.workspace_id != workspace_id
                    or item.state != "confirmed"
                    or not item.source_ids
                    for item in ordered
                ):
                    raise work_read.BrokerUnavailable("Synthetic context unavailable")
                if any(
                    item.revision != choice.expected_revision
                    for item, choice in zip(ordered, body.selections, strict=True)
                ):
                    raise work_review.Rejected(409)
                items = [item.model_dump(mode="json") for item in ordered]
                size = len(
                    json.dumps(
                        items,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    ).encode("utf-8")
                )
                if size > body.max_bytes:
                    raise work_review.Rejected(413)
                for item in ordered:
                    connection.execute(
                        text(
                            "INSERT INTO work.draft_audit(workspace_id,record_id,revision,actor_id,event_type) VALUES(:workspace,:record,:revision,:actor,'draft.read_prepared')"
                        ),
                        {
                            "workspace": workspace_id,
                            "record": item.id,
                            "revision": item.revision,
                            "actor": user.id,
                        },
                    )
                now = connection.scalar(text("SELECT clock_timestamp()"))
                if any(item.retain_until <= now for item in ordered):
                    raise work_review.Rejected(404)
                work_review._clock(authority)
        checked = work_review._clock(authority)
        if any(item.retain_until <= checked for item in ordered):
            raise work_review.Rejected(404)
        expiry = min(
            [checked + timedelta(seconds=60), identity.aware(authority.session.expires_at)]
            + [item.retain_until for item in ordered]
        )
        authority.session.last_seen_at = checked
        identity.audit(
            db,
            "work.context_preview",
            "success",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
            metadata={
                "records": [{"id": str(item.id), "revision": item.revision} for item in ordered],
                "items_bytes": size,
            },
        )
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "mode": "synthetic_work_context_preview",
                "workspace_id": str(workspace_id),
                "generated_at": checked.isoformat(),
                "valid_until": expiry.isoformat(),
                "items": items,
                "items_bytes": size,
                "max_bytes": body.max_bytes,
                "reference_only": True,
                "model_invoked": False,
                "execution_allowed": False,
                "ingestion_allowed": False,
            },
        )
    except work_review.Rejected as error:
        return identity.denied(db, error.status, "work.context_denied", user=user)
    except (SQLAlchemyError, work_read.BrokerUnavailable, ValidationError):
        identity.audit(
            db,
            "work.context_unavailable",
            "denied",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
        )
        return identity.Result(503, {"detail": "Synthetic context unavailable"})
