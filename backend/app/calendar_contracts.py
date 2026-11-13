"""Bounded normalized adapter boundary; no ICS parser or network capabilities."""

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.manual_tasks import Expected, Scoped


def zone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Unsupported timezone") from None
    return value


def midnight(value, timezone):
    return datetime.combine(value, time.min, ZoneInfo(timezone)).astimezone(UTC)


def date_only(value):
    if (
        not isinstance(value, (str, date))
        or isinstance(value, datetime)
        or (isinstance(value, str) and len(value) != 10)
    ):
        raise ValueError("Date required")
    return value


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uid: str = Field(min_length=1, max_length=128)
    recurrence_id: str = Field(default="", max_length=128)
    sequence: int = Field(strict=True, ge=0, le=2147483647)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=512)
    status: Literal["confirmed", "tentative", "cancelled"] = "confirmed"
    timezone: str = Field(max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        return zone(value)

    @field_validator("uid", "title")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Nonblank value required")
        return value


class Timed(Event):
    kind: Literal["timed"]
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def times(self):
        if self.end <= self.start or self.end - self.start > timedelta(days=31):
            raise ValueError("Invalid event interval")
        for instant in (self.start, self.end):
            if (
                instant.utcoffset() != timedelta(0)
                and instant.utcoffset() != instant.astimezone(ZoneInfo(self.timezone)).utcoffset()
            ):
                raise ValueError("Source offset differs from timezone")
        return self


class AllDay(Event):
    kind: Literal["all_day"]
    start_date: date
    end_date: date

    _dates = field_validator("start_date", "end_date", mode="before")(date_only)

    @model_validator(mode="after")
    def dates(self):
        if not 1 <= (self.end_date - self.start_date).days <= 31:
            raise ValueError("Invalid all-day interval")
        return self


Occurrence = Annotated[Timed | AllDay, Field(discriminator="kind")]


def interval(event):
    if event["kind"] == "timed":
        return datetime.fromisoformat(event["start"]), datetime.fromisoformat(event["end"])
    return midnight(date.fromisoformat(event["start_date"]), event["timezone"]), midnight(
        date.fromisoformat(event["end_date"]), event["timezone"]
    )


def all_day_dates(event):
    """Calendar dates of a stored all-day occurrence; malformed data is refused, never guessed."""
    try:
        first = date.fromisoformat(event["start_date"])
        last = date.fromisoformat(event["end_date"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Malformed all-day occurrence") from None
    if not 1 <= (last - first).days <= 31:
        raise ValueError("Malformed all-day occurrence")
    return first, last


def placed_on_day(event, day, start, end):
    """Whether an occurrence belongs to the display day ``day`` (the instants ``start`` to ``end``).

    An all-day occurrence is placed by its calendar dates alone (``start_date <= day < end_date``;
    the end date is exclusive), never by instants, so neither zone matters. A timed occurrence is
    placed by instant overlap, exactly as before. Any other kind is refused.
    """
    kind = event.get("kind") if isinstance(event, dict) else None
    if kind == "all_day":
        first, last = all_day_dates(event)
        return first <= day < last
    if kind == "timed":
        a, b = interval(event)
        return a < end and b > start
    raise ValueError("Unknown occurrence kind")


def agenda_key(event):
    """Sort key: all-day before timed; all-day by dates, timed by instants; then stable id."""
    kind = event.get("kind") if isinstance(event, dict) else None
    if kind == "all_day":
        return (0, *all_day_dates(event), event["id"])
    if kind == "timed":
        return (1, *interval(event), event["id"])
    raise ValueError("Unknown occurrence kind")


def key(event):
    return event["uid"], event["recurrence_id"]


class Window(BaseModel):
    model_config = ConfigDict(extra="forbid")
    complete: Literal[True]
    cursor: str = Field(min_length=1, max_length=128)
    fetched_at: AwareDatetime
    timezone: str = Field(max_length=64)
    start_date: date
    end_date: date
    events: list[Occurrence] = Field(max_length=100)

    _zone = field_validator("timezone")(zone)
    _dates = field_validator("start_date", "end_date", mode="before")(date_only)

    @field_validator("complete", mode="before")
    @classmethod
    def complete_only(cls, value):
        if value is not True:
            raise ValueError("Complete snapshot required")
        return value

    @model_validator(mode="after")
    def bounded(self):
        if not 1 <= (self.end_date - self.start_date).days <= 31:
            raise ValueError("Invalid coverage")
        start, end = (
            midnight(self.start_date, self.timezone),
            midnight(self.end_date, self.timezone),
        )
        if end <= start:
            raise ValueError("Coverage has no instants")
        keys = set()
        for event in self.events:
            raw = event.model_dump(mode="json")
            a, b = interval(raw)
            if a >= end or b <= start or key(raw) in keys:
                raise ValueError("Duplicate or outside coverage")
            keys.add(key(raw))
        if len(json.dumps(self.canonical(), ensure_ascii=False).encode()) > 65536:
            raise ValueError("Snapshot byte limit")
        return self

    def canonical(self):
        result = self.model_dump(mode="json")
        result["fetched_at"] = self.fetched_at.astimezone(UTC).isoformat()
        for event in result["events"]:
            if event["kind"] == "timed":
                for field in ("start", "end"):
                    event[field] = datetime.fromisoformat(event[field]).astimezone(UTC).isoformat()
        result["events"].sort(key=key)
        return result


class Create(Scoped):
    label: str = Field(min_length=1, max_length=160)

    @field_validator("label")
    @classmethod
    def label_required(cls, value):
        if not value.strip():
            raise ValueError("Label required")
        return value.strip()


class Import(Expected):
    window: Window


class Unavailable(Expected):
    reason: Literal["offline", "failed"]


class History(Scoped):
    after: int = Field(default=0, strict=True, ge=0, le=101)


class Export(History):
    acknowledge_copy_limits: Literal[True]

    @field_validator("acknowledge_copy_limits", mode="before")
    @classmethod
    def acknowledge(cls, value):
        if value is not True:
            raise ValueError("Explicit acknowledgement required")
        return value


class Query(Scoped):
    after: UUID | None = None
    # Optional expansion of provider sources over a display range (at most 400 days, 8.4 and 9).
    day: date | None = None
    days: int | None = Field(default=None, strict=True)
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return value if value is None else zone(value)

    @field_validator("day", mode="before")
    @classmethod
    def day_only(cls, value):
        return value if value is None else date_only(value)

    @model_validator(mode="after")
    def range_is_complete(self):
        if (self.day is None) != (self.days is None) or (self.day is None) != (
            self.timezone is None
        ):
            raise ValueError("day, days and timezone are given together")
        return self


class Briefing(Scoped):
    day: date
    timezone: str = Field(max_length=64)
    # 1 to 7 (checked by the route as 422 horizon_exceeded); omitted keeps the one-day v1 shape.
    horizon_days: int | None = Field(default=None, strict=True)
    _zone = field_validator("timezone")(zone)
    _day = field_validator("day", mode="before")(date_only)


class Provider(Scoped):
    provider_ref: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")


class Sync(Scoped):
    resync: bool = False
