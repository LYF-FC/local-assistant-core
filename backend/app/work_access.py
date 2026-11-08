"""Work identity metadata only. This module cannot accept or retrieve work content."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import identity, work_authority
from app.models import User, WorkGrant, WorkWorkspace

CAPABILITY = "work_private"
PENDING_GATES = (
    "dedicated_content_storage_and_roles",
    "workspace_retrieval_context_and_caches",
    "workspace_jobs_and_credentials",
    "work_content_audit_and_observability",
    "export_keys_retention_and_isolated_recovery",
)


def assigned(user: User):
    return (
        select(WorkWorkspace)
        .join(WorkGrant, WorkGrant.workspace_id == WorkWorkspace.id)
        .where(
            WorkGrant.user_id == user.id,
            WorkGrant.capability == CAPABILITY,
            WorkWorkspace.is_active.is_(True),
        )
    )


def inspect_work(
    db: Session,
    token: str | None,
    workspace_id: UUID | None = None,
    *,
    after: UUID | None = None,
    limit: int = 25,
) -> identity.Result:
    current = work_authority.resolve(db, token)
    if isinstance(current, identity.Result):
        return current
    user, session = current.user, current.session
    statement = assigned(user)
    if workspace_id is not None:
        workspace = db.scalar(statement.where(WorkWorkspace.id == workspace_id))
        if workspace is None:
            # Missing/unassigned/disabled share one response and no requested-ID audit.
            return identity.denied(db, 404, "work.access_denied", user=user)
        payload = {
            "schema_version": 1,
            "workspace": {"id": str(workspace.id), "slug": workspace.slug},
            "capability": CAPABILITY,
            "mode": "access_foundation_only",
            "ingestion_allowed": False,
            "model_invoked": False,
            "execution_allowed": False,
            "pending_gates": list(PENDING_GATES),
        }
        entity = str(workspace.id)
    else:
        if not 1 <= limit <= 25:
            return identity.Result(422, {"detail": "Invalid request"})
        if after is not None:
            statement = statement.where(WorkWorkspace.id > after)
        rows = list(db.scalars(statement.order_by(WorkWorkspace.id).limit(limit + 1)))
        items = rows[:limit]
        payload = {
            "schema_version": 1,
            "capability": CAPABILITY,
            "items": [{"id": str(row.id), "slug": row.slug} for row in items],
            "next_cursor": str(items[-1].id) if len(rows) > limit else None,
        }
        entity = None
    checked_at = current.checked_now()
    if checked_at is None:
        return identity.denied(db, 401, "work.access_session_denied", user=user)
    payload["authority_mode"] = "transaction_snapshot"
    payload["checked_at"] = checked_at.isoformat()
    session.last_seen_at = checked_at
    identity.audit(
        db,
        "work.access_status" if workspace_id is not None else "work.access_list",
        "success",
        user=user,
        entity=entity,
        entity_type="work_access_registry",
        metadata={"authority_mode": "transaction_snapshot"},
    )
    return identity.Result(200, payload)
