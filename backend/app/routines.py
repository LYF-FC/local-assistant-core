"""Human-authorized finite routines and aggregate lifecycle. No provider/model I/O."""

from datetime import timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from app import identity
from app import manual_tasks as tasks
from app import routine_contracts as contract
from app import task_reminders as reminders
from app.config import settings
from app.models import (
    AuditEvent,
    ManualTask,
    ManualTaskRevision,
    Routine,
    RoutineOccurrence,
    RoutineRevision,
    TaskReminder,
)


def visible(user, scope):
    return Routine.scope_key == scope, or_(
        Routine.owner_id == user.id, Routine.scope_key == "household_shared"
    )


def document(row):
    return {
        "id": str(row.id),
        "owner_id": str(row.owner_id),
        "scope": row.scope_key,
        "state": row.state,
        "revision": row.revision,
        "changes": row.changes,
        "position": row.position,
        "next_at": tasks.stamp(row.next_at),
        "data": row.data,
        "created_at": tasks.stamp(row.created_at),
        "updated_at": tasks.stamp(row.updated_at),
    }


def presented(row, user):
    return {**document(row), "can_edit": row.owner_id == user.id}


def record(db, user, row, operation, *, system=False, metadata=None):
    db.flush()
    db.add(
        RoutineRevision(
            routine_id=row.id,
            revision=row.revision,
            actor_id=None if system else user.id,
            snapshot=document(row) if row.state != "forgotten" else None,
            created_at=row.updated_at,
        )
    )
    audit(db, user, row, operation, system=system, metadata=metadata)


def audit(db, user, row, operation, *, system=False, metadata=None):
    db.add(
        AuditEvent(
            environment=settings.env,
            initiator_type="system" if system else "human",
            initiator_id="routine_worker" if system else str(user.id),
            scope_key=row.scope_key,
            entity_type="routine",
            entity_id=str(row.id),
            event_type="routines." + operation,
            result_status="success",
            after_json={"revision": row.revision, "state": row.state, "position": row.position},
            metadata_json=metadata or {},
            source_context={},
        )
    )
    db.flush()


def preview(db, token, csrf, body):
    current = tasks.authority(db, token, csrf, body.scope, event_prefix="routines")
    if isinstance(current, identity.Result):
        return current
    user, session = current
    now = identity.now_utc()
    try:
        data = contract.resolve(body, now)
    except ValueError:
        return identity.denied(db, 422, "routines.invalid_plan", user=user)
    identity.audit(
        db,
        "routines.preview",
        "success",
        user=user,
        scope=body.scope,
        metadata={"slots": len(data["plan"])},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "scope": body.scope,
            "data": data,
            "checked_at": tasks.stamp(now),
            "valid_until": tasks.stamp(
                min(now + timedelta(seconds=60), identity.aware(session.expires_at))
            ),
        },
    )


def create(db, token, csrf, body):
    current = tasks.authority(
        db, token, csrf, body.scope, exclusive_user=True, event_prefix="routines"
    )
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    if (
        db.scalar(select(func.count()).select_from(Routine).where(Routine.owner_id == user.id))
        >= 10
    ):
        return identity.denied(db, 429, "routines.identity_limit", user=user)
    now = identity.now_utc()
    try:
        data = contract.resolve(body, now)
    except ValueError:
        return identity.denied(db, 422, "routines.invalid_plan", user=user)
    row = Routine(
        owner_id=user.id,
        scope_key=body.scope,
        state="active",
        revision=1,
        changes=0,
        position=0,
        next_at=contract.next_at(data),
        data=data,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    record(db, user, row, "created")
    return identity.Result(201, presented(row, user))


def linked_tasks(db, row, *, exclusive):
    return list(
        db.scalars(
            select(ManualTask)
            .join(RoutineOccurrence, RoutineOccurrence.task_id == ManualTask.id)
            .where(
                RoutineOccurrence.routine_id == row.id,
                ManualTask.owner_id == row.owner_id,
                ManualTask.scope_key == row.scope_key,
            )
            .order_by(ManualTask.id)
            .with_for_update(read=not exclusive, of=ManualTask)
            .execution_options(populate_existing=True)
        )
    )


def cancel_linked(db, user, linked):
    for task in linked:
        reminder = db.scalar(
            select(TaskReminder)
            .where(TaskReminder.task_id == task.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if reminder and reminder.state in {"scheduled", "delivered"}:
            reminders.change(
                db,
                user,
                reminder,
                "cancelled",
                state="cancelled",
                next_attempt_at=None,
                reason="cancelled_by_owner",
                task_revision=task.revision,
            )


def forget_task(db, user, task):
    if task.state == "forgotten":
        return
    before = task.revision
    task.state = "forgotten"
    for field in (
        "title",
        "details",
        "source_reference",
        "status",
        "due_at",
        "assignee_id",
        "completed_at",
        "cancelled_at",
    ):
        setattr(task, field, None)
    task.revision += 1
    task.updated_at = identity.now_utc()
    db.flush()
    db.execute(
        update(ManualTaskRevision)
        .where(ManualTaskRevision.task_id == task.id)
        .values(snapshot=None)
    )
    reminders.cancel_for_task(db, user, task)
    tasks.snapshot(db, user, task, "forgotten")
    tasks.audit(db, user, task, "forgotten", before)


def occurrence_page(db, row, user, after=None):
    query = select(RoutineOccurrence).where(RoutineOccurrence.routine_id == row.id)
    if after:
        query = query.where(RoutineOccurrence.local_date > after.isoformat())
    rows = list(db.scalars(query.order_by(RoutineOccurrence.local_date).limit(26)))
    ids = [r.task_id for r in rows[:25] if r.task_id]
    current = {
        t.id: t
        for t in db.scalars(
            select(ManualTask)
            .where(
                ManualTask.id.in_(ids),
                ManualTask.owner_id == user.id,
                ManualTask.scope_key == row.scope_key,
            )
            .order_by(ManualTask.id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    }
    return {
        "items": [
            {
                "id": str(r.id),
                "local_date": r.local_date,
                "routine_revision": r.routine_revision,
                "due_at": tasks.stamp(r.due_at),
                "outcome": r.outcome,
                "task_id": str(r.task_id) if r.task_id else None,
                "task": tasks.presented(current[r.task_id], user) if r.task_id in current else None,
                "recorded_at": tasks.stamp(r.recorded_at),
            }
            for r in rows[:25]
        ],
        "next_date": rows[24].local_date if len(rows) > 25 else None,
    }


def operate(db, token, csrf, identifier, body, operation):
    unsafe = operation in {"correct", "action"}
    current = tasks.authority(
        db, token, csrf, body.scope, exclusive_user=unsafe, event_prefix="routines"
    )
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    row = db.scalar(
        select(Routine)
        .where(Routine.id == identifier, *visible(user, body.scope))
        .with_for_update(read=not unsafe)
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "routines.session_denied", user=user)
    if row is None:
        return identity.denied(db, 404, "routines.not_found", user=user)
    if operation != "read" and row.owner_id != user.id:
        return identity.denied(db, 403, "routines.owner_denied", user=user)
    if operation in {"history", "export", "occurrences"}:
        payload = {
            "schema_version": 1,
            "routine_id": str(row.id),
            "scope": row.scope_key,
            "current_revision": row.revision,
            "state": row.state,
        }
        if operation != "occurrences":
            rows = list(
                db.scalars(
                    select(RoutineRevision)
                    .where(
                        RoutineRevision.routine_id == row.id, RoutineRevision.revision > body.after
                    )
                    .order_by(RoutineRevision.revision)
                    .limit(6)
                )
            )
            payload.update(
                items=[
                    {
                        "revision": r.revision,
                        "actor_id": str(r.actor_id) if r.actor_id else None,
                        "created_at": tasks.stamp(r.created_at),
                        "snapshot": r.snapshot,
                    }
                    for r in rows[:5]
                ],
                next_cursor=rows[4].revision if len(rows) > 5 else None,
                managed_copy=False if operation == "export" else None,
            )
        if operation in {"occurrences", "export"}:
            payload["occurrences"] = occurrence_page(db, row, user, body.after_date)
        if identity.resolve(db, token, refresh_session=True) is None:
            return identity.denied(db, 401, "routines.session_denied", user=user)
        audit(db, user, row, operation)
        return identity.Result(200, payload)
    if row.state == "forgotten":
        audit(db, user, row, "forgotten_read")
        return identity.Result(410, presented(row, user))
    if not unsafe:
        audit(db, user, row, "read")
        return identity.Result(200, presented(row, user))
    if row.revision != body.expected_revision:
        return identity.denied(db, 409, "routines.revision_conflict", user=user)
    action = "correct" if operation == "correct" else body.action
    if (row.changes >= 100 or row.revision >= 997) and action not in {"pause", "forget"}:
        return identity.denied(db, 429, "routines.change_limit", user=user)
    data = None
    if action in {"correct", "resume"}:
        if action == "resume" and row.state not in {"paused", "blocked"}:
            return identity.denied(db, 409, "routines.invalid_transition", user=user)
        if (
            db.scalar(
                select(func.count())
                .select_from(RoutineOccurrence)
                .where(RoutineOccurrence.routine_id == row.id)
            )
            >= 400
        ):
            return identity.denied(db, 429, "routines.occurrence_limit", user=user)
        try:
            data = contract.resolve(
                body if action == "correct" else contract.Values.model_validate(row.data["values"]),
                identity.now_utc(),
                resumed=action == "resume",
            )
        except ValueError:
            return identity.denied(db, 422, "routines.invalid_plan", user=user)
    if action == "pause" and row.state != "active":
        return identity.denied(db, 409, "routines.invalid_transition", user=user)
    linked = linked_tasks(db, row, exclusive=True)
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "routines.session_denied", user=user)
    if action != "forget":
        cancel_linked(db, user, linked)
    if action == "forget":
        for task in linked:
            forget_task(db, user, task)
        row.state, row.data, row.next_at = "forgotten", None, None
    elif action == "pause":
        row.state, row.next_at = "paused", None
    else:
        row.data, row.position, row.next_at, row.state = data, 0, contract.next_at(data), "active"
    row.changes = min(102, row.changes + 1)
    row.revision += 1
    row.updated_at = identity.now_utc()
    db.flush()
    if row.state == "forgotten":
        db.execute(
            update(RoutineRevision)
            .where(RoutineRevision.routine_id == row.id)
            .values(snapshot=None)
        )
    record(db, user, row, action)
    if identity.resolve(db, token, refresh_session=True) is None:
        raise SQLAlchemyError("Routine authority expired; aggregate rolled back")
    return identity.Result(200, presented(row, user))


def listing(db, token, csrf, body):
    current = tasks.authority(db, token, csrf, body.scope, event_prefix="routines")
    if isinstance(current, identity.Result):
        return current
    user, _ = current
    query = select(Routine).where(*visible(user, body.scope), Routine.state != "forgotten")
    if body.after:
        query = query.where(Routine.id > body.after)
    rows = list(
        db.scalars(
            query.order_by(Routine.id)
            .limit(26)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "routines.session_denied", user=user)
    identity.audit(
        db,
        "routines.query",
        "success",
        user=user,
        scope=body.scope,
        metadata={"returned": min(25, len(rows))},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "scope": body.scope,
            "items": [presented(r, user) for r in rows[:25]],
            "next_cursor": str(rows[24].id) if len(rows) > 25 else None,
        },
    )
