"""Trusted local development/test administration of synthetic work identity metadata."""

import argparse
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import User, WorkGrant, WorkWorkspace
from app.work_access import CAPABILITY
from app.work_authority import registry_barrier


def administer(db: Session, action: str, slug: str, user_slug: str | None = None) -> None:
    if not re.fullmatch(r"synthetic-[a-z0-9][a-z0-9_-]{0,53}", slug):
        raise ValueError("Use a synthetic- prefixed workspace slug (maximum 64 characters)")
    registry_barrier(db, exclusive=True)
    workspace = db.scalar(select(WorkWorkspace).where(WorkWorkspace.slug == slug).with_for_update())
    if action == "create-workspace":
        if workspace is not None:
            raise ValueError("Workspace already exists")
        workspace = WorkWorkspace(slug=slug)
        db.add(workspace)
        db.flush()
    else:
        if workspace is None:
            raise ValueError("Workspace not found")
        if action in {"grant", "revoke"}:
            user = db.scalar(select(User).where(User.slug == user_slug).with_for_update())
            if user is None or (action == "grant" and not user.is_active):
                raise ValueError("Active user required for a grant")
            grant = db.get(WorkGrant, (user.id, workspace.id))
            if action == "grant" and grant is None:
                db.add(WorkGrant(user_id=user.id, workspace_id=workspace.id, capability=CAPABILITY))
            elif action == "revoke":
                db.execute(
                    delete(WorkGrant).where(
                        WorkGrant.user_id == user.id, WorkGrant.workspace_id == workspace.id
                    )
                )
        elif action in {"enable", "disable"}:
            workspace.is_active = action == "enable"
        else:
            raise ValueError("Unknown work administration action")
    db.flush()
    # Identity administration metadata only; no workspace label or employer content.
    from app.models import AuditEvent

    db.add(
        AuditEvent(
            environment=settings.env,
            initiator_type="local_admin",
            initiator_id="trusted_host_operator",
            scope_key="technical_admin",
            event_type="admin.work_" + action.replace("-", "_"),
            entity_type="work_access_registry",
            entity_id=str(workspace.id),
            result_status="success",
            source_context={},
            metadata_json={"user_id": str(user.id)} if action in {"grant", "revoke"} else {},
        )
    )
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument(
        "action", choices=["create-workspace", "grant", "revoke", "enable", "disable"]
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--slug")
    args = parser.parse_args()
    if settings.env != args.environment:
        parser.error("Environment does not match the configured development/test target")
    if args.action in {"grant", "revoke"} and not args.slug:
        parser.error("--slug is required for grant/revoke")
    with SessionLocal.begin() as db:
        administer(db, args.action, args.workspace, args.slug)
    print("Synthetic work access administration committed; no content imported")


if __name__ == "__main__":
    main()
