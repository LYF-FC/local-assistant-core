"""Synthetic lifecycle projections only: no storage, authorization, I/O or execution."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


class LifecycleError(ValueError):
    pass


def clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LifecycleError("Aware server time required")
    return value.astimezone(UTC)


def distinct(values: tuple[UUID, ...]) -> tuple[UUID, ...]:
    if len(values) != len(set(values)):
        raise ValueError("Duplicate source reference")
    return values


Sources = Annotated[tuple[UUID, ...], Field(max_length=10), AfterValidator(distinct)]
Marker = Annotated[
    str, Field(min_length=11, max_length=256, pattern=r"^synthetic:[a-zA-Z0-9 _.-]+$")
]


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class RetentionPolicy(Contract):
    workspace_id: UUID
    policy_id: UUID
    # Safety ceiling for this synthetic contract, not an approved production period.
    max_age_seconds: int = Field(strict=True, gt=0, le=31_536_000)


class Draft(Contract):
    kind: Literal["observation", "question", "decision", "action"]
    marker: Marker = Field(repr=False)
    source_ids: Sources = Field(default=(), repr=False)
    owner_id: UUID | None = None
    due_at: datetime | None = None
    retain_until: datetime

    @model_validator(mode="after")
    def aware_dates(self):
        clock(self.retain_until)
        if self.due_at is not None:
            clock(self.due_at)
        return self


class Record(Contract):
    id: UUID
    workspace_id: UUID
    policy_id: UUID
    revision: int = Field(strict=True, ge=1)
    kind: Literal["observation", "question", "decision", "action"]
    state: Literal["draft", "confirmed", "forgotten"]
    marker: Marker | None = Field(repr=False)
    source_ids: Sources = Field(repr=False)
    owner_id: UUID | None
    due_at: datetime | None
    retain_until: datetime | None
    actor_id: UUID
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def coherent(self):
        created, updated = clock(self.created_at), clock(self.updated_at)
        if updated < created:
            raise ValueError("Invalid record clock")
        if self.state == "forgotten":
            if (
                any(
                    v is not None
                    for v in (self.marker, self.owner_id, self.due_at, self.retain_until)
                )
                or self.source_ids
            ):
                raise ValueError("Forgotten payload must be fully redacted")
        elif (
            self.marker is None or self.retain_until is None or clock(self.retain_until) <= created
        ):
            raise ValueError("Live record requires bounded payload and retention")
        if self.state == "confirmed" and not self.source_ids:
            raise ValueError("Confirmation requires selected source references")
        if self.due_at is not None:
            clock(self.due_at)
        return self


History = tuple[Record, ...]


def _lineage(history: History, workspace_id: UUID, now: datetime) -> Record:
    now = clock(now)
    if (
        not isinstance(workspace_id, UUID)
        or not isinstance(history, tuple)
        or not history
        or len(history) > 101
        or any(not isinstance(item, Record) for item in history)
    ):
        raise LifecycleError("Invalid bounded workspace history")
    first = history[0]
    all_forgotten = all(item.state == "forgotten" for item in history)
    if any(item.state == "forgotten" for item in history) and not all_forgotten:
        raise LifecycleError("Partial history redaction is forbidden")
    if not all_forgotten and (first.state != "draft" or len(history) > 100):
        raise LifecycleError("Invalid initial state or history bound")
    previous_time = first.created_at
    previous = None
    for revision, item in enumerate(history, 1):
        if (
            item.workspace_id != workspace_id
            or item.id != first.id
            or item.kind != first.kind
            or item.policy_id != first.policy_id
            or item.created_at != first.created_at
            or item.revision != revision
            or not previous_time <= item.updated_at <= now
        ):
            raise LifecycleError("Inconsistent workspace history")
        if previous is not None and not all_forgotten:
            if item.retain_until > previous.retain_until:
                raise LifecycleError("History extends retention")
            if item.state == "confirmed" and (
                previous.state != "draft"
                or any(
                    getattr(item, key) != getattr(previous, key)
                    for key in ("marker", "source_ids", "owner_id", "due_at", "retain_until")
                )
            ):
                raise LifecycleError("Confirmation changed payload")
        previous = item
        previous_time = item.updated_at
    return history[-1]


def _metadata(workspace_id: UUID, actor_id: UUID) -> None:
    if not isinstance(workspace_id, UUID) or not isinstance(actor_id, UUID):
        raise LifecycleError("Typed server metadata required")


def create(
    payload: Draft,
    workspace_id: UUID,
    actor_id: UUID,
    policy: RetentionPolicy,
    now: datetime,
    *,
    record_id: UUID,
) -> History:
    _metadata(workspace_id, actor_id)
    _metadata(workspace_id, record_id)
    now = clock(now)
    if policy.workspace_id != workspace_id or not now < payload.retain_until <= now + timedelta(
        seconds=policy.max_age_seconds
    ):
        raise LifecycleError("Explicit workspace retention policy required")
    return (
        Record(
            id=record_id,
            workspace_id=workspace_id,
            policy_id=policy.policy_id,
            revision=1,
            state="draft",
            actor_id=actor_id,
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        ),
    )


def _current(history: History, workspace_id: UUID, expected_revision: int, now: datetime) -> Record:
    item = _lineage(history, workspace_id, now)
    if type(expected_revision) is not int or expected_revision != item.revision:
        raise LifecycleError("Stale revision")
    return item


def _append(history: History, item: Record, actor_id: UUID, now: datetime, **changes) -> History:
    _metadata(item.workspace_id, actor_id)
    if len(history) >= 100 and changes.get("state") != "forgotten":
        raise LifecycleError("History limit reached")
    value = dict(
        item.model_dump(), revision=item.revision + 1, actor_id=actor_id, updated_at=clock(now)
    )
    value.update(changes)
    return (*history, Record.model_validate(value))


def _live(item: Record, now: datetime) -> None:
    if item.state == "forgotten" or item.retain_until is None or clock(now) >= item.retain_until:
        raise LifecycleError("Record is unavailable")


def confirm(
    history: History, workspace_id: UUID, actor_id: UUID, expected_revision: int, now: datetime
) -> History:
    item = _current(history, workspace_id, expected_revision, now)
    _live(item, now)
    if item.state != "draft" or not item.source_ids:
        raise LifecycleError("Grounded draft review required")
    return _append(history, item, actor_id, now, state="confirmed")


def correct(
    history: History,
    payload: Draft,
    workspace_id: UUID,
    actor_id: UUID,
    expected_revision: int,
    now: datetime,
) -> History:
    item = _current(history, workspace_id, expected_revision, now)
    _live(item, now)
    if payload.kind != item.kind or not clock(now) < payload.retain_until <= item.retain_until:
        raise LifecycleError("Correction cannot reclassify or extend retention")
    return _append(history, item, actor_id, now, state="draft", **payload.model_dump())


def forget(
    history: History, workspace_id: UUID, actor_id: UUID, expected_revision: int, now: datetime
) -> History:
    item = _current(history, workspace_id, expected_revision, now)
    _metadata(workspace_id, actor_id)
    if item.state == "forgotten":
        return history
    redaction = {
        "state": "forgotten",
        "marker": None,
        "source_ids": (),
        "owner_id": None,
        "due_at": None,
        "retain_until": None,
    }
    # This returns a plan/projection; earlier Python references/storage are not erased.
    redacted = tuple(Record.model_validate(dict(old.model_dump(), **redaction)) for old in history)
    return _append(redacted, redacted[-1], actor_id, now, **redaction)


class ExportPreview(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["synthetic_lifecycle_preview"] = "synthetic_lifecycle_preview"
    workspace_id: UUID
    generated_at: datetime
    items: tuple[Record, ...] = Field(repr=False)
    persistent_export: Literal[False] = False
    execution_allowed: Literal[False] = False


def export_preview(
    histories: tuple[History, ...],
    workspace_id: UUID,
    now: datetime,
    *,
    include_drafts: bool = False,
) -> ExportPreview:
    now = clock(now)
    if (
        not isinstance(workspace_id, UUID)
        or not isinstance(histories, tuple)
        or len(histories) > 25
        or type(include_drafts) is not bool
    ):
        raise LifecycleError("Invalid bounded export selection")
    selected, identifiers = [], set()
    for history in histories:
        item = _lineage(history, workspace_id, now)
        if item.id in identifiers:
            raise LifecycleError("Duplicate export selection")
        identifiers.add(item.id)
        if item.state == "forgotten" or item.retain_until <= now:
            continue
        if item.state == "draft" and not include_drafts:
            continue
        selected.append(item)
    return ExportPreview(workspace_id=workspace_id, generated_at=now, items=tuple(selected))
