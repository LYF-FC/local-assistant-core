"""Authenticated metadata and independently pinned workspace key boundaries."""

import json
import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app import work_suppression as suppression
from app import work_suppression_auth as auth
from app.config import settings
from app.work_suppression_file import (
    Body,
    Manifest,
    canonical,
    digest,
    read_file,
    write_file,
    write_json_file,
)


def value(workspace):
    body = Body(
        export_id=uuid4(),
        workspace_id=workspace,
        exported_by=uuid4(),
        source_database_oid=1,
        generated_at=datetime.now(UTC),
        items=(),
    )
    return Manifest(body=body, digest=digest(body))


def setup(tmp_path):
    workspace = uuid4()
    key = auth.generate_key(workspace)
    key_path = tmp_path / "key.json"
    path = tmp_path / "manifest.json"
    auth.write_key(key_path, key)
    manifest = value(workspace)
    auth.write_signed(path, manifest, key)
    return workspace, key, key_path, path, manifest


def test_generation_roundtrip_pinned_identity_and_secret_masking(tmp_path):
    workspace, key, key_path, path, manifest = setup(tmp_path)
    seed = key.material.get_secret_value()
    assert seed not in repr(key) and seed not in key.model_dump_json()
    assert len(bytes.fromhex(seed)) == 32 and key_path.stat().st_mode & 0o777 == 0o600
    loaded = auth.load_key(key_path, auth.fingerprint(key), workspace)
    assert loaded == key and auth.read_signed(path, loaded, workspace) == manifest
    with pytest.raises(FileExistsError):
        auth.write_key(key_path, auth.generate_key(workspace))
    assert auth.load_key(key_path, auth.fingerprint(key), workspace) == key
    assert seed not in path.read_text()


@pytest.mark.parametrize(
    "fault",
    [
        "pin",
        "workspace",
        "key_id",
        "material",
        "date",
        "public",
        "symlink",
        "hardlink",
        "missing",
        "header",
        "oversize",
    ],
)
def test_bad_or_substituted_key_fails_pinned_load(tmp_path, fault):
    workspace, key, key_path, _, _ = setup(tmp_path)
    pin = auth.fingerprint(key)
    if fault == "pin":
        pin = "0" * 64
    elif fault == "workspace":
        workspace = uuid4()
    elif fault == "public":
        key_path.chmod(0o640)
    elif fault == "symlink":
        link = tmp_path / "link"
        link.symlink_to(key_path)
        key_path = link
    elif fault == "hardlink":
        os.link(key_path, tmp_path / "alias")
    elif fault == "missing":
        key_path.unlink()
    elif fault == "oversize":
        key_path.write_bytes(b" " * 2049)
    else:
        raw = json.loads(key_path.read_text())
        if fault == "key_id":
            raw["key_id"] = str(uuid4())
        elif fault == "material":
            raw["material"] = auth.generate_key(workspace).material.get_secret_value()
        elif fault == "date":
            raw["created_at"] = "2020-01-01T00:00:00Z"
        else:
            del raw["schema_version"]
        key_path.write_text(json.dumps(raw))
    with pytest.raises((ValueError, OSError)):
        auth.load_key(key_path, pin, workspace)


@pytest.mark.parametrize(
    "fault",
    [
        "recomputed_digest",
        "mac",
        "algorithm",
        "domain",
        "key_id",
        "fingerprint",
        "workspace",
        "legacy",
        "header",
        "extra",
        "rotation",
    ],
)
def test_authenticated_envelope_cannot_be_replaced_by_digest_or_other_key(tmp_path, fault):
    workspace, key, _, path, manifest = setup(tmp_path)
    raw = json.loads(path.read_text())
    if fault == "recomputed_digest":
        changed = value(workspace)
        raw["manifest"] = changed.model_dump(mode="json")
        assert changed.digest != manifest.digest
    elif fault == "mac":
        raw["mac"] = "0" * 64
    elif fault == "algorithm":
        raw["algorithm"] = "SHA256"
    elif fault == "domain":
        raw["mac"] = auth.fingerprint(key)
    elif fault == "key_id":
        raw["key_id"] = str(uuid4())
    elif fault == "fingerprint":
        raw["key_fingerprint"] = "0" * 64
    elif fault == "workspace":
        workspace = uuid4()
    elif fault == "legacy":
        raw = manifest.model_dump(mode="json")
    elif fault == "header":
        del raw["schema_version"]
    elif fault == "extra":
        raw["extra"] = True
    else:
        key = auth.generate_key(workspace)
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        auth.read_signed(path, key, workspace)


def test_namespace_bound_signing_and_explicit_legacy_inspection(tmp_path):
    workspace, key, _, _, manifest = setup(tmp_path)
    with pytest.raises(ValueError):
        auth.sign(manifest, auth.generate_key(uuid4()))
    legacy = tmp_path / "legacy.json"
    write_file(legacy, manifest)
    assert read_file(legacy) == manifest  # Privileged inspection is not authenticated CLI import.
    with pytest.raises(ValueError):
        auth.read_signed(legacy, key, workspace)


def test_offline_key_cli_outputs_public_anchor_only(tmp_path, monkeypatch, capsys):
    workspace = uuid4()
    path = tmp_path / "key.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["work_suppression_auth", "generate", "--workspace", str(workspace), "--output", str(path)],
    )
    auth.main()
    output = capsys.readouterr()
    result = json.loads(output.out)
    key = auth.load_key(path, result["fingerprint"], workspace)
    assert key.material.get_secret_value() not in output.out + output.err
    assert result["material_returned"] is False and result["independent_recovery_proven"] is False
    assert result["key_id"] == str(key.key_id)


@pytest.mark.parametrize(
    "fault",
    [
        "bad_pin",
        "tamper",
        "unsigned",
        "older",
        "missing_checkpoint",
        "bad_checkpoint",
        "export_checkpoint",
    ],
)
def test_cli_rejects_untrusted_inputs_before_database_connection(
    tmp_path, monkeypatch, capsys, fault
):
    workspace, key, key_path, path, manifest = setup(tmp_path)
    pin = auth.fingerprint(key)
    if fault == "bad_pin":
        pin = "0" * 64
    elif fault == "unsigned":
        path.write_text(canonical(manifest.model_dump(mode="json")).decode())
    elif fault == "older":
        # Both files are valid under the same pinned key; only checkpoint differs.
        path.unlink()
        auth.write_signed(path, value(workspace), key)
        assert auth.read_signed(path, key, workspace).digest != manifest.digest
    elif fault in {"missing_checkpoint", "bad_checkpoint", "export_checkpoint"}:
        pass
    else:
        raw = json.loads(path.read_text())
        raw["manifest"] = value(workspace).model_dump(mode="json")
        path.write_text(json.dumps(raw))
    monkeypatch.setattr(settings, "env", "test")
    monkeypatch.setattr(settings, "postgres_db", "butler_test")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Untrusted input reached database")

    monkeypatch.setattr(suppression.psycopg, "connect", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "work_suppression",
            "--environment",
            "test",
            "--database",
            "butler_test",
            "--workspace",
            str(workspace),
            "--operator",
            str(uuid4()),
            "--recovery-key",
            str(key_path),
            "--expected-key-fingerprint",
            pin,
            "--expected-manifest-hash",
            manifest.digest,
            "preview",
            "--manifest",
            str(path),
        ],
    )
    if fault == "export_checkpoint":
        sys.argv[-3:] = ["export", "--output", str(tmp_path / "export.json")]
    elif fault == "missing_checkpoint":
        index = sys.argv.index("--expected-manifest-hash")
        del sys.argv[index : index + 2]
    elif fault == "bad_checkpoint":
        sys.argv[sys.argv.index("--expected-manifest-hash") + 1] = "not-a-hash"
    with pytest.raises(SystemExit) as error:
        suppression.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert not output.out and key.material.get_secret_value() not in output.err


def test_key_model_and_writer_refuse_malformed_material(tmp_path):
    _workspace, key, _, _, _ = setup(tmp_path)
    raw = key.model_dump(mode="json")
    raw["material"] = "not-key-material"
    with pytest.raises(ValueError):
        auth.Key.model_validate(raw)
    with pytest.raises(TypeError):
        auth.write_key(tmp_path / "bad", {})
    with pytest.raises(ValueError):
        write_json_file(tmp_path / "too-large", {"padding": "x" * 3000}, max_bytes=2048)


@pytest.mark.parametrize("changes", [{"auth_key_id": uuid4()}, {"auth_key_fingerprint": "a" * 64}])
def test_partial_audit_authentication_reference_is_rejected(changes):
    with pytest.raises(ValueError):
        suppression.Request(
            workspace_id=uuid4(), operator_id=uuid4(), database="butler_test", **changes
        )


def test_offline_verification_cli_returns_no_key_or_mac(tmp_path, monkeypatch, capsys):
    workspace, key, key_path, path, manifest = setup(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "work_suppression_auth",
            "verify",
            "--workspace",
            str(workspace),
            "--recovery-key",
            str(key_path),
            "--expected-key-fingerprint",
            auth.fingerprint(key),
            "--expected-manifest-hash",
            manifest.digest,
            "--manifest",
            str(path),
        ],
    )
    auth.main()
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["manifest_hash"] == manifest.digest and result["recovery_complete"] is False
    assert key.material.get_secret_value() not in output.out + output.err
    assert "mac" not in result and not output.err


def test_self_consistent_replacement_pair_cannot_establish_its_own_anchor(tmp_path):
    workspace, original, _, _, _ = setup(tmp_path)
    attacker = auth.generate_key(workspace)
    attacker_key = tmp_path / "replacement-key.json"
    attacker_file = tmp_path / "replacement-manifest.json"
    auth.write_key(attacker_key, attacker)
    replacement = value(workspace)
    auth.write_signed(attacker_file, replacement, attacker)
    assert auth.read_signed(attacker_file, attacker, workspace) == replacement
    with pytest.raises(ValueError, match="trusted fingerprint"):
        auth.load_key(attacker_key, auth.fingerprint(original), workspace)


@pytest.mark.parametrize("expected", [None, "", "A" * 64, "0" * 64, "x" * 64, "a" * 63])
def test_checkpoint_requires_matching_explicit_hash(tmp_path, expected):
    workspace, key, _, path, manifest = setup(tmp_path)
    assert auth.read_signed(path, key, workspace) == manifest
    with pytest.raises(ValueError, match="checkpoint"):
        auth.require_checkpoint(manifest, expected)
    assert auth.require_checkpoint(manifest, manifest.digest)["manifest_hash"] == manifest.digest


def test_source_checkpoint_contains_only_public_metadata(tmp_path):
    workspace, key, _, _, manifest = setup(tmp_path)
    record = auth.checkpoint(manifest, key)
    assert set(record) == {
        "schema_version",
        "mode",
        "workspace_id",
        "export_id",
        "generated_at",
        "manifest_hash",
        "item_count",
        "authentication",
        "recovery_complete",
    }
    assert record["workspace_id"] == str(workspace)
    assert record["export_id"] == str(manifest.body.export_id)
    assert record["generated_at"] == manifest.body.generated_at.isoformat()
    assert record["manifest_hash"] == manifest.digest
    assert record["authentication"]["key_fingerprint"] == auth.fingerprint(key)
    assert key.material.get_secret_value() not in json.dumps(record)
    assert "mac" not in record and not record["recovery_complete"]
    with pytest.raises(ValueError, match="target checkpoint"):
        suppression.Request(
            workspace_id=workspace,
            operator_id=uuid4(),
            database="butler_test",
            decision="export",
            expected_manifest_hash=manifest.digest,
        )


@pytest.mark.parametrize("expected", [None, "bad", "0" * 64])
def test_offline_cli_rejects_missing_or_wrong_checkpoint(tmp_path, monkeypatch, capsys, expected):
    workspace, key, key_path, path, _ = setup(tmp_path)
    argv = [
        "work_suppression_auth",
        "verify",
        "--workspace",
        str(workspace),
        "--recovery-key",
        str(key_path),
        "--expected-key-fingerprint",
        auth.fingerprint(key),
        "--manifest",
        str(path),
    ]
    if expected is not None:
        argv += ["--expected-manifest-hash", expected]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as error:
        auth.main()
    assert error.value.code in {1, 2}
    assert not capsys.readouterr().out
