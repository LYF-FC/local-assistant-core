"""Current-human synthetic note changes; private preparation, never API note writes."""

import hmac
import json
from datetime import timedelta
from typing import Literal
from uuid import UUID

from pydantic import Field, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import (
    identity,
    work_access,
    work_authority,
    work_capture,
    work_context,
    work_lifecycle,
    work_read,
    work_review,
)
from app.config import settings
from app.models import WorkWorkspace


class Correct(work_lifecycle.Contract):
    request_id: UUID
    expected_revision: int = Field(strict=True, ge=1, le=99)
    decision: Literal["correct_note"]
    draft: work_capture.Draft


class Forget(work_lifecycle.Contract):
    request_id: UUID
    expected_revision: int = Field(strict=True, ge=1, le=100)
    decision: Literal["forget_note"]


def get_change_engines():
    return (
        work_read.get_work_engines()
        if settings.work_note_changes_enabled and work_context.local_target()
        else None
    )


def result(row, *, replayed=False):
    return identity.Result(
        202 if row.state == "pending" else 200,
        {
            "schema_version": 1,
            "mode": "synthetic_note_change",
            "change_request_id": str(row.id),
            "operation": row.intent,
            "state": row.state,
            "change_applied": row.state == "applied",
            "record_id": str(row.record_id) if row.record_id else None,
            "revision": row.result_revision,
            "expires_at": row.expires_at.isoformat(),
            "replayed": replayed,
            "confirmation_applied": False,
            "model_invoked": False,
            "execution_allowed": False,
            "real_ingestion_allowed": False,
        },
    )


def _correction(connection, values, body, now):
    row = connection.execute(
        text(
            "SELECT snapshot FROM work.drafts WHERE workspace_id=:workspace AND id=:target AND state IN ('draft','confirmed') AND retain_until>clock_timestamp() FOR SHARE"
        ),
        values,
    ).one_or_none()
    if row is None:
        raise work_review.Rejected(404)
    current = work_lifecycle.Record.model_validate(row.snapshot)
    if (
        current.revision != body.expected_revision
        or current.kind != body.draft.kind
        or not now < body.draft.retain_until <= current.retain_until
    ):
        raise work_review.Rejected(409)
    policy = connection.scalar(
        text(
            "SELECT max_age_seconds FROM work.retention_policies WHERE workspace_id=:workspace AND id=:policy"
        ),
        dict(values, policy=current.policy_id),
    )
    if policy is None or body.draft.retain_until > now + timedelta(seconds=policy):
        raise work_review.Rejected(409)
    sources = (
        connection.execute(
            text(
                "SELECT id FROM work.source_registry WHERE workspace_id=:workspace AND is_active AND id=ANY(:sources)"
            ),
            dict(values, sources=list(body.draft.source_ids)),
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
    return {"policy_id": str(current.policy_id), "draft": body.draft.model_dump(mode="json")}


def prepare(db, token, csrf, workspace_id, engines, target=None, body=None, command=None):
    authority = work_authority.resolve(db, token)
    if isinstance(authority, identity.Result):
        return authority
    user = authority.user
    if (
        not csrf
        or len(csrf) > 128
        or not hmac.compare_digest(authority.session.csrf_hash, identity.digest(csrf))
    ):
        return identity.denied(db, 403, "work.note_change_csrf_denied", user=user)
    if (
        db.scalar(
            work_access.assigned(user).where(
                WorkWorkspace.id == workspace_id, WorkWorkspace.slug.like("synthetic-%")
            )
        )
        is None
    ):
        return identity.denied(db, 404, "work.note_change_denied", user=user)
    try:
        if engines is None or not work_context.local_target():
            raise work_read.BrokerUnavailable("Synthetic note change unavailable")
        values = {"workspace": workspace_id, "actor": user.id, "session": authority.session.id}
        with engines.lease(workspace_id) as engine:
            if engine is None:
                raise work_read.BrokerUnavailable("Synthetic note change unavailable")
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
                            "SELECT * FROM work.capture_intents WHERE workspace_id=:workspace AND id=:command AND actor_id=:actor AND session_id=:session AND intent IN ('correct_note','forget_note')"
                        ),
                        dict(values, command=command),
                    ).one_or_none()
                    if row is None:
                        raise work_review.Rejected(404)
                    replayed = False
                else:
                    values.update(
                        target=target,
                        nonce=body.request_id,
                        intent=body.decision,
                        revision=body.expected_revision,
                    )
                    metadata = connection.execute(
                        text(
                            "SELECT revision,state FROM work.note_metadata WHERE workspace_id=:workspace AND id=:target"
                        ),
                        values,
                    ).one_or_none()
                    if metadata is None:
                        raise work_review.Rejected(404)
                    if metadata.state == "forgotten" or metadata.revision != body.expected_revision:
                        raise work_review.Rejected(409)
                    now = connection.scalar(text("SELECT clock_timestamp()"))
                    payload = (
                        _correction(connection, values, body, now)
                        if isinstance(body, Correct)
                        else {"forget": True}
                    )
                    expiry = min(
                        now + timedelta(minutes=5), identity.aware(authority.session.expires_at)
                    )
                    if isinstance(body, Correct):
                        expiry = min(expiry, body.draft.retain_until)
                    values.update(payload=json.dumps(payload), expires=expiry)
                    row = connection.execute(
                        text(
                            "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,intent,target_record_id,expected_revision,payload,expires_at) VALUES(:workspace,:actor,:session,:nonce,:intent,:target,:revision,CAST(:payload AS jsonb),:expires) ON CONFLICT(workspace_id,actor_id,session_id,request_id) DO NOTHING RETURNING *"
                        ),
                        values,
                    ).one_or_none()
                    replayed = row is None
                    if row is None:
                        row = connection.execute(
                            text(
                                "SELECT * FROM work.capture_intents WHERE workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND request_id=:nonce AND intent=:intent AND target_record_id=:target AND expected_revision=:revision AND state='pending' AND expires_at>clock_timestamp() AND payload=CAST(:payload AS jsonb)"
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
            "work.note_change_status" if command else "work.note_change_requested",
            "success",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
            metadata={"change_request_id": str(row.id), "session_id": str(authority.session.id)},
        )
        return result(row, replayed=replayed)
    except work_review.Rejected as error:
        return identity.denied(db, error.status, "work.note_change_denied", user=user)
    except (SQLAlchemyError, work_read.BrokerUnavailable, ValidationError):
        identity.audit(
            db,
            "work.note_change_unavailable",
            "denied",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
        )
        return identity.Result(503, {"detail": "Synthetic note change unavailable"})
