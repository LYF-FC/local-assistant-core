"""Spec 075 first slice: synthetic immutable-byte handoff, never restore activation."""

import hashlib
import os
import stat
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from recovery_set_support import (
    file_access_guards,
    make_key,
    make_set,
    private_dir,
    run_generate,
)

from app import recovery_staging as staging
from app.recovery_set.fsset import OpenSet
from app.recovery_set.verify import verifier_chain


@pytest.fixture
def case(tmp_path):
    payload = b"synthetic dump bytes, not household records"
    source = make_set(tmp_path / "source", archive=False, dump=payload)
    key = make_key(tmp_path / "keys")
    manifest = private_dir(tmp_path / "manifests") / "manifest.json"
    result, status = run_generate(source, key, manifest)
    assert status == 0
    scratch = private_dir(tmp_path / "scratch")
    expected = staging.StagingExpectations(
        key.installation_id,
        verifier_chain()[-1],
        key.path,
        key.fingerprint(),
        result["manifest_hash"],
    )
    return SimpleNamespace(
        payload=payload,
        source=source,
        key=key,
        manifest=manifest,
        scratch=scratch,
        expected=expected,
    )


def stage(case, **changes):
    return staging.stage_synthetic_dump(
        changes.get("source_set", case.source.set_dir),
        changes.get("manifest_path", case.manifest),
        changes.get("scratch_parent", case.scratch),
        changes.get("expectations", case.expected),
    )


def test_verified_stage_is_private_removed_and_handoff_uses_exact_immutable_bytes(
    case, monkeypatch
):
    original_verify = staging.verify
    inspected = []

    def inspect(trust, **kwargs):
        root = Path(trust["set"]).parent
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE(Path(trust["set"]).stat().st_mode) == 0o700
        assert stat.S_IMODE((Path(trust["set"]) / "database.dump").stat().st_mode) == 0o600
        assert stat.S_IMODE(Path(trust["manifest"]).stat().st_mode) == 0o600
        assert trust["require_freshness"] is True
        assert trust["expected_manifest_hash"] == case.expected.expected_manifest_hash
        assert trust["expect_archive"] == "absent"
        assert Path(trust["key"]) == case.key.path
        assert not (root / "recovery.key").exists()
        inspected.append(root)
        return original_verify(trust, **kwargs)

    monkeypatch.setattr(staging, "verify", inspect)
    result = stage(case)
    assert len(inspected) == 1 and not inspected[0].exists()
    assert list(case.scratch.iterdir()) == []
    assert result.dump_bytes == case.payload and type(result.dump_bytes) is bytes
    assert result.dump_sha256 == hashlib.sha256(case.payload).hexdigest()
    assert result.manifest_hash == case.expected.expected_manifest_hash
    assert result.installation_id == case.key.installation_id
    assert result.schema_head == case.expected.schema_head
    assert result.quarantined is True and result.restore_eligible is False
    supplied = []
    consumed = result.consume(lambda data: supplied.append(data) or {"restore_eligible": True})
    assert supplied == [case.payload] and supplied[0] is result.dump_bytes
    assert consumed.consumer_result == {"restore_eligible": True}
    assert consumed.quarantined is True and consumed.restore_eligible is False
    with pytest.raises(FrozenInstanceError):
        result.dump_bytes = b"replacement"
    assert case.key.material not in repr(result) + repr(case.expected) + repr(consumed)
    assert case.payload.decode() not in repr(result)
    assert str(case.key.path) not in repr(case.expected)


@pytest.mark.parametrize(
    "changes",
    [
        {"environment": "production"},
        {"installation_id": "bad"},
        {"schema_head": "../head"},
        {"expected_manifest_hash": None},
        {"expected_manifest_hash": "F" * 64},
        {"key_fingerprint": "short"},
        {"key_path": "\x00"},
    ],
)
def test_invalid_scope_and_trust_make_no_filesystem_calls(case, changes):
    expected = replace(case.expected, **changes)
    with (
        file_access_guards(raising=False) as (counts, _, _),
        pytest.raises(staging.StagingError) as error,
    ):
        stage(case, expectations=expected)
    assert dict(counts) == {}
    assert error.value.code in {"staging_scope_required", "staging_trust_invalid"}
    assert list(case.scratch.iterdir()) == []


@pytest.mark.parametrize("alias", [False, True])
def test_scratch_inside_source_is_rejected_before_any_directory_creation(case, monkeypatch, alias):
    parent = case.source.set_dir
    if alias:
        parent = case.scratch / "alias"
        parent.symlink_to(case.source.set_dir, target_is_directory=True)
    mkdir = []
    monkeypatch.setattr(staging.os, "mkdir", lambda *a, **k: mkdir.append(a))
    before = (case.source.set_dir / "database.dump").read_bytes()
    with pytest.raises(staging.StagingError, match="staging_trust_invalid"):
        stage(case, scratch_parent=parent)
    assert mkdir == []
    assert (case.source.set_dir / "database.dump").read_bytes() == before
    assert sorted(path.name for path in case.source.set_dir.iterdir()) == ["database.dump"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("expected_manifest_hash", "0" * 64, "freshness_expected_hash_mismatch"),
        ("key_fingerprint", "0" * 64, "key_fingerprint_mismatch"),
        ("schema_head", "different_head", "schema_head_mismatch"),
        ("installation_id", "00000000-0000-4000-8000-000000000001", "installation_mismatch"),
    ],
)
def test_trusted_expectation_mismatch_fails_closed_and_discards_stage(case, field, value, reason):
    with pytest.raises(staging.StagingError) as error:
        stage(case, expectations=replace(case.expected, **{field: value}))
    assert error.value.code == "staging_verification_failed"
    assert reason in error.value.verification_reasons
    assert list(case.scratch.iterdir()) == []


def test_tampered_source_cannot_be_legitimized_by_copying_private_modes(case):
    (case.source.set_dir / "database.dump").write_bytes(b"tampered source")
    with pytest.raises(staging.StagingError) as error:
        stage(case)
    assert error.value.code == "staging_verification_failed"
    assert error.value.verification_reasons == ("set_member_size_mismatch",)
    assert list(case.scratch.iterdir()) == []


@pytest.mark.parametrize("unsafe", ["mode", "hardlink", "symlink", "extra"])
def test_unsafe_source_is_not_sanitized_into_an_acceptable_copy(case, unsafe):
    dump = case.source.set_dir / "database.dump"
    if unsafe == "mode":
        dump.chmod(0o644)
    elif unsafe == "hardlink":
        os.link(dump, case.scratch / "other")
    elif unsafe == "symlink":
        saved = case.scratch / "outside"
        dump.rename(saved)
        dump.symlink_to(saved)
    else:
        (case.source.set_dir / "extra").write_bytes(b"unexpected")
    with pytest.raises(staging.StagingError, match="staging_source_rejected"):
        stage(case)
    assert not list(case.scratch.glob("spec075-*"))


def test_source_changed_between_metadata_scan_and_copy_is_rejected(case, monkeypatch):
    original = OpenSet.hash_member

    def change(handle, found, **kwargs):
        (case.source.set_dir / "database.dump").write_bytes(b"changed during copy")
        return original(handle, found, **kwargs)

    monkeypatch.setattr(OpenSet, "hash_member", change)
    with pytest.raises(staging.StagingError) as error:
        stage(case)
    assert error.value.verification_reasons == ("set_changed_during_read",)
    assert list(case.scratch.iterdir()) == []


def test_dump_above_small_slice_cap_is_rejected_before_content_copy(case, monkeypatch):
    monkeypatch.setattr(staging, "MAX_DUMP_BYTES", len(case.payload) - 1)
    monkeypatch.setattr(
        OpenSet, "hash_member", lambda *a, **k: pytest.fail("must not read content")
    )
    with pytest.raises(staging.StagingError) as error:
        stage(case)
    assert error.value.verification_reasons == ("set_size_limit_exceeded",)
    assert list(case.scratch.iterdir()) == []


def test_archive_present_source_is_refused_not_silently_omitted(case):
    archive = private_dir(case.source.set_dir / "archive")
    (archive / ".archive.lock").write_bytes(b"")
    with pytest.raises(staging.StagingError, match="staging_archive_unsupported"):
        stage(case)
    assert list(case.scratch.iterdir()) == []


def test_manifest_symlink_and_alias_are_refused(case):
    alias = case.scratch / "manifest-alias"
    alias.symlink_to(case.manifest)
    with pytest.raises(staging.StagingError) as error:
        stage(case, manifest_path=alias)
    assert error.value.verification_reasons == ("manifest_file_unsafe",)
    alias.unlink()
    os.link(case.manifest, alias)
    with pytest.raises(staging.StagingError) as error:
        stage(case, manifest_path=alias)
    assert error.value.verification_reasons == ("manifest_file_unsafe",)


def test_staged_dump_changed_after_verification_before_snapshot_is_rejected(case, monkeypatch):
    original = staging.verify

    def change(trust, **kwargs):
        report = original(trust, **kwargs)
        assert report.exit_status() == 0
        (Path(trust["set"]) / "database.dump").write_bytes(b"changed after verification")
        return report

    monkeypatch.setattr(staging, "verify", change)
    with pytest.raises(staging.StagingError, match="staging_bytes_changed"):
        stage(case)
    assert list(case.scratch.iterdir()) == []


def test_staged_symlink_replacement_before_snapshot_never_reads_outside(case, monkeypatch):
    outside = case.scratch / "outside"
    outside.write_bytes(b"outside must not be consumed")
    identity = outside.stat()
    original_verify, original_read = staging.verify, staging.os.read

    def replace_after_verify(trust, **kwargs):
        report = original_verify(trust, **kwargs)
        assert report.exit_status() == 0
        dump = Path(trust["set"]) / "database.dump"
        dump.unlink()
        dump.symlink_to(outside)
        return report

    def refuse_outside_read(descriptor, amount):
        info = os.fstat(descriptor)
        assert (info.st_ino, info.st_dev) != (identity.st_ino, identity.st_dev)
        return original_read(descriptor, amount)

    monkeypatch.setattr(staging, "verify", replace_after_verify)
    monkeypatch.setattr(staging.os, "read", refuse_outside_read)
    with pytest.raises(staging.StagingError) as error:
        stage(case)
    assert error.value.verification_reasons == ("set_changed_during_read",)
    assert outside.read_bytes() == b"outside must not be consumed"
    assert not list(case.scratch.glob("spec075-*"))


@pytest.mark.parametrize("unsafe", ["mode", "symlink-ancestor"])
def test_unsafe_scratch_parent_creates_no_stage_or_outside_writes(case, unsafe):
    parent = case.scratch
    if unsafe == "mode":
        parent.chmod(0o755)
    else:
        real = private_dir(case.scratch / "real")
        nested = private_dir(real / "nested")
        alias = case.scratch / "alias"
        alias.symlink_to(real, target_is_directory=True)
        parent = alias / "nested"
    with pytest.raises(staging.StagingError):
        stage(case, scratch_parent=parent)
    assert (case.source.set_dir / "database.dump").read_bytes() == case.payload
    assert not list(case.scratch.glob("spec075-*"))
    if unsafe == "symlink-ancestor":
        assert list(nested.iterdir()) == []


def test_source_replacement_after_snapshot_cannot_change_consumer_bytes(case):
    result = stage(case)
    dump = case.source.set_dir / "database.dump"
    dump.unlink()
    dump.write_bytes(b"replacement after snapshot")
    supplied = result.consume(lambda data: data)
    assert supplied.consumer_result is result.dump_bytes
    assert supplied.consumer_result == case.payload
    assert supplied.quarantined is True and supplied.restore_eligible is False


def test_disk_stage_mutation_after_snapshot_does_not_change_handoff(case, monkeypatch):
    original = staging.read_protected_file

    def read_then_change(path, **kwargs):
        data = original(path, **kwargs)
        if Path(path).name == "database.dump":
            Path(path).write_bytes(b"changed after snapshot")
        return data

    monkeypatch.setattr(staging, "read_protected_file", read_then_change)
    result = stage(case)
    assert result.consume(lambda data: data).consumer_result == case.payload


@pytest.mark.parametrize(
    "change", ["missing", "digest", "manifest", "member_count", "member_bytes"]
)
def test_missing_or_malformed_verified_references_cannot_release_bytes(case, monkeypatch, change):
    original = staging.verify

    def malformed(trust, **kwargs):
        result = original(trust, **kwargs)
        assert result.exit_status() == 0
        if change == "missing":
            del result.extras["verified_references"]
        elif change == "digest":
            result.extras["verified_references"]["dump_sha256"] = "not-a-digest"
        elif change == "manifest":
            result.extras["verified_references"]["manifest_hash"] = "0" * 64
        elif change == "member_count":
            result.extras["member_count"] = 2
        else:
            result.extras["member_bytes"] = True
        return result

    monkeypatch.setattr(staging, "verify", malformed)
    with pytest.raises(staging.StagingError, match="staging_verification_failed"):
        stage(case)
    assert list(case.scratch.iterdir()) == []


def test_cleanup_failure_prevents_handoff_and_retains_private_artifacts(case, monkeypatch):
    original = staging.os.unlink

    def fail(name, **kwargs):
        if name == "manifest.json":
            raise PermissionError("synthetic cleanup failure")
        return original(name, **kwargs)

    monkeypatch.setattr(staging.os, "unlink", fail)
    with pytest.raises(staging.StagingError, match="staging_cleanup_failed"):
        stage(case)
    [leftover] = case.scratch.iterdir()
    assert stat.S_IMODE(leftover.stat().st_mode) == 0o700
    assert (leftover / "manifest.json").exists()


@pytest.mark.parametrize("change", ["truncated", "extra", "same-length"])
def test_forged_snapshot_never_reaches_consumer(case, change):
    result = stage(case)
    supplied = []
    forged = {
        "truncated": case.payload[:-1],
        "extra": case.payload + b"extra",
        "same-length": b"X" + case.payload[1:],
    }[change]
    with pytest.raises(staging.StagingError, match="staging_bytes_changed"):
        replace(result, dump_bytes=forged).consume(supplied.append)
    assert supplied == []


def test_mutation_while_consumer_runs_fails_the_post_consumption_digest_gate(case):
    result = stage(case)

    def change(data):
        assert data == case.payload
        object.__setattr__(result, "dump_bytes", b"changed while consumer ran")

    with pytest.raises(staging.StagingError, match="staging_bytes_changed"):
        result.consume(change)


def test_consumer_exception_returns_no_promoted_result_and_stage_is_already_clean(case):
    result = stage(case)

    def fail(data):
        assert data == case.payload
        assert list(case.scratch.iterdir()) == []
        raise RuntimeError("synthetic consumer failed")

    with pytest.raises(RuntimeError, match="synthetic consumer failed"):
        result.consume(fail)
    assert result.quarantined is True and result.restore_eligible is False
    assert list(case.scratch.iterdir()) == []


def test_unexpected_programming_fault_is_not_disguised_as_verification_failure(case, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic programming defect")

    monkeypatch.setattr(staging, "verify", broken)
    with pytest.raises(RuntimeError, match="synthetic programming defect"):
        stage(case)
    assert list(case.scratch.iterdir()) == []
