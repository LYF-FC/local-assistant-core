"""Current-session synthetic preview/review preparation; no lifecycle writer."""

import hmac
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import identity, work_access, work_authority, work_lifecycle, work_read
from app.config import settings
from app.models import WorkWorkspace


class Preview(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Review(Preview):
    expected_revision: int = Field(strict=True, ge=1, le=100)
    reviewed_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_id: UUID
    decision: Literal["approve"]


class Rejected(Exception):
    def __init__(self, status: int):
        self.status = status


def get_review_engines() -> work_read.EngineSource | None:
    return work_read.get_work_engines() if settings.work_draft_review_enabled else None


def _clock(authority):
    now = authority.checked_now()
    if now is None:
        raise Rejected(401)
    return now


def prepare(
    db: Session,
    token: str | None,
    csrf: str | None,
    workspace_id: UUID,
    record_id: UUID,
    engines: work_read.EngineSource | None,
    review: Review | None = None,
) -> identity.Result:
    authority = work_authority.resolve(db, token)
    if isinstance(authority, identity.Result):
        return authority
    user = authority.user
    if (
        not csrf
        or len(csrf) > 128
        or not hmac.compare_digest(authority.session.csrf_hash, identity.digest(csrf))
    ):
        return identity.denied(db, 403, "work.draft_csrf_denied", user=user)
    if db.scalar(work_access.assigned(user).where(WorkWorkspace.id == workspace_id)) is None:
        return identity.denied(db, 404, "work.draft_denied", user=user)
    try:
        if engines is None:
            raise work_read.BrokerUnavailable("Synthetic review unavailable")
        with engines.lease(workspace_id) as engine:
            if engine is None:
                raise work_read.BrokerUnavailable("Synthetic review unavailable")
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
                _clock(authority)
                row = connection.execute(
                    text(
                        "SELECT snapshot,encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') AS payload_hash FROM work.drafts WHERE workspace_id=:workspace AND id=:record AND state='draft' AND retain_until>clock_timestamp() FOR SHARE"
                    ),
                    {"workspace": workspace_id, "record": record_id},
                ).one_or_none()
                if row is None:
                    raise Rejected(404)
                item = work_lifecycle.Record.model_validate(row.snapshot)
                _clock(authority)
                receipt = None
                replayed = False
                if review is None:
                    connection.execute(
                        text(
                            "INSERT INTO work.draft_audit(workspace_id,record_id,revision,actor_id,event_type) VALUES(:workspace,:record,:revision,:actor,'draft.read_prepared')"
                        ),
                        {
                            "workspace": workspace_id,
                            "record": record_id,
                            "revision": item.revision,
                            "actor": user.id,
                        },
                    )
                else:
                    if (
                        review.expected_revision != item.revision
                        or not hmac.compare_digest(review.reviewed_hash, row.payload_hash)
                        or not item.source_ids
                    ):
                        raise Rejected(409)
                    values = {
                        "workspace": workspace_id,
                        "record": record_id,
                        "revision": item.revision,
                        "actor": user.id,
                        "session": authority.session.id,
                        "request": review.request_id,
                        "hash": row.payload_hash,
                    }
                    receipt = connection.execute(
                        text(
                            "INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash) VALUES(:workspace,:record,:revision,:actor,:session,:request,'confirm_note',:hash) ON CONFLICT(workspace_id,actor_id,session_id,request_id) DO NOTHING RETURNING id,record_id,revision,payload_hash,expires_at"
                        ),
                        values,
                    ).one_or_none()
                    if receipt is None:
                        replayed = True
                        receipt = connection.execute(
                            text(
                                "SELECT id,record_id,revision,payload_hash,expires_at FROM work.draft_reviews WHERE workspace_id=:workspace AND actor_id=:actor AND session_id=:session AND request_id=:request AND expires_at>clock_timestamp()"
                            ),
                            values,
                        ).one_or_none()
                        if (
                            receipt is None
                            or receipt.record_id != record_id
                            or receipt.revision != item.revision
                            or receipt.payload_hash != row.payload_hash
                        ):
                            raise Rejected(409)
                if connection.scalar(text("SELECT clock_timestamp()")) >= item.retain_until:
                    raise Rejected(404)
                _clock(authority)
            # Work audit/review commits before identity; no distributed delivery claim.
        checked = _clock(authority)
        if checked >= item.retain_until:
            raise Rejected(404)
        if receipt is not None and checked >= receipt.expires_at:
            raise Rejected(409)
        authority.session.last_seen_at = checked
        metadata = {"record_id": str(record_id), "revision": item.revision}
        if receipt is not None:
            metadata["review_preparation_id"] = str(receipt.id)
            metadata["session_id"] = str(authority.session.id)
        identity.audit(
            db,
            "work.draft_review_recorded" if review else "work.draft_preview",
            "success",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
            metadata=metadata,
        )
        result = {
            "schema_version": 1,
            "workspace_id": str(workspace_id),
            "record_id": str(record_id),
            "revision": item.revision,
            "checked_at": checked.isoformat(),
            "confirmation_applied": False,
            "execution_allowed": False,
            "model_invoked": False,
            "ingestion_allowed": False,
        }
        if receipt is None:
            result.update(
                mode="synthetic_draft_preview",
                item=item.model_dump(mode="json"),
                payload_hash=row.payload_hash,
            )
        else:
            result.update(
                mode="synthetic_review_preparation",
                review_preparation_id=str(receipt.id),
                expires_at=receipt.expires_at.isoformat(),
                replayed=replayed,
            )
        return identity.Result(200, result)
    except Rejected as error:
        return identity.denied(db, error.status, "work.draft_review_denied", user=user)
    except (SQLAlchemyError, work_read.BrokerUnavailable, ValidationError):
        identity.audit(
            db,
            "work.draft_review_unavailable",
            "denied",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
        )
        return identity.Result(503, {"detail": "Synthetic review unavailable"})
