"""Finite routine/generated-task lineage sentinel for isolated logical recovery."""

import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, update

from app import identity, routine_worker, routines
from app import routine_contracts as contract
from app.config import settings
from app.db import SessionLocal
from app.manage import set_scope
from app.models import (
    ManualTask,
    ManualTaskRevision,
    Routine,
    RoutineOccurrence,
    RoutineRevision,
    User,
)

assert settings.env == "test" and settings.postgres_db in {"butler_test", "butler_test_restore"}
assert settings.postgres_user == "postgres"
phase = sys.argv[1]
assert phase in {"seed", "check"}
with SessionLocal.begin() as db:
    owner = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
    assert owner and owner.slug == "synthetic-queue-restore"
    if phase == "seed":
        set_scope(db, owner, "household_shared", True)
    for name in ("paused", "forgotten"):
        identifier = uuid5(NAMESPACE_URL, "butler-synthetic-routine-restore-" + name)
        if phase == "seed":
            now = identity.now_utc()
            day = (now - timedelta(days=2)).date()
            before = datetime.combine(day, datetime.min.time(), UTC)
            values = contract.Values(
                scope="household_shared",
                title="Synthetic restore routine",
                details="Synthetic routine content",
                source_reference="Synthetic restore instructions",
                timezone="UTC",
                local_time="09:00",
                frequency="daily",
                interval=1,
                weekdays=[],
                starts_on=day,
                ends_on=day + timedelta(days=4),
                remind=True,
            )
            data = contract.resolve(values, before)
            row = Routine(
                id=identifier,
                owner_id=owner.id,
                scope_key=values.scope,
                state="active",
                revision=1,
                changes=0,
                position=0,
                next_at=contract.next_at(data),
                data=data,
                created_at=before,
                updated_at=before,
            )
            db.add(row)
            routines.record(db, owner, row, "created")
            assert (
                routine_worker.process(
                    db, SimpleNamespace(id=row.id, owner_id=owner.id, scope_key=row.scope_key)
                )
                == "generated"
            )
            linked = routines.linked_tasks(db, row, exclusive=True)
            assert len(linked) == 1
            if name == "forgotten":
                for task in linked:
                    routines.forget_task(db, owner, task)
                row.state, row.data, row.next_at = "forgotten", None, None
            else:
                routines.cancel_linked(db, owner, linked)
                row.state, row.next_at = "paused", None
            row.revision += 1
            row.changes += 1
            row.updated_at = identity.now_utc()
            db.flush()
            if name == "forgotten":
                db.execute(
                    update(RoutineRevision)
                    .where(RoutineRevision.routine_id == row.id)
                    .values(snapshot=None)
                )
            routines.record(db, owner, row, "forget" if name == "forgotten" else "pause")
        else:
            row = db.get(Routine, identifier)
            receipts = list(
                db.scalars(
                    select(RoutineOccurrence).where(RoutineOccurrence.routine_id == identifier)
                )
            )
            made = [r for r in receipts if r.outcome == "created"]
            assert (
                row.owner_id == owner.id
                and row.scope_key == "household_shared"
                and row.state == name
                and row.next_at is None
            )
            assert len(made) == 1 and made[0].task_id == uuid5(row.id, made[0].local_date)
            task = db.get(ManualTask, made[0].task_id)
            history = list(
                db.scalars(select(RoutineRevision).where(RoutineRevision.routine_id == identifier))
            )
            assert len(history) == 3 and made[0].routine_revision == 1
            if name == "paused":
                assert (
                    row.data["values"]["timezone"] == "UTC"
                    and task.status == "open"
                    and history[-1].snapshot["state"] == "paused"
                )
            else:
                assert (
                    row.data is None
                    and task.state == "forgotten"
                    and all(r.snapshot is None for r in history)
                )
                assert all(
                    r.snapshot is None
                    for r in db.scalars(
                        select(ManualTaskRevision).where(ManualTaskRevision.task_id == task.id)
                    )
                )
print(
    "Synthetic routine plan/receipt/generated-task lineage and aggregate forgetting recovery verified"
)
