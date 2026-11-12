"""Read-only provider interface and the synthetic SQLite provider (Batch 3, commit 2).

The provider contract has **no write method**: a provider can only be asked for changes since an
opaque cursor. The synthetic provider opens a SQLite file (WAL) read-only inside one directory
that configuration names; ``provider_ref`` selects a file name there and is never a path. A
separate writer process (test harness, ``tests/calendar_synthetic_writer.py``) is the only
component that appends to it.

This module imports no network, socket or HTTP library (asserted by a static test).
"""

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Protocol

from app import calendar_codes as codes

REF_PATTERN = re.compile(r"[a-z0-9_-]{1,64}")
CURSOR_PATTERN = re.compile(r"v1:[0-9]{1,15}")


class ProviderError(Exception):
    """Base of the typed provider errors."""


class ProviderUnavailable(ProviderError):
    pass


class ProviderTimeout(ProviderError):
    pass


class InvalidCursor(ProviderError):
    pass


class CursorExpired(ProviderError):
    pass


class PageTooLarge(ProviderError):
    pass


class MalformedItem(ProviderError):
    def __init__(self, index):
        super().__init__(f"malformed item at {index}")
        self.index = index


@dataclass(frozen=True)
class ProviderItem:
    """An upsert or explicit delete of a series or an override (untrusted until normalized)."""

    entity: str  # series | override
    operation: str  # upsert | delete
    uid: str
    sequence: int
    recurrence_id: str | None = None  # override only: the RECURRENCE-ID value string
    body: object = None  # upsert only: the RFC 5545 terms of section 5, still raw


@dataclass(frozen=True)
class ChangePage:
    items: tuple
    next_cursor: str
    has_more: bool


class CalendarProvider(Protocol):
    def changes(self, since: str | None, limit: int) -> ChangePage: ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS changes (
  change_id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity TEXT NOT NULL,
  operation TEXT NOT NULL,
  uid TEXT NOT NULL,
  recurrence_id TEXT,
  sequence INTEGER NOT NULL,
  body TEXT
);
CREATE TABLE IF NOT EXISTS events (
  entity TEXT NOT NULL,
  uid TEXT NOT NULL,
  recurrence_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  deleted INTEGER NOT NULL,
  PRIMARY KEY (entity, uid, recurrence_id)
);
CREATE TABLE IF NOT EXISTS faults (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  times INTEGER NOT NULL DEFAULT 1,
  arg TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
"""


def _cursor_id(cursor):
    if cursor is None:
        return 0
    if not isinstance(cursor, str) or not CURSOR_PATTERN.fullmatch(cursor):
        raise InvalidCursor("malformed cursor")
    return int(cursor[3:])


class SyntheticProvider:
    """Read-only view of one synthetic fixture file; each page is one read transaction."""

    def __init__(self, directory, ref):
        if not isinstance(ref, str) or not REF_PATTERN.fullmatch(ref):
            raise ProviderUnavailable("invalid provider reference")
        root = os.path.realpath(directory)
        target = os.path.join(root, ref + ".sqlite")
        resolved = os.path.realpath(target)
        if os.path.dirname(resolved) != root or not os.path.isfile(resolved):
            raise ProviderUnavailable("fixture not available")
        self._path = resolved
        self._faults = None  # (kind, remaining, arg) read once, consumed in memory

    def _connect(self):
        try:
            connection = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error:
            raise ProviderUnavailable("fixture not readable") from None
        connection.isolation_level = None
        return connection

    def _scripted_faults(self, connection):
        if self._faults is None:
            rows = connection.execute("SELECT kind, times, arg FROM faults ORDER BY id").fetchall()
            self._faults = [[kind, times, arg] for kind, times, arg in rows]
        for fault in self._faults:
            kind, remaining, arg = fault
            if kind == "delay":
                time.sleep(float(arg or 0))
            elif kind in {"timeout", "unavailable"} and remaining > 0:
                fault[1] -= 1
                if kind == "timeout":
                    raise ProviderTimeout("scripted timeout")
                raise ProviderUnavailable("scripted unavailable")

    def changes(self, since, limit):
        if type(limit) is not int or not 1 <= limit <= codes.PAGE_ITEMS_MAX:
            raise PageTooLarge("limit out of range")
        after = _cursor_id(since)
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._scripted_faults(connection)
            newest = connection.execute(
                "SELECT COALESCE(MAX(change_id), 0) FROM changes"
            ).fetchone()[0]
            floor = connection.execute(
                "SELECT COALESCE((SELECT value FROM meta WHERE key='min_retained'), 0)"
            ).fetchone()[0]
            if after > newest:
                raise InvalidCursor("cursor unknown to the provider")
            if since is not None and after < floor:
                raise CursorExpired("history no longer held")
            rows = connection.execute(
                "SELECT change_id, entity, operation, uid, recurrence_id, sequence, body "
                "FROM changes WHERE change_id > ? ORDER BY change_id LIMIT ?",
                (after, limit + 1),
            ).fetchall()
            connection.execute("COMMIT")
        except sqlite3.Error:
            raise ProviderUnavailable("fixture read failed") from None
        finally:
            connection.close()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = []
        for index, (_, entity, operation, uid, recurrence_id, sequence, body) in enumerate(rows):
            try:
                parsed = None if body is None else json.loads(body)
            except ValueError:
                raise MalformedItem(index) from None
            items.append(ProviderItem(entity, operation, uid, sequence, recurrence_id, parsed))
        if len(json.dumps([vars(i) for i in items], ensure_ascii=False).encode()) > (
            codes.PAGE_BYTES_MAX
        ):
            raise PageTooLarge("page exceeds the byte limit")
        last = rows[-1][0] if rows else after
        next_cursor = f"v1:{last}" if rows or since is None else since
        return ChangePage(tuple(items), next_cursor, has_more)
