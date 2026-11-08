"""Staged disposable recovery assessment; no activation or business-state changes."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID

import psycopg
from app.config import settings
from psycopg import sql

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
phase = sys.argv[1]
assert phase in {
    "source",
    "before",
    "after_work",
    "after_execution",
    "after_sessions",
    "container_before",
    "container_after",
}
workspace = UUID("a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1")
actor = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)


def invoke(module, *args):
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, "Synthetic assessment command failed"
    return json.loads(result.stdout)


def snapshot():
    tables = [
        ("public", name)
        for name in (
            "users",
            "auth_credentials",
            "auth_sessions",
            "user_scopes",
            "work_workspaces",
            "work_access_grants",
            "approvals",
            "durable_jobs",
            "job_outbox",
            "memory_records",
            "work_confirmation_requests",
        )
    ] + [
        ("work", name)
        for name in (
            "drafts",
            "parties",
            "capture_intents",
            "draft_reviews",
            "draft_revisions",
        )
    ]
    with psycopg.connect(url) as db:
        return {
            (schema, table): db.execute(
                sql.SQL("SELECT * FROM {}.{} ORDER BY 1,2").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            ).fetchall()
            for schema, table in tables
        }


def inspect(extra):
    before = snapshot()
    report = invoke(
        "app.recovery_assessment",
        "--environment",
        "test",
        "--restored-database",
        settings.postgres_db,
        "--operator",
        str(actor),
        "--workspace",
        str(workspace),
        "--scope",
        "household_shared",
        *extra,
    )
    assert snapshot() == before
    assert not report["activation_authorized"] and not report["recovery_complete"]
    assert "independent_latest_forgetting_coverage" in report["unverified_gates"]
    assert "full_host_offsite_and_owner_acceptance" in report["unverified_gates"]
    assert (
        not report["credentials"]["role_profile_verified"]
        and not report["credentials"]["credential_recovery_verified"]
    )
    assert len(report["execution"]["items"]) <= 25
    assert (
        not report["execution"]["has_more"] or len(report["execution"]["items"]) == 25
    )
    encoded = json.dumps(report)
    for hidden in (
        "payload_hash",
        "token_hash",
        "csrf_hash",
        "password_hash",
        "lease_hash",
        "idempotency_hash",
        "synthetic:old-backup-forget",
    ):
        assert hidden not in encoded
    with psycopg.connect(url) as db:
        assert (
            report["database_oid"]
            == db.execute(
                "SELECT oid FROM pg_database WHERE datname=current_database()"
            ).fetchone()[0]
        )
        assert (
            report["global_unrevoked_sessions"]
            == db.execute(
                "SELECT count(*) FROM public.auth_sessions WHERE revoked_at IS NULL"
            ).fetchone()[0]
        )
        metadata = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE id=%s",
            (report["report_id"],),
        ).fetchone()[0]
        assert (
            metadata["report_hash"] == report["report_hash"]
            and not metadata["activation_authorized"]
        )
    return report


if phase.startswith("container"):
    # Retain public anchors from trusted synthetic generation/export stdout, never candidate fields.
    with tempfile.TemporaryDirectory(prefix="synthetic-assessment-") as directory:
        key = Path(directory) / "key.json"
        manifest = Path(directory) / "manifest.json"
        generated = invoke(
            "app.work_suppression_auth",
            "generate",
            "--workspace",
            str(workspace),
            "--output",
            str(key),
        )
        exported = invoke(
            "app.work_suppression",
            "--environment",
            "test",
            "--database",
            settings.postgres_db,
            "--workspace",
            str(workspace),
            "--operator",
            str(actor),
            "--recovery-key",
            str(key),
            "--expected-key-fingerprint",
            generated["fingerprint"],
            "export",
            "--output",
            str(manifest),
        )
        report = inspect(
            [
                "--recovery-key",
                str(key),
                "--expected-key-fingerprint",
                generated["fingerprint"],
                "--manifest",
                str(manifest),
                "--expected-manifest-hash",
                exported["checkpoint"]["manifest_hash"],
            ]
        )
else:
    extra = (
        []
        if phase == "source"
        else [
            "--recovery-key",
            os.environ["BUTLER_SUPPRESSION_KEY_FILE"],
            "--expected-key-fingerprint",
            os.environ["BUTLER_SUPPRESSION_KEY_FINGERPRINT"],
            "--manifest",
            os.environ["BUTLER_SUPPRESSION_MANIFEST_FILE"],
            "--expected-manifest-hash",
            os.environ["BUTLER_SUPPRESSION_EXPECTED_HASH"],
        ]
    )
    report = inspect(extra)

if phase == "source":
    assert (
        report["work"]["enabled"]
        and report["work"]["grants"] == 1
        and report["work"]["pending_effects"] == 4
    )
    assert (
        not report["checkpoint"]["verified"]
        and "supply_independently_trusted_checkpoint" in report["required_actions"]
    )
else:
    assert report["checkpoint"]["verified"]
    if phase == "before":
        assert report["work"]["enabled"] and report["global_unrevoked_sessions"] > 0
        assert report["checkpoint"]["assessment"] == "requires_workspace_quarantine"
    else:
        assert not report["work"]["enabled"] and report["work"]["grants"] == 0
        assert report["work"]["pending_effects"] == 0
        assert report["checkpoint"]["assessment"] == "no_supplied_changes_observed"
        assert report["checkpoint"]["changes_required"] == 0
        # Earlier execution quarantine deliberately preserves an unselected queued control.
        assert report["execution"]["outstanding_jobs"] >= 1
        assert "review_selected_scope_execution" in report["required_actions"]
    if phase in {"after_sessions", "container_after"}:
        assert (
            report["global_unrevoked_sessions"] == 0
            and "revoke_global_sessions" not in report["required_actions"]
        )
    elif phase in {"before", "after_work", "after_execution"}:
        assert (
            report["global_unrevoked_sessions"] > 0
            and "revoke_global_sessions" in report["required_actions"]
        )
print(
    "Synthetic staged recovery assessment/checkpoint/inventory/non-mutation/unknown-gates verified; no payloads/secrets displayed"
)
