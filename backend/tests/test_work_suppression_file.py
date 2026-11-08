"""Protected local metadata file handling, canonical integrity and strict structure."""

import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app import work_suppression_file as files
from app.work_suppression import Request


def manifest(**changes):
    values = {
        "export_id": uuid4(),
        "workspace_id": uuid4(),
        "exported_by": uuid4(),
        "source_database_oid": 1,
        "generated_at": datetime.now(UTC),
        "items": (),
    }
    values.update(changes)
    body = files.Body(**values)
    return files.Manifest(body=body, digest=files.digest(body))


def test_exclusive_protected_roundtrip_no_overwrite(tmp_path):
    value = manifest()
    path = tmp_path / "manifest.json"
    files.write_file(path, value)
    assert path.stat().st_mode & 0o777 == 0o600
    assert files.read_file(path) == value
    with pytest.raises(FileExistsError):
        files.write_file(path, manifest())
    assert files.read_file(path) == value


@pytest.mark.parametrize(
    "fault",
    [
        "symlink",
        "hardlink",
        "fifo",
        "directory",
        "public",
        "oversize",
        "duplicate",
        "digest",
        "json",
        "deep_json",
        "missing_header",
        "boolean_header",
        "extra",
    ],
)
def test_untrusted_files_are_rejected_without_hanging(tmp_path, fault):
    path = tmp_path / "manifest.json"
    value = manifest()
    files.write_file(path, value)
    if fault == "symlink":
        other = tmp_path / "link"
        other.symlink_to(path)
        path = other
    elif fault == "hardlink":
        os.link(path, tmp_path / "other")
    elif fault == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    elif fault == "directory":
        path = tmp_path
    elif fault == "public":
        path.chmod(0o640)
    elif fault == "oversize":
        path.write_bytes(b" " * 32769)
    elif fault == "duplicate":
        path.write_text('{"body":{},"body":{},"digest":"' + "a" * 64 + '"}')
    elif fault == "digest":
        data = value.model_dump(mode="json")
        data["body"]["workspace_id"] = str(uuid4())
        path.write_text(json.dumps(data))
    elif fault == "deep_json":
        path.write_text("[" * 2000 + "0" + "]" * 2000)
    elif fault in {"missing_header", "boolean_header"}:
        data = value.model_dump(mode="json")
        if fault == "missing_header":
            del data["body"]["schema_version"]
        else:
            data["body"]["schema_version"] = True
        path.write_text(json.dumps(data))
    elif fault == "json":
        path.write_text("{")
    else:
        data = value.model_dump(mode="json")
        data["extra"] = True
        path.write_text(json.dumps(data))
    with pytest.raises((ValueError, OSError)):
        files.read_file(path)


def test_wrong_owner_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    files.write_file(path, manifest())
    original = os.geteuid()
    monkeypatch.setattr(files.os, "geteuid", lambda: original + 1)
    with pytest.raises(ValueError):
        files.read_file(path)


def test_failed_fsync_removes_only_new_file(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"

    def fail(_):
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(files.os, "fsync", fail)
    with pytest.raises(OSError):
        files.write_file(path, manifest())
    assert not path.exists()


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "unordered",
        "future",
        "naive",
        "revision",
        "revision_cap",
        "party_revision",
        "cap",
    ],
)
def test_terminal_entries_are_bounded_ordered_and_aware(fault):
    now = datetime.now(UTC)
    item = {
        "kind": "note",
        "id": uuid4(),
        "forgotten_revision": 2,
        "forgotten_at": now - timedelta(seconds=1),
    }
    items = [item]
    if fault == "duplicate":
        items = [item, item]
    elif fault == "unordered":
        items = [dict(item, kind="party"), item]
    elif fault == "future":
        item["forgotten_at"] = now + timedelta(minutes=1)
    elif fault == "naive":
        item["forgotten_at"] = datetime(2026, 1, 1)
    elif fault == "revision":
        item["forgotten_revision"] = True
    elif fault == "revision_cap":
        item["forgotten_revision"] = 102
    elif fault == "party_revision":
        item.update(kind="party", forgotten_revision=4)
    else:
        items = [dict(item, id=uuid4()) for _ in range(26)]
    with pytest.raises(ValidationError):
        manifest(items=items)


@pytest.mark.parametrize(
    "changes",
    [
        {"database": "unsafe;drop"},
        {"issued_at": datetime(2026, 1, 1)},
        {"decision": "reconcile_restored_suppressions"},
        {"reviewed_hash": "a" * 64},
        {"decision": "export", "issued_at": datetime.now(UTC)},
        {"decision": "other"},
    ],
)
def test_request_requires_explicit_current_review(changes):
    values = {"workspace_id": uuid4(), "operator_id": uuid4(), "database": "butler_test_restore"}
    values.update(changes)
    with pytest.raises(ValidationError):
        Request(**values)


def test_mid_read_metadata_change_fails_closed(tmp_path, monkeypatch):
    from types import SimpleNamespace

    path = tmp_path / "manifest.json"
    files.write_file(path, manifest())
    original = os.fstat
    calls = 0

    def changed(fd):
        nonlocal calls
        calls += 1
        value = original(fd)
        if calls == 2:
            return SimpleNamespace(
                st_size=value.st_size + 1,
                st_mtime_ns=value.st_mtime_ns,
                st_ctime_ns=value.st_ctime_ns,
            )
        return value

    monkeypatch.setattr(files.os, "fstat", changed)
    with pytest.raises(ValueError, match="changed"):
        files.read_file(path)
