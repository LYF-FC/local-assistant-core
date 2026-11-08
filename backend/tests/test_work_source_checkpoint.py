"""Purpose separation, independently pinned inputs and no-DB offline verification."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app import work_source_checkpoint as recovery
from app import work_source_checkpoint_file as files
from app import work_suppression_auth as auth
from app.config import settings
from app.work_suppression_file import canonical


def manifest(workspace, **changes):
    body = files.Body(
        **(
            {
                "export_id": uuid4(),
                "workspace_id": workspace,
                "exported_by": uuid4(),
                "source_database_oid": 1,
                "generated_at": datetime.now(UTC),
                "items": (
                    {
                        "source_id": uuid4(),
                        "receipt_id": uuid4(),
                        "withdrawn_at": datetime.now(UTC) - timedelta(minutes=1),
                    },
                ),
            }
            | changes
        )
    )
    return files.Manifest(body=body, digest=files.digest(body))


def setup(tmp_path):
    workspace = uuid4()
    key = auth.generate_key(workspace)
    key_path, path = tmp_path / "key.json", tmp_path / "sources.json"
    auth.write_key(key_path, key)
    value = manifest(workspace)
    files.write_signed(path, value, key)
    return workspace, key, key_path, path, value


def test_roundtrip_and_distinct_purpose_authentication(tmp_path):
    workspace, key, _, path, value = setup(tmp_path)
    assert files.read_signed(path, key, workspace) == value
    assert key.material.get_secret_value() not in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        files.write_signed(path, value, key)
    with pytest.raises(ValueError):
        auth.read_signed(path, key, workspace)
    raw = files.sign(value, key).model_dump(mode="json")
    raw["mac"] = auth._tag(key, auth.MANIFEST_DOMAIN, {k: v for k, v in raw.items() if k != "mac"})
    path.write_bytes(canonical(raw))
    with pytest.raises(ValueError, match="authentication"):
        files.read_signed(path, key, workspace)


@pytest.mark.parametrize(
    "fault",
    [
        "digest",
        "mac",
        "purpose",
        "algorithm",
        "key_id",
        "pin",
        "workspace",
        "key",
        "unsigned",
        "header",
        "boolean",
        "body_header",
        "extra",
        "public",
        "symlink",
        "hardlink",
        "duplicate",
        "oversize",
    ],
)
def test_untrusted_or_substituted_file_refused(tmp_path, fault):
    workspace, key, _, path, value = setup(tmp_path)
    raw = json.loads(path.read_text())
    if fault == "digest":
        changed = value.body.model_copy(update={"export_id": uuid4()})
        raw["manifest"] = files.Manifest(body=changed, digest=files.digest(changed)).model_dump(
            mode="json"
        )
    elif fault == "mac":
        raw["mac"] = "0" * 64
    elif fault == "purpose":
        raw["mode"] = "synthetic_work_authenticated_suppression"
    elif fault == "algorithm":
        raw["algorithm"] = "sha256"
    elif fault == "key_id":
        raw["key_id"] = str(uuid4())
    elif fault == "pin":
        raw["key_fingerprint"] = "0" * 64
    elif fault == "workspace":
        workspace = uuid4()
    elif fault == "key":
        key = auth.generate_key(workspace)
    elif fault == "unsigned":
        raw = value.model_dump(mode="json")
    elif fault == "header":
        del raw["schema_version"]
    elif fault == "boolean":
        raw["schema_version"] = True
    elif fault == "body_header":
        del raw["manifest"]["body"]["schema_version"]
    elif fault == "extra":
        raw["extra"] = "ignored"
    elif fault == "public":
        path.chmod(0o640)
    elif fault == "symlink":
        link = tmp_path / "alias"
        link.symlink_to(path)
        path = link
    elif fault == "hardlink":
        os.link(path, tmp_path / "alias")
    elif fault == "duplicate":
        path.write_bytes(b'{"schema_version":1,"schema_version":1}')
    elif fault == "oversize":
        path.write_bytes(b" " * 32769)
    if fault not in {"public", "symlink", "hardlink", "duplicate", "oversize"}:
        path.write_bytes(canonical(raw))
    with pytest.raises((ValueError, OSError)):
        files.read_signed(path, key, workspace)


@pytest.mark.parametrize("expected", [None, "", "0" * 64, "e" * 63, "é" * 64, True])
def test_explicit_independent_checkpoint_required(expected):
    with pytest.raises(ValueError):
        files.require_checkpoint(manifest(uuid4()), expected)


def test_authentic_older_same_key_file_is_not_the_known_newer_checkpoint(tmp_path):
    workspace, key, _, old_path, old = setup(tmp_path)
    newer = manifest(workspace)
    loaded = files.read_signed(old_path, key, workspace)
    assert loaded == old
    with pytest.raises(ValueError):
        files.require_checkpoint(loaded, newer.digest)
    assert files.require_checkpoint(loaded, old.digest)["manifest_hash"] == old.digest
    assert not files.checkpoint(loaded, key)["latest_completeness_verified"]


def test_offline_cli_needs_no_database_configuration(tmp_path):
    workspace, key, key_path, path, value = setup(tmp_path)
    env = {k: v for k, v in os.environ.items() if not k.startswith("BUTLER_")}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.work_source_checkpoint_file",
            "verify",
            "--workspace",
            str(workspace),
            "--recovery-key",
            str(key_path),
            "--expected-key-fingerprint",
            auth.fingerprint(key),
            "--manifest",
            str(path),
            "--expected-manifest-hash",
            value.digest,
        ],
        check=False,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["checkpoint"]["manifest_hash"] == value.digest and not report["recovery_complete"]
    assert key.material.get_secret_value() not in result.stdout and "mac" not in report


@pytest.mark.parametrize(
    "fault",
    [
        "pin",
        "hash",
        "same_key_older",
        "mac",
        "unsigned",
        "purpose",
        "partial",
        "key_namespace",
        "selection_override",
    ],
)
def test_cli_fails_untrusted_evidence_before_database_connection(
    tmp_path, monkeypatch, capsys, fault
):
    workspace, key, key_path, path, value = setup(tmp_path)
    monkeypatch.setattr(settings, "env", "test")
    monkeypatch.setattr(settings, "postgres_db", "butler_test")
    called = []

    def forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError("Untrusted input reached database")

    monkeypatch.setattr(recovery.psycopg, "connect", forbidden)
    pin, expected = auth.fingerprint(key), value.digest
    if fault == "pin":
        pin = "0" * 64
    if fault == "hash":
        expected = "0" * 64
    if fault == "same_key_older":
        expected = manifest(workspace).digest
    if fault in {"mac", "unsigned", "purpose"}:
        raw = json.loads(path.read_text())
        if fault == "mac":
            raw["mac"] = "0" * 64
        elif fault == "unsigned":
            raw = value.model_dump(mode="json")
        else:
            raw["mode"] = "synthetic_work_authenticated_suppression"
        path.write_bytes(canonical(raw))
    if fault == "key_namespace":
        workspace = uuid4()
    argv = [
        "checkpoint",
        "preview",
        "--environment",
        "test",
        "--database",
        "butler_test",
        "--operator",
        str(uuid4()),
        "--workspace",
        str(workspace),
        "--recovery-key",
        str(key_path),
        "--expected-key-fingerprint",
        pin,
        "--manifest",
        str(path),
    ]
    if fault != "partial":
        argv.extend(["--expected-manifest-hash", expected])
    if fault == "selection_override":
        argv.extend(["--source", str(uuid4())])
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        recovery.main()
    assert not called
    assert key.material.get_secret_value() not in capsys.readouterr().err


@pytest.mark.parametrize(
    "changes",
    [
        {"source_ids": ()},
        {"source_ids": (uuid4(),), "expected_manifest_hash": "a" * 64},
        {"issued_at": datetime.now(UTC)},
        {"reviewed_hash": "a" * 64},
    ],
)
def test_export_contract_refuses_target_authority(changes):
    with pytest.raises(ValueError):
        recovery.Request(
            database="butler_test",
            workspace_id=uuid4(),
            operator_id=uuid4(),
            auth_key_id=uuid4(),
            auth_key_fingerprint="a" * 64,
            decision="export",
            **changes,
        )


@pytest.mark.parametrize(
    "fault", ["empty", "duplicate", "order", "capacity", "future", "oid", "digest"]
)
def test_source_manifest_contracts(fault):
    workspace = uuid4()
    value = manifest(workspace)
    item = value.body.items[0]
    changes = {}
    if fault == "empty":
        changes["items"] = ()
    if fault == "duplicate":
        changes["items"] = (item, item)
    if fault == "order":
        changes["items"] = tuple(
            sorted(
                [item, item.model_copy(update={"source_id": uuid4()})],
                key=lambda x: x.source_id,
                reverse=True,
            )
        )
    if fault == "capacity":
        changes["items"] = tuple(item.model_copy(update={"source_id": uuid4()}) for _ in range(11))
    if fault == "future":
        changes["items"] = (
            item.model_copy(update={"withdrawn_at": datetime.now(UTC) + timedelta(hours=1)}),
        )
    if fault == "oid":
        changes["source_database_oid"] = True
    with pytest.raises(ValueError):
        if fault == "digest":
            files.Manifest(body=value.body, digest="0" * 64)
        else:
            files.Body(**(value.body.model_dump() | changes))
