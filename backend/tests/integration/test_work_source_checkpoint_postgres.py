"""Receipt-backed exports and exact file-bound older-target source recovery."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from work_source_helpers import extra_notes, prepare, quarantine
from work_storage_helpers import connect, insert

from app import work_source_checkpoint as recovery
from app import work_source_checkpoint_file as files
from app import work_source_withdrawal as withdrawal
from app import work_suppression_auth as auth
from app.config import settings
from app.work_authority import REGISTRY_KEY

pytestmark = pytest.mark.integration


@pytest.fixture
def case(review_case):
    case = prepare(review_case)
    case["key"] = auth.generate_key(case["workspace"])
    body = files.Body(
        export_id=uuid4(),
        workspace_id=case["workspace"],
        exported_by=case["actor"],
        source_database_oid=1,
        generated_at=datetime.now(UTC) - timedelta(seconds=1),
        items=(
            {
                "source_id": case["source"],
                "receipt_id": uuid4(),
                "withdrawn_at": datetime.now(UTC) - timedelta(minutes=1),
            },
        ),
    )
    case["manifest"] = files.Manifest(body=body, digest=files.digest(body))
    quarantine(case)
    return case


def request(case, **changes):
    return recovery.Request(
        **(
            {
                "database": settings.postgres_db,
                "operator_id": case["actor"],
                "workspace_id": case["workspace"],
                "auth_key_id": case["key"].key_id,
                "auth_key_fingerprint": auth.fingerprint(case["key"]),
                "expected_manifest_hash": case["manifest"].digest,
            }
            | changes
        )
    )


def run(case, **changes):
    with connect() as db, db.transaction():
        return recovery.reconcile(db, request(case, **changes), case["manifest"])


def apply(case, plan, **changes):
    return run(
        case,
        **(
            {
                "decision": "reapply_source_withdrawals",
                "issued_at": datetime.fromisoformat(plan["withdrawal"]["issued_at"]),
                "reviewed_hash": plan["reviewed_hash"],
            }
            | changes
        ),
    )


def export(case, **changes):
    with connect() as db, db.transaction():
        return recovery.prepare(
            db,
            request(
                case,
                decision="export",
                source_ids=(case["source"],),
                expected_manifest_hash=None,
                **changes,
            ),
        )


def withdraw(case):
    base = {
        "database": settings.postgres_db,
        "operator_id": case["actor"],
        "workspace_id": case["workspace"],
        "source_ids": (case["source"],),
    }
    with connect() as db, db.transaction():
        plan = withdrawal.reconcile(db, withdrawal.Request(**base))
        return withdrawal.reconcile(
            db,
            withdrawal.Request(
                **base,
                decision="withdraw_sources",
                issued_at=datetime.fromisoformat(plan["issued_at"]),
                reviewed_hash=plan["reviewed_hash"],
            ),
        )


def test_export_requires_clean_committed_withdrawal_and_records_preparation_only(case):
    with pytest.raises(ValueError, match="Clean withdrawn"):
        export(case)
    receipt = withdraw(case)
    manifest = export(case)
    assert str(manifest.body.items[0].receipt_id) == receipt["receipt_id"]
    with connect() as db:
        source_time = db.execute(
            "SELECT occurred_at FROM public.audit_events WHERE id=%s", (receipt["receipt_id"],)
        ).fetchone()[0]
        assert manifest.body.items[0].withdrawn_at == source_time
        metadata = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE event_type='admin.work_source_checkpoint_prepared' AND entity_id=%s",
            (str(case["workspace"]),),
        ).fetchone()[0]
        assert metadata["manifest_hash"] == manifest.digest and not metadata["file_saved_verified"]
        assert not metadata["independent_retention_verified"]
    assert "synthetic:review-note" not in str(manifest)


def test_inactive_flag_without_receipt_cannot_be_exported(case):
    # An unused synthetic binding is clean/inactive but has never been withdrawn through the reviewed tool.
    with connect() as db:
        db.execute(
            "UPDATE public.work_workspaces SET is_active=true WHERE id=%s", (case["workspace"],)
        )
    source = insert(case["storage"])
    with connect() as db:
        db.execute(
            "INSERT INTO work.source_registry(workspace_id,id,is_active) VALUES(%s,%s,false)",
            (case["workspace"], source),
        )
    quarantine(case)
    with pytest.raises(ValueError, match="Committed source"), connect() as db, db.transaction():
        recovery.prepare(
            db, request(case, decision="export", source_ids=(source,), expected_manifest_hash=None)
        )


def test_file_bound_reapply_redacts_current_history_pending_and_commits_both_receipts(case):
    plan = run(case)
    assert "reviewed_hash" not in plan["withdrawal"]
    assert len(plan["withdrawal"]["notes"]) == 2 and len(plan["withdrawal"]["linked"]) == 4
    assert plan["checkpoint"]["manifest_hash"] == case["manifest"].digest
    result = apply(case, plan)
    assert (
        not result["recovery_complete"]
        and not result["activation_authorized"]
        and not result["latest_completeness_verified"]
    )
    with connect() as db:
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["source"]),
        ).fetchone() == (False,)
        assert db.execute(
            "SELECT count(*) FROM work.drafts WHERE workspace_id=%s AND state='forgotten'",
            (case["workspace"],),
        ).fetchone() == (2,)
        assert db.execute(
            "SELECT state,payload,payload_hash FROM work.capture_intents WHERE id=%s",
            (case["pending"],),
        ).fetchone() == ("denied", None, None)
        assert db.execute(
            "SELECT state FROM work.capture_intents WHERE id=%s", (case["unrelated"],)
        ).fetchone() == ("pending",)
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s",
                (result["reconciliation_receipt_id"],),
            ).fetchone()[0]
            == result
        )
        inner = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE id=%s",
            (result["source_withdrawal_receipt_id"],),
        ).fetchone()[0]
        assert (
            inner["mode"] == "synthetic_sources_withdrawn"
            and inner["plan_hash"] != result["file_bound_plan_hash"]
        )
    with pytest.raises(ValueError, match="changed"):
        apply(case, plan)
    with pytest.raises(ValueError, match="No source"):
        apply(case, run(case))


def test_equal_selection_from_another_export_invalidates_exact_outer_plan(case):
    plan = run(case)
    body = case["manifest"].body.model_copy(update={"export_id": uuid4()})
    case["manifest"] = files.Manifest(body=body, digest=files.digest(body))
    with pytest.raises(ValueError, match="changed"):
        apply(case, plan)


def test_second_receipt_failure_rolls_back_inner_receipt_and_all_redaction(case):
    plan = run(case)
    with connect() as db:
        collision = db.execute(
            "SELECT id FROM public.audit_events ORDER BY occurred_at LIMIT 1"
        ).fetchone()[0]
    with (
        patch.object(recovery, "uuid4", return_value=collision),
        pytest.raises(psycopg.errors.UniqueViolation),
    ):
        apply(case, plan)
    with connect() as db:
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["source"]),
        ).fetchone() == (True,)
        assert db.execute(
            "SELECT state,payload IS NOT NULL FROM work.capture_intents WHERE id=%s",
            (case["pending"],),
        ).fetchone() == ("pending", True)
        assert db.execute(
            "SELECT count(*) FROM public.audit_events WHERE entity_id=%s AND event_type='admin.work_sources_withdrawn'",
            (str(case["workspace"]),),
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    "fault",
    [
        "target",
        "operator",
        "workspace",
        "pin",
        "future",
        "hash",
        "expired",
        "isolation",
        "grants",
        "active",
        "absent",
    ],
)
def test_bad_target_authority_or_evidence_does_not_apply(case, fault):
    changes = {}
    if fault == "target":
        changes["database"] = "butler_test_wrong"
    if fault == "operator":
        changes["operator_id"] = uuid4()
    if fault == "workspace":
        changes["workspace_id"] = uuid4()
    if fault == "pin":
        changes["expected_manifest_hash"] = "0" * 64
    if fault == "future":
        body = case["manifest"].body.model_copy(
            update={"generated_at": datetime.now(UTC) + timedelta(hours=1)}
        )
        case["manifest"] = files.Manifest(body=body, digest=files.digest(body))
    if fault == "hash":
        changes.update(
            decision="reapply_source_withdrawals",
            issued_at=datetime.now(UTC),
            reviewed_hash="0" * 64,
        )
    if fault == "expired":
        changes["issued_at"] = datetime.now(UTC) - timedelta(minutes=6)
    if fault == "absent":
        body = case["manifest"].body.model_copy(
            update={
                "items": (
                    files.Entry(
                        source_id=uuid4(),
                        receipt_id=uuid4(),
                        withdrawn_at=datetime.now(UTC) - timedelta(minutes=1),
                    ),
                )
            }
        )
        case["manifest"] = files.Manifest(body=body, digest=files.digest(body))
    if fault in {"grants", "active"}:
        with connect() as db:
            if fault == "active":
                db.execute(
                    "UPDATE public.work_workspaces SET is_active=true WHERE id=%s",
                    (case["workspace"],),
                )
            else:
                db.execute(
                    "INSERT INTO public.work_access_grants(user_id,workspace_id,capability,created_at) VALUES(%s,%s,'work_private',now())",
                    (case["actor"], case["workspace"]),
                )
    with pytest.raises(ValueError), connect() as db, db.transaction():
        if fault == "isolation":
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        recovery.reconcile(db, request(case, **changes), case["manifest"])
    with connect() as db:
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["source"]),
        ).fetchone() == (True,)


def test_existing_capacity_limit_prevents_partial_authenticated_recovery(case):
    with connect() as db:
        db.execute(
            "UPDATE public.work_workspaces SET is_active=true WHERE id=%s", (case["workspace"],)
        )
    extra_notes(case, 24)
    quarantine(case)
    with pytest.raises(ValueError, match="Too many derived"):
        run(case)


def test_registry_busy_and_restricted_role_refuse(case):
    with connect() as blocker:
        blocker.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
        with pytest.raises(ValueError, match="busy"):
            run(case)
    with pytest.raises(ValueError, match="Clean"), connect() as db, db.transaction():
        db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(case["role"])))
        recovery.reconcile(db, request(case), case["manifest"])


def test_export_file_failure_preserves_preparation_audit_without_success(
    case, tmp_path, monkeypatch, capsys
):
    import sys

    withdraw(case)
    key_path, output = tmp_path / "key.json", tmp_path / "existing.json"
    auth.write_key(key_path, case["key"])
    output.write_bytes(b"existing-owner-file")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "checkpoint",
            "export",
            "--environment",
            "test",
            "--database",
            settings.postgres_db,
            "--operator",
            str(case["actor"]),
            "--workspace",
            str(case["workspace"]),
            "--source",
            str(case["source"]),
            "--recovery-key",
            str(key_path),
            "--expected-key-fingerprint",
            auth.fingerprint(case["key"]),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit):
        recovery.main()
    captured = capsys.readouterr()
    assert not captured.out and "operation failed" in captured.err
    assert case["key"].material.get_secret_value() not in captured.err
    assert output.read_bytes() == b"existing-owner-file"
    with connect() as db:
        metadata = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE entity_id=%s AND event_type='admin.work_source_checkpoint_prepared'",
            (str(case["workspace"]),),
        ).fetchone()[0]
        assert (
            not metadata["file_saved_verified"] and not metadata["independent_retention_verified"]
        )


def test_export_audit_failure_creates_no_file(case, tmp_path, monkeypatch, capsys):
    import sys

    withdraw(case)
    key_path, output = tmp_path / "key.json", tmp_path / "new.json"
    auth.write_key(key_path, case["key"])
    with connect() as db:
        collision = db.execute("SELECT id FROM public.audit_events LIMIT 1").fetchone()[0]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "checkpoint",
            "export",
            "--environment",
            "test",
            "--database",
            settings.postgres_db,
            "--operator",
            str(case["actor"]),
            "--workspace",
            str(case["workspace"]),
            "--source",
            str(case["source"]),
            "--recovery-key",
            str(key_path),
            "--expected-key-fingerprint",
            auth.fingerprint(case["key"]),
            "--output",
            str(output),
        ],
    )
    with patch.object(recovery, "uuid4", return_value=collision), pytest.raises(SystemExit):
        recovery.main()
    assert not output.exists() and not capsys.readouterr().out
    with connect() as db:
        assert db.execute(
            "SELECT count(*) FROM public.audit_events WHERE entity_id=%s AND event_type='admin.work_source_checkpoint_prepared'",
            (str(case["workspace"]),),
        ).fetchone() == (0,)
