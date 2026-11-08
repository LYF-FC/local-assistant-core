"""Synthetic local archive faults: actual private files, never an owner directory."""

import os
from uuid import uuid4

import pytest

from app import document_archive as storage


def test_exact_durable_idempotent_bytes_and_private_objects(archive_root):
    doc = uuid4()
    data = b"\xef\xbb\xbfSynthetic\r\n" + "é😀".encode()
    with storage.opened(archive_root) as archive:
        archive.put(doc, 1, data)
        archive.put(doc, 1, data)
        assert archive.read(doc, 1) == data
        assert len(archive.entries()) == 3
    with storage.opened(archive_root) as archive:
        assert archive.read(doc, 1) == data
        archive.purge(doc)
        assert len(archive.entries()) == 2
        archive.purge(doc)


def test_corruption_never_overwritten(archive_root):
    doc = uuid4()
    with storage.opened(archive_root) as archive:
        archive.put(doc, 1, b"Synthetic one")
        with pytest.raises(storage.ArchiveError):
            archive.put(doc, 1, b"Synthetic changed")
        assert archive.read(doc, 1) == b"Synthetic one"


def test_full_capacity_still_permits_forgetting(archive_root, monkeypatch):
    monkeypatch.setattr(storage, "MAX_BYTES", 3)
    doc = uuid4()
    with storage.opened(archive_root) as archive:
        archive.put(doc, 1, b"abc")
        archive.put(doc, 1, b"abc")
        with pytest.raises(storage.ArchiveError):
            archive.put(doc, 2, b"x")
        archive.purge(doc)
        archive.put(doc, 1, b"new")


@pytest.mark.parametrize("bad", [b"", b"x" * 131073, "text"])
def test_bounded_original(archive_root, bad):
    with storage.opened(archive_root) as archive, pytest.raises(storage.ArchiveError):
        archive.put(uuid4(), 1, bad)


@pytest.mark.parametrize("revision", [0, 51, True, "../escape"])
def test_generated_keys_only(archive_root, revision):
    with storage.opened(archive_root) as archive, pytest.raises(storage.ArchiveError):
        archive.put(uuid4(), revision, b"x")


def test_initialization_refuses_existing_content_or_reinitialization(archive_root, tmp_path):
    with pytest.raises(storage.ArchiveError):
        storage.initialize(archive_root)
    occupied = tmp_path / "occupied"
    occupied.mkdir(mode=0o700)
    (occupied / "synthetic.txt").write_text("Keep")
    with pytest.raises(storage.ArchiveError):
        storage.initialize(occupied)
    assert (occupied / "synthetic.txt").read_text() == "Keep"


def test_symlink_component_root_and_blob_and_hardlink_refused(archive_root, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(archive_root, target_is_directory=True)
    with pytest.raises(storage.ArchiveError), storage.opened(alias):
        pass
    doc = uuid4()
    outside = tmp_path / "outside"
    outside.write_bytes(b"Synthetic")
    outside.chmod(0o600)
    target = archive_root / storage.Archive.key(doc, 1)
    target.symlink_to(outside)
    with pytest.raises(storage.ArchiveError), storage.opened(archive_root):
        pass
    target.unlink()
    os.link(outside, target)
    with pytest.raises(storage.ArchiveError), storage.opened(archive_root):
        pass
    assert outside.read_bytes() == b"Synthetic"


def test_world_readable_root_and_unknown_entries_refused(archive_root):
    archive_root.chmod(0o755)
    with pytest.raises(storage.ArchiveError), storage.opened(archive_root):
        pass
    archive_root.chmod(0o700)
    (archive_root / "unknown").write_bytes(b"Synthetic")
    with pytest.raises(storage.ArchiveError), storage.opened(archive_root):
        pass


def test_root_identity_lock_and_entry_bounds(archive_root, monkeypatch):
    with pytest.raises(storage.ArchiveError), storage.opened(archive_root, uuid4()):
        pass
    with (
        storage.opened(archive_root),
        pytest.raises(storage.ArchiveError),
        storage.opened(archive_root),
    ):
        pass
    monkeypatch.setattr(storage, "MAX_ENTRIES", 2)
    with storage.opened(archive_root) as archive, pytest.raises(storage.ArchiveError):
        archive.put(uuid4(), 1, b"x")


def test_interrupted_write_keeps_bounded_temporary_then_retry(archive_root, monkeypatch):
    doc = uuid4()
    real = storage.write_all

    def stop(fd, data):
        os.write(fd, data[:2])
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(storage, "write_all", stop)
    with pytest.raises(storage.ArchiveError), storage.opened(archive_root) as archive:
        archive.put(doc, 1, b"Synthetic")
    assert len(list(archive_root.glob(".pending-*"))) == 1
    monkeypatch.setattr(storage, "write_all", real)
    with storage.opened(archive_root) as archive:
        archive.discard_pending(doc)
        archive.put(doc, 1, b"Synthetic")
        assert archive.read(doc, 1) == b"Synthetic"
    assert not list(archive_root.glob(".pending-*"))


def test_partial_delete_can_retry_without_touching_another_document(archive_root, monkeypatch):
    doc, other = uuid4(), uuid4()
    with storage.opened(archive_root) as archive:
        for i in [1, 2]:
            archive.put(doc, i, b"Synthetic")
        archive.put(other, 1, b"Other")
    unlink = storage.os.unlink
    count = 0

    def stop(name, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("Synthetic deletion failure")
        return unlink(name, **kwargs)

    monkeypatch.setattr(storage.os, "unlink", stop)
    with pytest.raises(storage.ArchiveError), storage.opened(archive_root) as archive:
        archive.purge(doc)
    monkeypatch.setattr(storage.os, "unlink", unlink)
    with storage.opened(archive_root) as archive:
        archive.purge(doc)
        assert archive.read(other, 1) == b"Other"
        assert len(archive.entries()) == 3


def test_crash_after_atomic_link_publication_is_retryable(archive_root, monkeypatch):
    doc = uuid4()
    unlink = storage.os.unlink

    def stop(name, **kwargs):
        if name.startswith(".pending-"):
            raise OSError("Synthetic crash after publish")
        return unlink(name, **kwargs)

    monkeypatch.setattr(storage.os, "unlink", stop)
    with pytest.raises(storage.ArchiveError), storage.opened(archive_root) as archive:
        archive.put(doc, 1, b"Synthetic")
    monkeypatch.setattr(storage.os, "unlink", unlink)
    with storage.opened(archive_root) as archive:
        archive.put(doc, 1, b"Synthetic")
        assert archive.read(doc, 1) == b"Synthetic"
    assert not list(archive_root.glob(".pending-*"))


@pytest.mark.parametrize(
    "marker",
    [
        b'{"schema_version":1,"root_id":123}',
        b'{"schema_version":true,"root_id":"bad"}',
        b"[]",
        b'{"schema_version":1,"root_id":"bad"}',
    ],
)
def test_malformed_root_marker_fails_closed(archive_root, marker):
    (archive_root / storage.MARKER).write_bytes(marker)
    with pytest.raises(storage.ArchiveError), storage.opened(archive_root):
        pass


def test_directory_sync_failure_never_claims_completion(archive_root, monkeypatch):
    doc = uuid4()
    sync = storage.os.fsync
    count = 0

    def fail(fd):
        nonlocal count
        count += 1
        if count == 3:
            raise OSError("Synthetic directory sync failure")
        return sync(fd)

    monkeypatch.setattr(storage.os, "fsync", fail)
    with pytest.raises(storage.ArchiveError), storage.opened(archive_root) as archive:
        archive.put(doc, 1, b"Synthetic")
    monkeypatch.setattr(storage.os, "fsync", sync)
    with storage.opened(archive_root) as archive:
        archive.put(doc, 1, b"Synthetic")
        assert archive.read(doc, 1) == b"Synthetic"
