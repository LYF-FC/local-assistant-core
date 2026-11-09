"""Finite explicit recurrence rules; no free-form rule/parser or provider access."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from app.calendar_contracts import date_only, zone
from app.manual_tasks import Expected, Scoped


class Values(Scoped):
    title: str = Field(min_length=1, max_length=160)
    details: str = Field(default="", max_length=2000)
    source_reference: str = Field(min_length=1, max_length=512)
    timezone: str = Field(min_length=1, max_length=64)
    local_time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    frequency: Literal["daily", "weekly"]
    interval: int = Field(strict=True, ge=1, le=4)
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    starts_on: date
    ends_on: date
    remind: bool = Field(strict=True)
    _zone = field_validator("timezone")(zone)
    _dates = field_validator("starts_on", "ends_on", mode="before")(date_only)

    @field_validator("title", "source_reference")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Nonblank text required")
        return value.strip()

    @field_validator("weekdays", mode="before")
    @classmethod
    def days(cls, value):
        if (
            not isinstance(value, list)
            or any(type(x) is not int or not 1 <= x <= 7 for x in value)
            or len(set(value)) != len(value)
        ):
            raise ValueError("Distinct ISO weekdays required")
        return sorted(value)

    @model_validator(mode="after")
    def valid_rule(self):
        if not 0 <= (self.ends_on - self.starts_on).days <= 365:
            raise ValueError("Finite rule of at most 366 days required")
        if (self.frequency == "weekly") != bool(self.weekdays):
            raise ValueError("Weekdays are required only for weekly rules")
        return self


class Save(Values):
    authorize_future_tasks: Literal[True]

    @field_validator("authorize_future_tasks", mode="before")
    @classmethod
    def authorize(cls, value):
        if value is not True:
            raise ValueError("Explicit scheduling authorization required")
        return value


class Correct(Save):
    expected_revision: int = Field(strict=True, ge=1)


class Action(Expected):
    action: Literal["pause", "resume", "forget"]


class Query(Scoped):
    after: UUID | None = None


class History(Scoped):
    after: int = Field(default=0, strict=True, ge=0)


class Occurrences(Scoped):
    after_date: date | None = None


class Export(History):
    after_date: date | None = None
    acknowledge_copy_limits: Literal[True]

    @field_validator("acknowledge_copy_limits", mode="before")
    @classmethod
    def acknowledge(cls, value):
        if value is not True:
            raise ValueError("Explicit copy acknowledgement required")
        return value


def local_instant(day, clock, timezone):
    """Round-trip both folds; a gap has no instant, a fold chooses the earlier one."""
    naive = datetime.combine(day, time.fromisoformat(clock))
    z = ZoneInfo(timezone)
    valid = []
    for fold in (0, 1):
        instant = naive.replace(tzinfo=z, fold=fold).astimezone(UTC)
        if instant.astimezone(z).replace(tzinfo=None) == naive:
            valid.append(instant)
    return min(valid) if valid else None


def resolve(values, now, *, resumed=False):
    z = ZoneInfo(values.timezone)
    today = now.astimezone(z).date()
    if values.starts_on < today and not resumed:
        raise ValueError("Start date must be today or later")
    monday = values.starts_on - timedelta(days=values.starts_on.weekday())
    plan = []
    for offset in range((values.ends_on - values.starts_on).days + 1):
        day = values.starts_on + timedelta(days=offset)
        eligible = (
            offset % values.interval == 0
            if values.frequency == "daily"
            else (
                ((day - monday).days // 7) % values.interval == 0
                and day.isoweekday() in values.weekdays
            )
        )
        if not eligible or day < today:
            continue
        instant = local_instant(day, values.local_time, values.timezone)
        if instant is not None and instant <= now:
            continue
        plan.append({"day": day.isoformat(), "due_at": instant.isoformat() if instant else None})
    if not any(item["due_at"] for item in plan):
        raise ValueError("At least one future real occurrence is required")
    return {
        "values": values.model_dump(mode="json", include=set(Values.model_fields)),
        "plan": plan,
    }


def next_at(data, position=0):
    return next(
        (datetime.fromisoformat(p["due_at"]) for p in data["plan"][position:] if p["due_at"]), None
    )
