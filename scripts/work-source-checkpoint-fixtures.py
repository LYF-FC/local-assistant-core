"""Newer authenticated source decisions, older target recovery and container CLI."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import psycopg
from psycopg.types.json import Jsonb

from app.config import settings
from app import work_suppression_auth as auth

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
phase = sys.argv[1]
assert phase in {"export", "recover", "container"}
url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)


def identifier(label):
    return uuid5(NAMESPACE_URL, "butler-synthetic-source-withdrawal-" + label)


workspace, actor, source = [identifier(label) for label in ("workspace", "actor", "source")]


def cli(module, args, success=True, offline=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("BUTLER_")} if offline else None
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env=env,
    )
    assert (result.returncode == 0) == success, "Synthetic authenticated source command failed"
    assert "synthetic:source-" not in result.stdout + result.stderr
    return json.loads(result.stdout) if success else None


def common():
    return [
        "--environment",
        "test",
        "--database",
        settings.postgres_db,
        "--operator",
        str(actor),
        "--workspace",
        str(workspace),
    ]


def export_files(key_path, old_path, new_path):
    key = auth.generate_key(workspace)
    auth.write_key(key_path, key)
    pin = auth.fingerprint(key)  # Trusted generation, never adopted from candidate files.
    base = [
        *common(),
        "--source",
        str(source),
        "--recovery-key",
        str(key_path),
        "--expected-key-fingerprint",
        pin,
    ]
    old = cli("app.work_source_checkpoint", ["export", *base, "--output", str(old_path)])
    new = cli("app.work_source_checkpoint", ["export", *base, "--output", str(new_path)])
    assert old["checkpoint"]["manifest_hash"] != new["checkpoint"]["manifest_hash"]
    assert (
        not new["checkpoint"]["latest_completeness_verified"]
        and not new["independent_retention_verified"]
    )
    assert key.material.get_secret_value() not in json.dumps(new)
    return {"key_fingerprint": pin, "manifest_hash": new["checkpoint"]["manifest_hash"]}


def recover(key_path, old_path, new_path, reference, expected_notes):
    trust = [
        "--workspace",
        str(workspace),
        "--recovery-key",
        str(key_path),
        "--expected-key-fingerprint",
        reference["key_fingerprint"],
        "--expected-manifest-hash",
        reference["manifest_hash"],
    ]
    cli(
        "app.work_source_checkpoint_file",
        ["verify", *trust, "--manifest", str(old_path)],
        success=False,
        offline=True,
    )
    cli(
        "app.work_source_checkpoint_file",
        ["verify", *trust, "--manifest", str(new_path)],
        offline=True,
    )
    target_trust = [
        "--recovery-key",
        str(key_path),
        "--expected-key-fingerprint",
        reference["key_fingerprint"],
        "--expected-manifest-hash",
        reference["manifest_hash"],
    ]
    with psycopg.connect(url) as db:
        before = db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (workspace, source),
        ).fetchone()
        assert before == (True,)
    cli(
        "app.work_source_checkpoint",
        ["preview", *common(), *target_trust, "--manifest", str(old_path)],
        success=False,
    )
    with psycopg.connect(url) as db:
        assert (
            db.execute(
                "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
                (workspace, source),
            ).fetchone()
            == before
        )
    base = [*common(), *target_trust, "--manifest", str(new_path)]
    plan = cli("app.work_source_checkpoint", ["preview", *base])
    assert (
        len(plan["withdrawal"]["notes"]) == expected_notes
        and len(plan["withdrawal"]["linked"]) == 1
    )
    assert "reviewed_hash" not in plan["withdrawal"]
    if expected_notes:
        assert plan["source_database_oid"] != plan["withdrawal"]["database_oid"]
        assert any(
            item["historical_reference"] and not item["current_reference"]
            for item in plan["withdrawal"]["notes"]
        )
    flags = [
        "--issued-at",
        plan["withdrawal"]["issued_at"],
        "--reviewed-hash",
        plan["reviewed_hash"],
        "--decision",
        "reapply_source_withdrawals",
    ]
    receipt = cli("app.work_source_checkpoint", ["apply", *base, *flags])
    assert (
        not receipt["recovery_complete"]
        and not receipt["activation_authorized"]
        and not receipt["latest_completeness_verified"]
    )
    cli("app.work_source_checkpoint", ["apply", *base, *flags], success=False)
    after = cli("app.work_source_checkpoint", ["preview", *base])
    assert not after["withdrawal"]["notes"] and not after["withdrawal"]["linked"]
    with psycopg.connect(url) as db:
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (workspace, source),
        ).fetchone() == (False,)
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s",
                (receipt["reconciliation_receipt_id"],),
            ).fetchone()[0]
            == receipt
        )
        assert db.execute(
            "SELECT state,payload IS NOT NULL FROM work.capture_intents WHERE id=%s",
            (identifier("control-capture"),),
        ).fetchone() == ("pending", True)
    return receipt


if phase == "export":
    reference = export_files(
        Path(os.environ["BUTLER_SOURCE_KEY_FILE"]),
        Path(os.environ["BUTLER_SOURCE_OLDER_FILE"]),
        Path(os.environ["BUTLER_SOURCE_MANIFEST_FILE"]),
    )
    print(json.dumps(reference))
elif phase == "recover":
    # The older dump still has an enabled workspace: explicitly run the existing reviewed quarantine.
    quarantine_args = [
        "--environment",
        "test",
        "--restored-database",
        settings.postgres_db,
        "--operator",
        str(actor),
        "--workspace",
        str(workspace),
    ]
    quarantine_plan = cli("app.work_restore", quarantine_args)
    cli(
        "app.work_restore",
        [
            *quarantine_args,
            "--issued-at",
            quarantine_plan["issued_at"],
            "--reviewed-hash",
            quarantine_plan["reviewed_hash"],
            "--decision",
            "quarantine_restored_workspace",
        ],
    )
    receipt = recover(
        Path(os.environ["BUTLER_SOURCE_KEY_FILE"]),
        Path(os.environ["BUTLER_SOURCE_OLDER_FILE"]),
        Path(os.environ["BUTLER_SOURCE_MANIFEST_FILE"]),
        {
            "key_fingerprint": os.environ["BUTLER_SOURCE_KEY_FINGERPRINT"],
            "manifest_hash": os.environ["BUTLER_SOURCE_EXPECTED_HASH"],
        },
        2,
    )
    print(
        "Authenticated newer source checkpoint/recovered key/older-file rejection/old-dump current-history-copy cleanup/dual receipt verified"
    )
else:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        primary, recovered = root / "primary-key.json", root / "recovered-key.json"
        old, new = root / "older.json", root / "newer.json"
        reference = export_files(primary, old, new)
        shutil.copyfile(primary, recovered)
        recovered.chmod(0o600)
        primary.unlink()
        # Simulate a revived source flag and unbound copied input without reviving terminal notes.
        # The separate logical job proves actual older-dump note/history reconciliation.
        command = uuid4()
        with psycopg.connect(url) as db:
            db.execute("UPDATE public.work_workspaces SET is_active=true WHERE id=%s", (workspace,))
            db.execute(
                "UPDATE work.source_registry SET is_active=true WHERE workspace_id=%s AND id=%s",
                (workspace, source),
            )
            payload = db.execute(
                "SELECT payload FROM work.capture_intents WHERE id=%s",
                (identifier("control-capture"),),
            ).fetchone()[0]
            payload["draft"]["source_ids"] = [str(source)]
            db.execute(
                "INSERT INTO work.capture_intents(id,workspace_id,actor_id,session_id,request_id,payload,expires_at) VALUES(%s,%s,%s,%s,%s,%s,now()+interval '4 minutes')",
                (command, workspace, actor, identifier("session"), uuid4(), Jsonb(payload)),
            )
            db.execute(
                "UPDATE public.work_workspaces SET is_active=false WHERE id=%s", (workspace,)
            )
        recover(recovered, old, new, reference, 0)
        with psycopg.connect(url) as db:
            assert db.execute(
                "SELECT state,payload,payload_hash FROM work.capture_intents WHERE id=%s",
                (command,),
            ).fetchone() == ("denied", None, None)
    print(
        "Non-root authenticated source export/offline verification/checkpoint-bound reapplication/copy redaction/dual receipt verified"
    )
