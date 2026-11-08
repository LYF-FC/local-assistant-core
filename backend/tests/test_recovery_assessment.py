"""Strict report target and scope; observations never authorize activation."""

import sys
from uuid import uuid4

import pytest

from app import recovery_assessment as assessment


def values():
    return {
        "restored_database": "butler_test_restore",
        "operator_id": uuid4(),
        "workspace_id": uuid4(),
        "scope_key": "household_shared",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"restored_database": ""},
        {"restored_database": "db;drop"},
        {"restored_database": "a" * 64},
        {"scope_key": "unknown"},
        {"workspace_id": "not-a-uuid"},
        {"extra": True},
    ],
)
def test_invalid_context(change):
    with pytest.raises(ValueError):
        assessment.Request(**(values() | change))


def test_known_context_and_explicit_unknown_gates():
    assert assessment.Request(**values()).scope_key == "household_shared"
    assert "independent_latest_forgetting_coverage" in assessment.UNVERIFIED
    assert "full_host_offsite_and_owner_acceptance" in assessment.UNVERIFIED


def test_cli_invalid_scope_never_connects(monkeypatch, capsys):
    monkeypatch.setattr(assessment, "validate_target", lambda _: None)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Invalid report reached database")

    monkeypatch.setattr(assessment.psycopg, "connect", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "assessment",
            "--environment",
            "test",
            "--restored-database",
            "butler_test",
            "--operator",
            str(uuid4()),
            "--workspace",
            str(uuid4()),
            "--scope",
            "unknown",
        ],
    )
    with pytest.raises(SystemExit) as error:
        assessment.main()
    assert error.value.code == 1 and not capsys.readouterr().out


@pytest.mark.parametrize("fault", ["partial", "pin", "checkpoint", "unsigned", "mac"])
def test_untrusted_cli_evidence_never_reaches_database(tmp_path, monkeypatch, capsys, fault):
    import json
    from datetime import UTC, datetime

    from app import work_suppression_auth as auth
    from app.work_suppression_file import Body, Manifest, digest

    request = values()
    workspace = request["workspace_id"]
    key = auth.generate_key(workspace)
    key_path = tmp_path / "key.json"
    path = tmp_path / "manifest.json"
    auth.write_key(key_path, key)
    body = Body(
        export_id=uuid4(),
        workspace_id=workspace,
        exported_by=request["operator_id"],
        source_database_oid=1,
        generated_at=datetime.now(UTC),
        items=(),
    )
    manifest = Manifest(body=body, digest=digest(body))
    auth.write_signed(path, manifest, key)
    if fault == "unsigned":
        path.write_text(manifest.model_dump_json())
    elif fault == "mac":
        raw = json.loads(path.read_text())
        raw["mac"] = "0" * 64
        path.write_text(json.dumps(raw))
    args = [
        "assessment",
        "--environment",
        "test",
        "--restored-database",
        "butler_test",
        "--operator",
        str(request["operator_id"]),
        "--workspace",
        str(workspace),
        "--scope",
        "household_shared",
        "--recovery-key",
        str(key_path),
    ]
    if fault != "partial":
        args += [
            "--expected-key-fingerprint",
            "0" * 64 if fault == "pin" else auth.fingerprint(key),
            "--manifest",
            str(path),
            "--expected-manifest-hash",
            "0" * 64 if fault == "checkpoint" else manifest.digest,
        ]
    monkeypatch.setattr(assessment, "validate_target", lambda _: None)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Untrusted evidence reached database")

    monkeypatch.setattr(assessment.psycopg, "connect", forbidden)
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as error:
        assessment.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert not output.out and key.material.get_secret_value() not in output.err
