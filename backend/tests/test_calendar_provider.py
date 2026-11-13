"""Synthetic provider and writer harness: contract, containment, faults, real separate process."""

import ast
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from calendar_synthetic_writer import DependencyOrder, SyntheticWriter

from app import calendar_codes as codes
from app import calendar_provider as provider
from app.calendar_provider import (
    CalendarProvider,
    CursorExpired,
    InvalidCursor,
    MalformedItem,
    PageTooLarge,
    ProviderTimeout,
    ProviderUnavailable,
    SyntheticProvider,
)

APP = Path(__file__).resolve().parents[1] / "app"
BACKEND = Path(__file__).resolve().parents[1]


def series_item(uid="s1", sequence=1, **body):
    return {
        "entity": "series",
        "operation": "upsert",
        "uid": uid,
        "sequence": sequence,
        "body": {
            "title": "Synthetic",
            "dtstart": "TZID=Europe/Paris:20260315T090000",
            "duration": 3600,
            "rrule": "FREQ=WEEKLY;COUNT=4",
            **body,
        },
    }


def override_item(uid="s1", sequence=1, recurrence_id="TZID=Europe/Paris:20260322T090000"):
    return {
        "entity": "override",
        "operation": "upsert",
        "uid": uid,
        "recurrence_id": recurrence_id,
        "sequence": sequence,
        "body": {"recurrence_id": recurrence_id, "status": "cancelled"},
    }


@pytest.fixture
def fixture(tmp_path):
    writer = SyntheticWriter(tmp_path / "household.sqlite")
    return tmp_path, writer, SyntheticProvider(tmp_path, "household")


def test_pages_cursor_progress_and_has_more(fixture):
    _, writer, reader = fixture
    empty = reader.changes(None, 10)
    assert (empty.items, empty.next_cursor, empty.has_more) == ((), "v1:0", False)
    ids = writer.append([series_item("a"), series_item("b"), series_item("c")])
    first = reader.changes(None, 2)
    assert [i.uid for i in first.items] == ["a", "b"]
    assert first.has_more and first.next_cursor == f"v1:{ids[1]}"
    second = reader.changes(first.next_cursor, 2)
    assert [i.uid for i in second.items] == ["c"]
    assert not second.has_more and second.next_cursor == f"v1:{ids[2]}"
    caught_up = reader.changes(second.next_cursor, 2)
    assert (caught_up.items, caught_up.next_cursor, caught_up.has_more) == (
        (),
        second.next_cursor,
        False,
    )
    assert first.items[0].body["title"] == "Synthetic" and first.items[0].entity == "series"


def test_invalid_expired_and_malformed_cursors(fixture):
    _, writer, reader = fixture
    ids = writer.append([series_item("a"), series_item("b"), series_item("c")])
    for bad in ("garbage", "v2:1", "v1:", "v1:-1", "v1:1.5", "", 5):
        with pytest.raises(InvalidCursor):
            reader.changes(bad, 10)
    with pytest.raises(InvalidCursor):
        reader.changes(f"v1:{ids[-1] + 50}", 10)
    writer.truncate_before(ids[2])
    with pytest.raises(CursorExpired):
        reader.changes("v1:0", 10)
    assert [i.uid for i in reader.changes(f"v1:{ids[1]}", 10).items] == ["c"]


def test_since_none_restarts_from_the_retained_history_even_after_expiry(fixture):
    _, writer, reader = fixture
    ids = writer.append([series_item("a"), series_item("b")])
    writer.truncate_before(ids[1])
    with pytest.raises(CursorExpired):
        reader.changes("v1:0", 10)
    # An owner resync (since=None) must never be reported invalid or expired.
    assert [i.uid for i in reader.changes(None, 10).items] == ["b"]


def test_limit_and_page_size_are_enforced(fixture):
    _, writer, reader = fixture
    for bad in (0, -1, codes.PAGE_ITEMS_MAX + 1, "10", True):
        with pytest.raises(PageTooLarge):
            reader.changes(None, bad)
    writer.append([series_item("big", title="x" * 70000)])
    with pytest.raises(PageTooLarge):
        reader.changes(None, 10)


def test_a_malformed_row_names_its_page_index(fixture):
    _, writer, reader = fixture
    writer.append([series_item("a"), {**series_item("b"), "raw_body": "{not json"}])
    with pytest.raises(MalformedItem) as caught:
        reader.changes(None, 10)
    assert caught.value.index == 1


def test_unsupported_rules_are_delivered_raw_for_the_sync_layer_to_refuse(fixture):
    _, writer, reader = fixture
    writer.append([series_item("a", rrule="FREQ=HOURLY")])
    (item,) = reader.changes(None, 10).items
    assert item.body["rrule"] == "FREQ=HOURLY"  # the provider never interprets rules


def test_duplicate_and_out_of_order_delivery_are_reproducible(fixture):
    _, writer, reader = fixture
    writer.append([series_item("b", 2), series_item("a", 1), series_item("a", 1)])
    got = [(i.uid, i.sequence) for i in reader.changes(None, 10).items]
    assert got == [("b", 2), ("a", 1), ("a", 1)]


def test_dependency_order_is_honoured_by_construction_and_the_fault_bypasses_it(fixture):
    _, writer, reader = fixture
    with pytest.raises(DependencyOrder):
        writer.append([override_item("missing")])
    assert reader.changes(None, 10).items == ()  # the refused batch left nothing behind
    writer.append([series_item("s1"), override_item("s1")])  # same batch, series first
    writer.append([override_item("s1", 2)])  # series already earlier in the log
    for limit in (1, 2, 3):  # holds at every page size, including 1
        cursor, seen = None, []
        while True:
            page = reader.changes(cursor, limit)
            seen += [(i.entity, i.uid) for i in page.items]
            cursor = page.next_cursor
            if not page.has_more:
                break
        assert seen[0] == ("series", "s1") and len(seen) == 3
    writer.append([override_item("ghost")], force=True)  # test-only override_before_series
    assert reader.changes(None, 10).items[-1].uid == "ghost"


def test_replace_from_rewrites_the_unapplied_tail(fixture):
    _, writer, reader = fixture
    ids = writer.append([series_item("a"), {**series_item("b"), "raw_body": "{bad"}])
    with pytest.raises(MalformedItem):
        reader.changes(None, 10)
    writer.replace_from(ids[1], [series_item("b")])
    assert [i.uid for i in reader.changes(f"v1:{ids[0]}", 10).items] == ["b"]


def test_scripted_faults_timeout_and_unavailable_then_recover(fixture):
    tmp, writer, _ = fixture
    writer.append([series_item("a")])
    writer.add_fault("timeout", 2)
    writer.add_fault("unavailable", 1)
    reader = SyntheticProvider(tmp, "household")
    for _ in range(2):
        with pytest.raises(ProviderTimeout):
            reader.changes(None, 10)
    with pytest.raises(ProviderUnavailable):
        reader.changes(None, 10)
    assert [i.uid for i in reader.changes(None, 10).items] == ["a"]


def test_provider_refs_are_names_never_paths(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    directory = tmp_path / "fixtures"
    directory.mkdir()
    SyntheticWriter(directory / "good.sqlite")
    SyntheticWriter(outside / "secret.sqlite")
    (directory / "escape.sqlite").symlink_to(outside / "secret.sqlite")
    assert SyntheticProvider(directory, "good").changes(None, 5).items == ()
    for ref in (
        "../outside/secret",
        "/etc/passwd",
        "a/b",
        "Good",
        "good.sqlite",
        "",
        "x" * 65,
        "missing",
        "escape",
        None,
        5,
    ):
        with pytest.raises(ProviderUnavailable):
            SyntheticProvider(directory, ref)


def test_the_provider_opens_the_file_read_only(fixture):
    _, _, reader = fixture
    connection = reader._connect()
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO meta (key, value) VALUES ('x', 1)")
    finally:
        connection.close()


def test_a_separate_writer_process_and_the_reader_see_the_same_file(tmp_path):
    path = tmp_path / "shared.sqlite"
    commands = "\n".join(
        json.dumps(c)
        for c in (
            {"op": "append", "items": [series_item("a"), series_item("b")]},
            {"op": "append", "items": [override_item("a")]},
        )
    )
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    done = subprocess.run(
        [sys.executable, str(BACKEND / "tests" / "calendar_synthetic_writer.py"), str(path)],
        input=commands,
        capture_output=True,
        text=True,
        env=env,
        cwd=BACKEND,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert [json.loads(line) for line in done.stdout.splitlines()] == [[1, 2], [3]]
    reader = SyntheticProvider(tmp_path, "shared")
    assert [(i.entity, i.uid) for i in reader.changes(None, 10).items] == [
        ("series", "a"),
        ("series", "b"),
        ("override", "a"),
    ]


def test_the_provider_contract_has_no_write_method():
    public = lambda cls: {n for n in vars(cls) if not n.startswith("_")}
    assert public(CalendarProvider) == {"changes"}
    assert public(SyntheticProvider) == {"changes"}


def test_the_provider_module_imports_no_network_library():
    banned = {
        "socket",
        "ssl",
        "http",
        "urllib",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "smtplib",
        "poplib",
        "imaplib",
        "telnetlib",
        "xmlrpc",
        "asyncio",
        "websockets",
    }
    imported = set()
    for node in ast.walk(ast.parse((APP / "calendar_provider.py").read_text())):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert not imported & banned
    assert provider.SyntheticProvider.__module__ == "app.calendar_provider"


def test_the_shared_code_lists_are_consistent():
    assert len(set(codes.BLOCKED_REASONS)) == len(codes.BLOCKED_REASONS)
    assert not set(codes.BLOCKED_REASONS) & set(codes.LAST_ERROR_CODES)
    assert codes.TOMBSTONE_HASH == (
        "136a90c93d282c605c5a7003b6a381fa429e9bce3201d454cb59a41480005b01"
    )
    # The digest is length-prefixed: these two tuples collide under raw concatenation only.
    assert codes.recurrence_digest("s", "ab", "c") != codes.recurrence_digest("s", "a", "bc")
    assert len(codes.uid_digest("s", "u")) == 12
    assert codes.BACKOFF_SECONDS == (30, 120, 600, 3600)
