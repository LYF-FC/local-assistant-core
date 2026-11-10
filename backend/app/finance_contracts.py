"""Closed manual financial capture values; no calculation or execution authority."""

import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Values(Schema):
    schema_version: Literal[1]
    topic: Literal["lifestyle", "horizon", "spending", "property", "constraint", "general"]
    basis: Literal["confirmed_input", "assumption", "forecast", "unknown"]
    title: str = Field(min_length=1, max_length=160)
    statement: str = Field(default="", max_length=4000)
    as_of: date
    target_date: date | None = None
    source_reference: str = Field(min_length=1, max_length=512)
    source_date: date | None = None
    amount: str | None = None
    currency: Literal["EUR", "USD", "GBP", "CHF", "CAD", "JPY"] | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def version(cls, v):
        if type(v) is not int or v != 1:
            raise ValueError("Schema1 required")
        return v

    @field_validator("title", "source_reference", "statement")
    @classmethod
    def printable(cls, v):
        if any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in v):
            raise ValueError("Printable text required")
        return v.strip()

    @field_validator("title", "source_reference")
    @classmethod
    def nonblank(cls, v):
        if not v:
            raise ValueError("Nonblank text required")
        return v

    @field_validator("as_of", "target_date", "source_date", mode="before")
    @classmethod
    def calendar_date(cls, v):
        if v is None:
            return v
        if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("Calendar date required")
        result = date.fromisoformat(v)
        if not 1900 <= result.year <= 2200:
            raise ValueError("Date outside supported range")
        return result

    @field_validator("amount", mode="before")
    @classmethod
    def decimal_string(cls, v):
        if v is None:
            return None
        if not isinstance(v, str) or not re.fullmatch(
            r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?", v
        ):
            raise ValueError("Bounded fixed decimal string required")
        return format(Decimal(v), ".2f")

    def payload(self):
        if (self.amount is None) != (self.currency is None):
            raise ValueError("Amount and currency must be paired")
        return self.model_dump(mode="json")


class Scoped(Schema):
    scope: Literal["finance_private"]


class Create(Scoped):
    kind: Literal["goal", "assumption", "plan", "source"]
    values: Values


class Expected(Scoped):
    expected_revision: int = Field(strict=True, ge=1, le=101)


class Correct(Expected):
    values: Values


class Accept(Expected):
    acknowledge_record_only: Literal[True]

    @field_validator("acknowledge_record_only", mode="before")
    @classmethod
    def explicit(cls, v):
        if v is not True:
            raise ValueError("Explicit acknowledgement required")
        return v


class Query(Scoped):
    after: UUID | None = None
    search: str = Field(default="", max_length=160)


class History(Scoped):
    after: int = Field(default=0, strict=True, ge=0, le=101)


class Export(Query):
    format: Literal["json", "markdown"] = "json"
    acknowledge_copy_limits: Literal[True]
    _explicit = field_validator("acknowledge_copy_limits", mode="before")(Accept.explicit.__func__)


class RecordExport(Expected):
    after: int = Field(default=0, strict=True, ge=0, le=101)
    acknowledge_copy_limits: Literal[True]
    format: Literal["json", "markdown"] = "json"
    _explicit = field_validator("acknowledge_copy_limits", mode="before")(Accept.explicit.__func__)
