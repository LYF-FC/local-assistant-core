"""Writer harness for the synthetic SQLite calendar provider (tests only, never shipped).

Run as a separate OS process (``python calendar_synthetic_writer.py <file> < commands.jsonl``) or
imported. It is the only component that appends to the fixture file; the application opens the
same file read-only. It refuses to append an override unless its series already exists earlier in
the log (or earlier in the same batch), so the provider honours the dependency-order contract at
every page size; ``force=True`` is the test-only ``override_before_series`` fault.
"""

import json
import sqlite3
import sys

from app.calendar_provider import SCHEMA


class DependencyOrder(Exception):
    pass


class SyntheticWriter:
    def __init__(self, path):
        self.path = str(path)
        connection = self._connect()
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(SCHEMA)
        connection.close()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.isolation_level = None
        return connection

    @staticmethod
    def _row(item):
        body = item.get("body")
        text = (
            item["raw_body"] if "raw_body" in item else None if body is None else json.dumps(body)
        )
        return (
            item["entity"],
            item["operation"],
            item["uid"],
            item.get("recurrence_id"),
            item["sequence"],
            text,
        )

    def append(self, items, *, force=False):
        """Append one atomic batch; returns the new change ids."""
        connection = self._connect()
        ids = []
        try:
            connection.execute("BEGIN IMMEDIATE")
            for item in items:
                if item["entity"] == "override" and not force:
                    known = connection.execute(
                        "SELECT 1 FROM changes WHERE entity='series' AND uid=? LIMIT 1",
                        (item["uid"],),
                    ).fetchone()
                    if known is None:
                        connection.execute("ROLLBACK")
                        raise DependencyOrder(item["uid"])
                cursor = connection.execute(
                    "INSERT INTO changes (entity, operation, uid, recurrence_id, sequence, body) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    self._row(item),
                )
                ids.append(cursor.lastrowid)
                connection.execute(
                    "INSERT INTO events (entity, uid, recurrence_id, sequence, deleted) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(entity, uid, recurrence_id) DO UPDATE "
                    "SET sequence=excluded.sequence, deleted=excluded.deleted",
                    (
                        item["entity"],
                        item["uid"],
                        item.get("recurrence_id") or "",
                        item["sequence"],
                        int(item["operation"] == "delete"),
                    ),
                )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return ids

    def replace_from(self, change_id, items, *, force=False):
        """Rewrite the unapplied tail of the log (simulates a provider-side correction)."""
        connection = self._connect()
        try:
            connection.execute("DELETE FROM changes WHERE change_id >= ?", (change_id,))
        finally:
            connection.close()
        return self.append(items, force=force)

    def truncate_before(self, change_id):
        """Drop history older than ``change_id`` so older cursors expire."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM changes WHERE change_id < ?", (change_id,))
            connection.execute(
                "INSERT INTO meta (key, value) VALUES ('min_retained', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (change_id - 1,),
            )
            connection.execute("COMMIT")
        finally:
            connection.close()

    def add_fault(self, kind, times=1, arg=None):
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO faults (kind, times, arg) VALUES (?, ?, ?)", (kind, times, arg)
            )
        finally:
            connection.close()


def main(argv=None, stdin=None):
    """Apply JSON-lines commands: ``{"op": "append"|"replace_from"|"truncate_before"|...}``."""
    argv = sys.argv[1:] if argv is None else argv
    writer = SyntheticWriter(argv[0])
    for line in stdin or sys.stdin:
        if not line.strip():
            continue
        command = json.loads(line)
        operation = command.pop("op")
        print(json.dumps(getattr(writer, operation)(**command)), flush=True)


if __name__ == "__main__":
    main()
