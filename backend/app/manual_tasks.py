"""Human-controlled local agenda. No dispatch, reminders, models or legacy task writes."""

import hmac
from datetime import UTC, timedelta
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select, text, update

from app import identity
from app.models import AuthSession, ManualTask, ManualTaskRevision, User

Scope = Literal["household_shared", "member_a_private", "member_b_private"]
Status = Literal["open", "done", "cancelled"]


class Scoped(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Scope


class Values(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    details: str = Field(default="", max_length=4000)
    source_reference: str = Field(default="Manually entered", min_length=1, max_length=512)
    due_at: AwareDatetime | None = None
    assignment: Literal["unknown", "me"] = "unknown"

    @field_validator("title", "source_reference")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A nonblank value is required")
        return value.strip()


class Create(Values, Scoped):
    pass


class Read(Scoped):
    pass


class Expected(Scoped):
    expected_revision: int = Field(strict=True, ge=1)


class Correct(Values, Expected):
    pass


class Transition(Expected):
    status: Status


class History(Scoped):
    after: int = Field(default=0, strict=True, ge=0)


class Query(Scoped):
    status: Literal["all", "open", "done", "cancelled"] = "open"
    due: Literal["all", "overdue", "next_seven_days", "unknown"] = "all"
    search: str = Field(default="", max_length=160)
    after: UUID | None = None


class Export(Query):
    acknowledge_copy_limits: Literal[True]

    @field_validator("acknowledge_copy_limits", mode="before")
    @classmethod
    def explicit_boolean(cls, value):
        if value is not True:
            raise ValueError("Explicit acknowledgement required")
        return value


def authority(
    db, token, csrf, scope, *, exclusive_user=False, event_prefix="tasks", scope_lock="tasks"
):
    if not token or not 40 <= len(token) <= 128:
        return identity.denied(db, 401, event_prefix + ".session_denied")
    user_id = db.scalar(
        select(AuthSession.user_id).where(AuthSession.token_hash == identity.digest(token))
    )
    if user_id is None:
        return identity.denied(db, 401, event_prefix + ".session_denied")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout='2s'"))
        db.execute(text("SET LOCAL statement_timeout='5s'"))
    user = db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update(read=not exclusive_user)
        .execution_options(populate_existing=True)
    )
    current = identity.resolve(db, token, refresh_session=True) if user and user.is_active else None
    if current is None or current[0].id != user_id:
        return identity.denied(db, 401, event_prefix + ".session_denied")
    session = current[1]
    if (
        not csrf
        or len(csrf) > 128
        or not hmac.compare_digest(session.csrf_hash, identity.digest(csrf))
    ):
        return identity.denied(db, 403, event_prefix + ".csrf_denied", user=user)
    granted = (
        db.scalar(
            text(
                {
                    "tasks": "SELECT public.butler_lock_task_scope(:actor,:scope)",
                    "finance": "SELECT public.butler_lock_finance_scope(:actor,:scope)",
                    "installation": "SELECT public.butler_lock_installation_scope(:actor,:scope)",
                }[scope_lock]
            ),
            {"actor": user.id, "scope": scope},
        )
        if db.get_bind().dialect.name == "postgresql"
        else scope in identity.memberships(db, user)
    )
    if not granted:
        return identity.denied(db, 403, event_prefix + ".scope_denied", user=user)
    return user, session


def visible(user, scope):
    return (
        ManualTask.scope_key == scope,
        or_(ManualTask.owner_id == user.id, ManualTask.scope_key == "household_shared"),
    )


def stamp(value):
    return identity.aware(value).astimezone(UTC).isoformat() if value else None


def document(row):
    result = {
        "id": str(row.id),
        "owner_id": str(row.owner_id),
        "scope": row.scope_key,
        "state": row.state,
        "revision": row.revision,
        "created_at": stamp(row.created_at),
        "updated_at": stamp(row.updated_at),
    }
    if row.state == "active":
        result.update(
            title=row.title,
            details=row.details,
            source_reference=row.source_reference,
            status=row.status,
            assignee_id=str(row.assignee_id) if row.assignee_id else None,
            due_at=stamp(row.due_at),
            completed_at=stamp(row.completed_at),
            cancelled_at=stamp(row.cancelled_at),
        )
    return result


def presented(row, user):
    return dict(document(row), can_edit=row.owner_id == user.id)


def audit(db, user, row, operation, before=None):
    identity.audit(
        db,
        "tasks." + operation,
        "success",
        user=user,
        scope=row.scope_key,
        entity_type="manual_task",
        entity=str(row.id),
        before={"revision": before} if before else None,
        after={"revision": row.revision, "state": row.state, "status": row.status},
    )


def snapshot(db, user, row, operation):
    db.add(
        ManualTaskRevision(
            task_id=row.id,
            revision=row.revision,
            actor_id=user.id,
            operation=operation,
            snapshot=document(row) if row.state == "active" else None,
            created_at=row.updated_at,
        )
    )


def values_for(body, user):
    return {
        "title": body.title,
        "details": body.details,
        "source_reference": body.source_reference,
        "due_at": identity.aware(body.due_at).astimezone(UTC) if body.due_at else None,
        "assignee_id": user.id if body.assignment == "me" else None,
    }


def create(db, token, csrf, body):
    current = authority(db, token, csrf, body.scope)
    if isinstance(current, identity.Result):
        return current
    user, session = current
    now = identity.now_utc()
    row = ManualTask(
        owner_id=user.id,
        scope_key=body.scope,
        state="active",
        status="open",
        revision=1,
        created_at=now,
        updated_at=now,
        **values_for(body, user),
    )
    db.add(row)
    db.flush()
    snapshot(db, user, row, "created")
    audit(db, user, row, "created")
    session.last_seen_at = now
    return identity.Result(201, presented(row, user))


def operate(db, token, csrf, identifier, body, operation):
    current = authority(db, token, csrf, body.scope)
    if isinstance(current, identity.Result):
        return current
    user, session = current
    unsafe = operation in {"correct", "transition", "forget"}
    row = db.scalar(
        select(ManualTask)
        .where(ManualTask.id == identifier, *visible(user, body.scope))
        .with_for_update(read=not unsafe)
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "tasks.session_denied", user=user)
    if row is None:
        return identity.denied(db, 404, "tasks.not_found", user=user)
    if (unsafe or operation == "history") and row.owner_id != user.id:
        return identity.denied(db, 403, "tasks.owner_denied", user=user, scope=body.scope)
    session.last_seen_at = identity.now_utc()
    if operation == "history":
        rows = list(
            db.scalars(
                select(ManualTaskRevision)
                .where(
                    ManualTaskRevision.task_id == row.id, ManualTaskRevision.revision > body.after
                )
                .order_by(ManualTaskRevision.revision)
                .limit(26)
            )
        )
        audit(db, user, row, "history_read")
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "task_id": str(row.id),
                "current_revision": row.revision,
                "state": row.state,
                "items": [
                    {
                        "revision": rev.revision,
                        "actor_id": str(rev.actor_id),
                        "operation": rev.operation,
                        "created_at": stamp(rev.created_at),
                        "snapshot": rev.snapshot,
                    }
                    for rev in rows[:25]
                ],
                "next_cursor": rows[24].revision if len(rows) > 25 else None,
            },
        )
    if unsafe and row.revision != body.expected_revision:
        return identity.denied(db, 409, "tasks.revision_conflict", user=user, scope=body.scope)
    if row.state == "forgotten":
        audit(db, user, row, "forgotten_read")
        return identity.Result(410, document(row))
    before = row.revision
    if operation == "correct":
        values = values_for(body, user)
        if all(
            (identity.aware(row.due_at) if key == "due_at" and row.due_at else getattr(row, key))
            == val
            for key, val in values.items()
        ):
            return identity.denied(db, 409, "tasks.no_change", user=user, scope=body.scope)
        for key, value in values.items():
            setattr(row, key, value)
        operation = "corrected"
    elif operation == "transition":
        if not (
            (row.status == "open" and body.status in {"done", "cancelled"})
            or (row.status in {"done", "cancelled"} and body.status == "open")
        ):
            return identity.denied(db, 409, "tasks.invalid_transition", user=user, scope=body.scope)
        row.status = body.status
        row.completed_at = identity.now_utc() if body.status == "done" else None
        row.cancelled_at = identity.now_utc() if body.status == "cancelled" else None
        operation = {"done": "completed", "cancelled": "cancelled", "open": "reopened"}[body.status]
    elif operation == "forget":
        row.state = "forgotten"
        for name in (
            "title",
            "details",
            "source_reference",
            "status",
            "due_at",
            "assignee_id",
            "completed_at",
            "cancelled_at",
        ):
            setattr(row, name, None)
        operation = "forgotten"
    else:
        audit(db, user, row, "read")
        return identity.Result(200, presented(row, user))
    row.revision += 1
    row.updated_at = (
        row.completed_at or row.cancelled_at
        if operation in {"completed", "cancelled"}
        else identity.now_utc()
    )
    db.flush()
    if row.state == "forgotten":
        db.execute(
            update(ManualTaskRevision)
            .where(ManualTaskRevision.task_id == row.id)
            .values(snapshot=None)
        )
    if row.state == "forgotten" or row.status in {"done", "cancelled"}:
        from app.task_reminders import cancel_for_task

        cancel_for_task(db, user, row)
    snapshot(db, user, row, operation)
    audit(db, user, row, operation, before)
    return identity.Result(200, presented(row, user))


def listing(db, token, csrf, body, export=False):
    current = authority(db, token, csrf, body.scope)
    if isinstance(current, identity.Result):
        return current
    user, session = current
    now = identity.now_utc()
    query = select(ManualTask).where(*visible(user, body.scope), ManualTask.state == "active")
    if body.status != "all":
        query = query.where(ManualTask.status == body.status)
    if body.search:
        query = query.where(
            or_(
                ManualTask.title.icontains(body.search, autoescape=True),
                ManualTask.details.icontains(body.search, autoescape=True),
            )
        )
    if body.due == "unknown":
        query = query.where(ManualTask.due_at.is_(None))
    elif body.due in {"overdue", "next_seven_days"}:
        query = query.where(ManualTask.status == "open", ManualTask.due_at.is_not(None))
        query = (
            query.where(ManualTask.due_at < now)
            if body.due == "overdue"
            else query.where(ManualTask.due_at >= now, ManualTask.due_at < now + timedelta(days=7))
        )
    if body.after:
        query = query.where(ManualTask.id > body.after)
    rows = list(
        db.scalars(
            query.order_by(ManualTask.id)
            .limit(26)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "tasks.session_denied", user=user)
    session.last_seen_at = identity.now_utc()
    identity.audit(
        db,
        "tasks.export" if export else "tasks.query",
        "success",
        user=user,
        scope=body.scope,
        entity_type="manual_task",
        metadata={"returned": min(len(rows), 25)},
    )
    return identity.Result(
        200,
        {
            "schema_version": 1,
            "mode": "manual_task_page",
            "checked_at": now.isoformat(),
            "filters": body.model_dump(mode="json", exclude={"acknowledge_copy_limits"}),
            "page_limit": 25,
            "managed_copy": False if export else None,
            "items": [presented(row, user) for row in rows[:25]],
            "next_cursor": str(rows[24].id) if len(rows) > 25 else None,
        },
    )
