"""Synthetic manual task/history sentinel for the actual logical restore drill."""

import sys
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app import identity, manual_tasks as tasks
from app.config import settings
from app.db import SessionLocal
from app.models import ManualTask, ManualTaskRevision, User

assert settings.env == "test" and settings.postgres_db in {"butler_test", "butler_test_restore"}
assert settings.postgres_user == "postgres"
phase = sys.argv[1]
assert phase in {"seed", "check"}
with SessionLocal.begin() as db:
    owner = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
    assert owner and owner.slug == "synthetic-queue-restore"
    for name in ("completed", "forgotten"):
        identifier = uuid5(NAMESPACE_URL, "butler-synthetic-manual-task-restore-" + name)
        if phase == "seed":
            now = identity.now_utc()
            row = ManualTask(
                id=identifier,
                owner_id=owner.id,
                scope_key="household_shared",
                state="active",
                status="open",
                revision=1,
                title="Synthetic task restore",
                details="Synthetic task restore details",
                source_reference="Synthetic restore source",
                assignee_id=owner.id,
                due_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            tasks.snapshot(db, owner, row, "created")
            tasks.audit(db, owner, row, "created")
            db.flush()
            row.revision = 2
            row.status = "done"
            row.updated_at = identity.now_utc()
            row.completed_at = row.updated_at
            db.flush()
            tasks.snapshot(db, owner, row, "completed")
            tasks.audit(db, owner, row, "completed", 1)
            db.flush()
            if name == "forgotten":
                row.state = "forgotten"
                row.revision = 3
                row.updated_at = identity.now_utc()
                for key in (
                    "title",
                    "details",
                    "source_reference",
                    "status",
                    "assignee_id",
                    "due_at",
                    "completed_at",
                    "cancelled_at",
                ):
                    setattr(row, key, None)
                db.flush()
                db.execute(
                    update(ManualTaskRevision)
                    .where(ManualTaskRevision.task_id == identifier)
                    .values(snapshot=None)
                )
                tasks.snapshot(db, owner, row, "forgotten")
                tasks.audit(db, owner, row, "forgotten", 2)
        else:
            row = db.get(ManualTask, identifier)
            revisions = list(
                db.scalars(
                    select(ManualTaskRevision)
                    .where(ManualTaskRevision.task_id == identifier)
                    .order_by(ManualTaskRevision.revision)
                )
            )
            assert row.owner_id == owner.id and row.scope_key == "household_shared"
            if name == "completed":
                assert (
                    row.status == "done"
                    and row.revision == 2
                    and row.assignee_id == owner.id
                    and row.due_at
                )
                assert (
                    row.details == "Synthetic task restore details"
                    and row.source_reference == "Synthetic restore source"
                )
                assert [r.operation for r in revisions] == ["created", "completed"]
                assert revisions[0].snapshot["status"] == "open" and revisions[1].snapshot[
                    "completed_at"
                ] == tasks.stamp(row.completed_at)
            else:
                assert row.state == "forgotten" and row.revision == 3
                assert all(
                    getattr(row, key) is None
                    for key in (
                        "title",
                        "details",
                        "source_reference",
                        "status",
                        "due_at",
                        "assignee_id",
                        "completed_at",
                        "cancelled_at",
                    )
                )
                assert [r.snapshot for r in revisions] == [None, None, None]
                assert revisions[-1].operation == "forgotten"
if phase == "check":
    for statement in (
        "UPDATE manual_task_revisions SET snapshot='{}' WHERE snapshot IS NULL",
        "DELETE FROM manual_task_revisions",
        "TRUNCATE manual_tasks CASCADE",
    ):
        with SessionLocal.begin() as db:
            try:
                db.execute(text(statement))
            except DBAPIError:
                pass
            else:
                raise AssertionError("Restored task guard accepted mutation")
print("Synthetic manual task status, provenance, history, forgetting and restored guards verified")
