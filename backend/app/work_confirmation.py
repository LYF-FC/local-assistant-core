"""Authenticated metadata queue; no business writer or owner connection."""

import hmac
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import text

from app import identity, work_access, work_authority, work_read, work_review
from app.config import settings
from app.models import WorkWorkspace


class Confirmation(work_review.Preview):
    review_preparation_id: UUID
    expected_revision: int = Field(strict=True, ge=1, le=99)
    request_id: UUID
    decision: Literal["confirm_note"]


def _local_target():
    return settings.env in {"development", "test"} and (
        settings.env != "test" or settings.postgres_db.startswith("butler_test")
    )


def get_confirmation_engines():
    return (
        work_review.get_review_engines()
        if settings.work_draft_confirmation_enabled and _local_target()
        else None
    )


def _result(row, *, replayed=False):
    return identity.Result(
        202 if row.state == "pending" else 200,
        {
            "schema_version": 1,
            "mode": "synthetic_note_confirmation",
            "confirmation_request_id": str(row.id),
            "state": row.state,
            "confirmation_applied": row.state == "applied",
            "applied_revision": row.applied_revision,
            "expires_at": row.expires_at.isoformat(),
            "replayed": replayed,
            "execution_allowed": False,
            "model_invoked": False,
            "ingestion_allowed": False,
        },
    )


def request_confirmation(
    db, token, csrf, workspace_id, record_id, engines, body=None, command=None
):
    authority = work_authority.resolve(db, token)
    if isinstance(authority, identity.Result):
        return authority
    user = authority.user
    if (
        not csrf
        or len(csrf) > 128
        or not hmac.compare_digest(authority.session.csrf_hash, identity.digest(csrf))
    ):
        return identity.denied(db, 403, "work.confirmation_csrf_denied", user=user)
    if db.scalar(work_access.assigned(user).where(WorkWorkspace.id == workspace_id)) is None:
        return identity.denied(db, 404, "work.confirmation_denied", user=user)
    try:
        if engines is None or not _local_target():
            raise work_read.BrokerUnavailable("Synthetic confirmation unavailable")
        values = {"workspace": workspace_id, "actor": user.id, "session": authority.session.id}
        if command is not None:
            row = db.execute(
                text(
                    "SELECT * FROM public.work_confirmation_requests WHERE workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND id=:command"
                ),
                dict(values, command=command),
            ).one_or_none()
            if row is None:
                raise work_review.Rejected(404)
            work_review._clock(authority)
            identity.audit(db, "work.confirmation_status", "success", user=user)
            return _result(row)
        values.update(
            record=record_id,
            review=body.review_preparation_id,
            revision=body.expected_revision,
            nonce=body.request_id,
        )
        row = db.execute(
            text(
                "SELECT * FROM public.work_confirmation_requests WHERE workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND request_id=:nonce"
            ),
            values,
        ).one_or_none()
        if row is None:
            row = db.execute(
                text(
                    "SELECT * FROM public.work_confirmation_requests WHERE workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND review_preparation_id=:review"
                ),
                values,
            ).one_or_none()
        if row is not None:
            if (row.record_id, row.review_preparation_id, row.reviewed_revision) != (
                record_id,
                body.review_preparation_id,
                body.expected_revision,
            ):
                raise work_review.Rejected(409)
            work_review._clock(authority)
            identity.audit(db, "work.confirmation_replayed", "success", user=user)
            return _result(row, replayed=True)
        with engines.lease(workspace_id) as engine:
            if engine is None:
                raise work_read.BrokerUnavailable("Synthetic confirmation unavailable")
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
                item = connection.execute(
                    text(
                        "SELECT revision,retain_until,encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') AS payload_hash FROM work.drafts WHERE workspace_id=:workspace AND id=:record AND state='draft' AND retain_until>clock_timestamp() FOR SHARE"
                    ),
                    values,
                ).one_or_none()
                receipt = connection.execute(
                    text(
                        "SELECT expires_at,payload_hash FROM work.draft_reviews WHERE workspace_id=:workspace AND id=:review AND record_id=:record AND revision=:revision AND actor_id=:actor AND session_id=:session AND intent='confirm_note' AND expires_at>clock_timestamp()"
                    ),
                    values,
                ).one_or_none()
                if (
                    item is None
                    or receipt is None
                    or item.revision != body.expected_revision
                    or receipt.payload_hash != item.payload_hash
                ):
                    raise work_review.Rejected(409)
                connection.execute(
                    text(
                        "INSERT INTO work.draft_audit(workspace_id,record_id,revision,actor_id,event_type) VALUES(:workspace,:record,:revision,:actor,'draft.read_prepared')"
                    ),
                    values,
                )
                expires = min(receipt.expires_at, item.retain_until)
        if work_review._clock(authority) >= expires:
            raise work_review.Rejected(409)
        values["expires"] = expires
        # No business mutation here. Worker verifies both COMMITTED identity events.
        row = db.execute(
            text(
                "INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) SELECT :workspace,:record,:review,:revision,:actor,:session,:nonce,:expires WHERE :expires>clock_timestamp() ON CONFLICT DO NOTHING RETURNING *"
            ),
            values,
        ).one_or_none()
        if row is None:
            raise work_review.Rejected(409)
        identity.audit(
            db,
            "work.draft_confirmation_requested",
            "success",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
            metadata={
                "record_id": str(record_id),
                "revision": body.expected_revision,
                "review_preparation_id": str(body.review_preparation_id),
                "session_id": str(authority.session.id),
                "confirmation_request_id": str(row.id),
            },
        )
        return _result(row)
    except work_review.Rejected as error:
        return identity.denied(db, error.status, "work.confirmation_denied", user=user)
    except work_read.BrokerUnavailable:
        return identity.Result(503, {"detail": "Synthetic confirmation unavailable"})
