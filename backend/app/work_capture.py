"""Current-human synthetic capture preparation; no note writer or owner credential."""

import hmac
import json
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import (
    identity,
    work_access,
    work_authority,
    work_context,
    work_lifecycle,
    work_read,
    work_review,
)
from app.config import settings
from app.models import WorkWorkspace


class Draft(work_lifecycle.Draft):
    source_ids: work_lifecycle.Sources = Field(min_length=1)


class Payload(work_lifecycle.Contract):
    policy_id: UUID
    draft: Draft


class Capture(Payload):
    request_id: UUID
    decision: Literal["capture_draft"]

    def content(self):
        return {"policy_id": str(self.policy_id), "draft": self.draft.model_dump(mode="json")}


def get_capture_engines():
    return (
        work_read.get_work_engines()
        if settings.work_synthetic_capture_enabled and work_context.local_target()
        else None
    )


def result(row, *, replayed=False):
    return identity.Result(
        202 if row.state == "pending" else 200,
        {
            "schema_version": 1,
            "mode": "synthetic_draft_capture",
            "capture_preparation_id": str(row.id),
            "state": row.state,
            "capture_applied": row.state == "applied",
            "record_id": str(row.record_id) if row.record_id else None,
            "revision": 1 if row.state == "applied" else None,
            "expires_at": row.expires_at.isoformat(),
            "replayed": replayed,
            "confirmation_applied": False,
            "execution_allowed": False,
            "model_invoked": False,
            "real_ingestion_allowed": False,
        },
    )


def prepare(db, token, csrf, workspace_id, engines, body=None, command=None):
    authority = work_authority.resolve(db, token)
    if isinstance(authority, identity.Result):
        return authority
    user = authority.user
    if (
        not csrf
        or len(csrf) > 128
        or not hmac.compare_digest(authority.session.csrf_hash, identity.digest(csrf))
    ):
        return identity.denied(db, 403, "work.capture_csrf_denied", user=user)
    if (
        db.scalar(
            work_access.assigned(user).where(
                WorkWorkspace.id == workspace_id, WorkWorkspace.slug.like("synthetic-%")
            )
        )
        is None
    ):
        return identity.denied(db, 404, "work.capture_denied", user=user)
    try:
        if engines is None or not work_context.local_target():
            raise work_read.BrokerUnavailable("Synthetic capture unavailable")
        values = {"workspace": workspace_id, "actor": user.id, "session": authority.session.id}
        with engines.lease(workspace_id) as engine:
            if engine is None:
                raise work_read.BrokerUnavailable("Synthetic capture unavailable")
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
                if command is not None:
                    row = connection.execute(
                        text(
                            "SELECT * FROM work.capture_intents WHERE intent='capture_draft' AND workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND id=:command"
                        ),
                        dict(values, command=command),
                    ).one_or_none()
                    if row is None:
                        raise work_review.Rejected(404)
                    replayed = False
                else:
                    values.update(nonce=body.request_id, payload=json.dumps(body.content()))
                    now = connection.scalar(text("SELECT clock_timestamp()"))
                    policy = connection.scalar(
                        text(
                            "SELECT max_age_seconds FROM work.retention_policies WHERE workspace_id=:workspace AND id=:policy"
                        ),
                        dict(values, policy=body.policy_id),
                    )
                    if policy is None:
                        raise work_review.Rejected(404)
                    from datetime import timedelta

                    if not now < body.draft.retain_until <= now + timedelta(seconds=policy):
                        raise work_review.Rejected(409)
                    sources = (
                        connection.execute(
                            text(
                                "SELECT id FROM work.source_registry WHERE workspace_id=:workspace AND is_active AND id=ANY(:ids)"
                            ),
                            dict(values, ids=list(body.draft.source_ids)),
                        )
                        .scalars()
                        .all()
                    )
                    if set(sources) != set(body.draft.source_ids):
                        raise work_review.Rejected(404)
                    if (
                        body.draft.owner_id is not None
                        and connection.scalar(
                            text(
                                "SELECT id FROM work.parties WHERE workspace_id=:workspace AND id=:owner AND state='active' AND retain_until>clock_timestamp()"
                            ),
                            dict(values, owner=body.draft.owner_id),
                        )
                        is None
                    ):
                        raise work_review.Rejected(404)
                    values["expires"] = min(
                        now + timedelta(minutes=5),
                        body.draft.retain_until,
                        identity.aware(authority.session.expires_at),
                    )
                    row = connection.execute(
                        text(
                            "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,payload,expires_at) VALUES(:workspace,:actor,:session,:nonce,CAST(:payload AS jsonb),:expires) ON CONFLICT(workspace_id,actor_id,session_id,request_id) DO NOTHING RETURNING *"
                        ),
                        values,
                    ).one_or_none()
                    replayed = row is None
                    if row is None:
                        row = connection.execute(
                            text(
                                "SELECT * FROM work.capture_intents WHERE workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND request_id=:nonce AND intent='capture_draft' AND state='pending' AND expires_at>clock_timestamp() AND payload=CAST(:payload AS jsonb)"
                            ),
                            values,
                        ).one_or_none()
                        if row is None:
                            raise work_review.Rejected(409)
                work_review._clock(authority)
        checked = work_review._clock(authority)
        if command is None and checked >= row.expires_at:
            raise work_review.Rejected(409)
        authority.session.last_seen_at = checked
        identity.audit(
            db,
            "work.capture_status" if command else "work.capture_requested",
            "success",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
            metadata={
                "capture_preparation_id": str(row.id),
                "session_id": str(authority.session.id),
            },
        )
        return result(row, replayed=replayed)
    except work_review.Rejected as error:
        return identity.denied(db, error.status, "work.capture_denied", user=user)
    except (SQLAlchemyError, work_read.BrokerUnavailable):
        identity.audit(
            db,
            "work.capture_unavailable",
            "denied",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
        )
        return identity.Result(503, {"detail": "Synthetic capture unavailable"})
