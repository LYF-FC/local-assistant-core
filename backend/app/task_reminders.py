"""Creator-private in-app reminders. No copied task text or external dispatch."""

from datetime import UTC, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, field_validator
from sqlalchemy import select

from app import identity
from app import manual_tasks as tasks
from app.config import settings
from app.models import AuditEvent, ManualTask, ReminderPreferences, TaskReminder, TaskReminderEvent


class TaskRequest(tasks.Scoped):
    task_id: UUID


class Schedule(TaskRequest):
    expected_task_revision: int = Field(strict=True, ge=1)
    expected_revision: int | None = Field(default=None, strict=True, ge=1)
    scheduled_at: AwareDatetime


class Action(TaskRequest):
    expected_revision: int = Field(strict=True, ge=1)
    action: Literal["acknowledge", "cancel"]


class History(TaskRequest):
    after: int = Field(default=0, strict=True, ge=0)


class Query(tasks.Scoped):
    state: Literal["all", "scheduled", "delivered", "acknowledged", "cancelled"] = "delivered"
    after: UUID | None = None


class Export(Query):
    acknowledge_copy_limits: bool = Field(strict=True)


class Policy(tasks.Scoped):
    expected_revision: int = Field(strict=True, ge=0)
    enabled: bool = Field(strict=True)
    timezone: str = Field(min_length=1, max_length=64)
    quiet_start: int = Field(strict=True, ge=0, le=1439)
    quiet_end: int = Field(strict=True, ge=0, le=1439)
    daily_limit: int = Field(strict=True, ge=1, le=20)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("An available IANA timezone is required") from None
        return value


def policy_document(row=None):
    return {
        "schema_version": 1,
        "revision": row.revision if row else 0,
        "enabled": row.enabled if row else True,
        "timezone": row.timezone if row else "Europe/Paris",
        "quiet_start": row.quiet_start if row else 1320,
        "quiet_end": row.quiet_end if row else 480,
        "daily_limit": row.daily_limit if row else 5,
    }


def document(row):
    return {
        "id": str(row.id),
        "task_id": str(row.task_id),
        "owner_id": str(row.owner_id),
        "scope": row.scope_key,
        "state": row.state,
        "revision": row.revision,
        "cycle": row.cycle,
        "policy_revision": row.policy_revision,
        "task_revision": row.task_revision,
        "scheduled_at": tasks.stamp(row.scheduled_at),
        "next_attempt_at": tasks.stamp(row.next_attempt_at),
        "delivered_at": tasks.stamp(row.delivered_at),
        "reason": row.reason,
        "created_at": tasks.stamp(row.created_at),
        "updated_at": tasks.stamp(row.updated_at),
    }


def record_event(db, user, row, operation, *, system=False, before=None, routine_schedule=False):
    if routine_schedule and (not system or operation != "scheduled"):
        raise ValueError("Routine authorization applies only to initial scheduling")
    db.flush()
    db.add(
        TaskReminderEvent(
            reminder_id=row.id,
            owner_id=row.owner_id,
            revision=row.revision,
            actor_id=user.id if routine_schedule or not system else None,
            operation=operation,
            recorded_at=row.updated_at,
            snapshot=document(row),
        )
    )
    db.add(
        AuditEvent(
            environment=settings.env,
            initiator_type="system" if system else "human",
            initiator_id="routine_worker"
            if routine_schedule
            else "reminder_worker"
            if system
            else str(user.id),
            scope_key=row.scope_key,
            event_type="reminders." + operation,
            entity_type="task_reminder",
            entity_id=str(row.id),
            result_status="success",
            before_json={"revision": before} if before else None,
            after_json={
                "revision": row.revision,
                "state": row.state,
                "cycle": row.cycle,
                "reason": row.reason,
            },
            metadata_json={},
            source_context={},
        )
    )
    db.flush()


def change(db, user, row, operation, *, system=False, recorded_now=None, **values):
    before = row.revision
    for name, value in values.items():
        setattr(row, name, value)
    row.revision += 1
    row.updated_at = recorded_now or identity.now_utc()
    record_event(db, user, row, operation, system=system, before=before)


def cancel_for_task(db, user, task):
    row = db.scalar(
        select(TaskReminder)
        .where(TaskReminder.task_id == task.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row and row.state in {"scheduled", "delivered"}:
        change(
            db,
            user,
            row,
            "cancelled",
            state="cancelled",
            next_attempt_at=None,
            reason="task_forgotten" if task.state == "forgotten" else "task_closed",
            task_revision=task.revision,
        )


def task_access(db, token, csrf, body):
    current = tasks.authority(db, token, csrf, body.scope)
    if isinstance(current, identity.Result):
        return current
    user, session = current
    task = db.scalar(
        select(ManualTask)
        .where(
            ManualTask.id == body.task_id,
            ManualTask.owner_id == user.id,
            ManualTask.scope_key == body.scope,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "reminders.session_denied", user=user)
    if task is None:
        return identity.denied(db, 404, "reminders.not_found", user=user)
    session.last_seen_at = identity.now_utc()
    row = db.scalar(
        select(TaskReminder)
        .where(TaskReminder.task_id == task.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return user, session, task, row


def operate(db, token, csrf, body, operation):
    current = task_access(db, token, csrf, body)
    if isinstance(current, identity.Result):
        return current
    user, _, task, row = current
    if operation == "read":
        identity.audit(
            db,
            "reminders.read",
            "success",
            user=user,
            scope=body.scope,
            entity_type="manual_task",
            entity=str(task.id),
        )
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "task_id": str(task.id),
                "reminder": document(row) if row else None,
            },
        )
    if operation == "history":
        rows = (
            list(
                db.scalars(
                    select(TaskReminderEvent)
                    .where(
                        TaskReminderEvent.reminder_id == row.id,
                        TaskReminderEvent.revision > body.after,
                    )
                    .order_by(TaskReminderEvent.revision)
                    .limit(26)
                )
            )
            if row
            else []
        )
        identity.audit(
            db,
            "reminders.history",
            "success",
            user=user,
            scope=body.scope,
            entity_type="manual_task",
            entity=str(task.id),
        )
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "task_id": str(task.id),
                "items": [
                    {
                        "revision": r.revision,
                        "actor_id": str(r.actor_id) if r.actor_id else None,
                        "operation": r.operation,
                        "recorded_at": tasks.stamp(r.recorded_at),
                        "snapshot": r.snapshot,
                    }
                    for r in rows[:25]
                ],
                "next_cursor": rows[24].revision if len(rows) > 25 else None,
            },
        )
    if (row.revision if row else None) != body.expected_revision:
        return identity.denied(db, 409, "reminders.revision_conflict", user=user, scope=body.scope)
    if operation == "schedule":
        now = identity.now_utc()
        when = body.scheduled_at.astimezone(UTC)
        if task.state != "active" or task.status != "open":
            return identity.denied(db, 409, "reminders.task_closed", user=user, scope=body.scope)
        if task.revision != body.expected_task_revision:
            return identity.denied(db, 409, "reminders.task_changed", user=user, scope=body.scope)
        if not now < when <= now + timedelta(days=365):
            return identity.denied(db, 422, "reminders.invalid_time", user=user, scope=body.scope)
        policy = db.get(ReminderPreferences, user.id)
        version = policy.revision if policy else 0
        if row:
            change(
                db,
                user,
                row,
                "rescheduled",
                state="scheduled",
                scheduled_at=when,
                next_attempt_at=when,
                delivered_at=None,
                reason=None,
                cycle=row.cycle + 1,
                policy_revision=version,
                task_revision=task.revision,
            )
        else:
            row = TaskReminder(
                task_id=task.id,
                owner_id=user.id,
                scope_key=task.scope_key,
                revision=1,
                cycle=1,
                policy_revision=version,
                task_revision=task.revision,
                state="scheduled",
                scheduled_at=when,
                next_attempt_at=when,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            record_event(db, user, row, "scheduled")
    elif row is None:
        return identity.denied(db, 404, "reminders.not_found", user=user)
    elif body.action == "acknowledge":
        if row.state != "delivered" or task.state != "active" or task.status != "open":
            return identity.denied(db, 409, "reminders.not_delivered", user=user, scope=body.scope)
        change(
            db,
            user,
            row,
            "acknowledged",
            state="acknowledged",
            reason=None,
            task_revision=task.revision,
        )
    else:
        if row.state not in {"scheduled", "delivered"}:
            return identity.denied(db, 409, "reminders.not_active", user=user, scope=body.scope)
        change(
            db,
            user,
            row,
            "cancelled",
            state="cancelled",
            next_attempt_at=None,
            reason="cancelled_by_owner",
            task_revision=task.revision,
        )
    return identity.Result(200, document(row))


def preferences(db, token, csrf, body, write=False):
    current = tasks.authority(db, token, csrf, body.scope, exclusive_user=write)
    if isinstance(current, identity.Result):
        return current
    user, session = current
    row = db.scalar(
        select(ReminderPreferences)
        .where(ReminderPreferences.owner_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "reminders.session_denied", user=user)
    session.last_seen_at = identity.now_utc()
    before = policy_document(row)
    if write:
        if before["revision"] != body.expected_revision:
            return identity.denied(db, 409, "reminders.policy_changed", user=user)
        values = body.model_dump(exclude={"scope", "expected_revision"})
        if all(before[k] == v for k, v in values.items()):
            return identity.denied(db, 409, "reminders.no_change", user=user)
        now = identity.now_utc()
        if row:
            for key, value in values.items():
                setattr(row, key, value)
            row.revision += 1
            row.updated_at = now
        else:
            row = ReminderPreferences(
                owner_id=user.id, revision=1, created_at=now, updated_at=now, **values
            )
            db.add(row)
        db.flush()
    result = policy_document(row)
    identity.audit(
        db,
        "reminders.preferences_" + ("changed" if write else "read"),
        "success",
        user=user,
        scope=body.scope,
        entity_type="reminder_preferences",
        entity=str(user.id),
        before=before if write else None,
        after=result if write else None,
    )
    return identity.Result(200, result)


def listing(db, token, csrf, body, export=False):
    current = tasks.authority(db, token, csrf, body.scope)
    if isinstance(current, identity.Result):
        return current
    user, session = current
    if export and not body.acknowledge_copy_limits:
        return identity.denied(db, 422, "reminders.copy_ack_required", user=user)
    # Lock tasks before reminder rows, matching mutations/worker; user lock pins visibility.
    query = select(TaskReminder.id, TaskReminder.task_id).where(
        TaskReminder.owner_id == user.id, TaskReminder.scope_key == body.scope
    )
    if body.state != "all":
        query = query.where(TaskReminder.state == body.state)
    if body.after:
        query = query.where(TaskReminder.id > body.after)
    candidates = list(db.execute(query.order_by(TaskReminder.id).limit(26)))
    ids = [r.task_id for r in candidates[:25]]
    locked = (
        list(
            db.scalars(
                select(ManualTask)
                .where(
                    ManualTask.id.in_(ids),
                    ManualTask.owner_id == user.id,
                    ManualTask.scope_key == body.scope,
                )
                .order_by(ManualTask.id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        )
        if ids
        else []
    )
    by_id = {t.id: t for t in locked}
    rows = (
        list(
            db.scalars(
                select(TaskReminder)
                .where(TaskReminder.task_id.in_(list(by_id)))
                .order_by(TaskReminder.id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        )
        if by_id
        else []
    )
    rows = [r for r in rows if body.state == "all" or r.state == body.state]
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "reminders.session_denied", user=user)
    session.last_seen_at = identity.now_utc()
    items = []
    for row in rows[:25]:
        task = by_id[row.task_id]
        items.append({"reminder": document(row), "task": tasks.document(task)})
    identity.audit(
        db,
        "reminders.export" if export else "reminders.query",
        "success",
        user=user,
        scope=body.scope,
        entity_type="task_reminder",
        metadata={"returned": len(items)},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "checked_at": tasks.stamp(identity.now_utc()),
            "owner_id": str(user.id),
            "scope": body.scope,
            "state": body.state,
            "after": str(body.after) if body.after else None,
            "items": items,
            "next_cursor": str(candidates[24].id) if len(candidates) > 25 else None,
            "managed_copy": False if export else None,
            "preferences": policy_document(db.get(ReminderPreferences, user.id)),
        },
    )
