"""Unexpired older-snapshot forgetting, trusted metadata input and atomic guards."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb
from work_migration_helpers import assert_downgrade_refused
from work_storage_helpers import PASSWORD, connect

from app import (
    work_capture,
    work_drafts,
    work_parties,
    work_restore,
)
from app import (
    work_suppression as suppression,
)
from app.config import settings
from app.manage import set_scope
from app.models import User
from app.work_manage import administer
from app.work_suppression_file import Body, Manifest, digest

pytestmark = pytest.mark.integration


@pytest.fixture
def case(review_case):
    with review_case["maker"].begin() as db:
        set_scope(db, db.get(User, review_case["actor"]), "technical_admin", True)
    with connect() as db, db.transaction():
        party = work_parties.create(
            db,
            review_case["workspace"],
            review_case["policy"],
            "synthetic:suppressed-person",
            work_drafts._now(db) + timedelta(hours=1),
        )
    return dict(review_case, party=party)


def manifest(case, **changes):
    with connect() as db:
        now = work_drafts._now(db)
    entries = [
        {
            "kind": kind,
            "id": item.id,
            "forgotten_revision": 2,
            "forgotten_at": now - timedelta(seconds=1),
        }
        for kind, item in [("note", case["item"]), ("party", case["party"])]
    ]
    values = {
        "export_id": uuid4(),
        "workspace_id": case["workspace"],
        "exported_by": case["actor"],
        "source_database_oid": 1,
        "generated_at": now,
        "items": entries,
    }
    values.update(changes)
    body = Body(**values)
    return Manifest(body=body, digest=digest(body))


def request(case, **changes):
    values = {
        "workspace_id": case["workspace"],
        "operator_id": case["actor"],
        "database": settings.postgres_db,
    }
    values.update(changes)
    return suppression.Request(**values)


def run(case, value, **changes):
    with connect() as db, db.transaction():
        return suppression.reconcile(db, request(case, **changes), value)


def apply(case, value, plan):
    return run(
        case,
        value,
        decision="reconcile_restored_suppressions",
        issued_at=datetime.fromisoformat(plan["issued_at"]),
        reviewed_hash=plan["reviewed_hash"],
    )


def quarantine(case):
    with connect() as db, db.transaction():
        first = work_restore.Request(
            workspace_id=case["workspace"],
            operator_id=case["actor"],
            restored_database=settings.postgres_db,
        )
        plan = work_restore.reconcile(db, first)
        work_restore.reconcile(
            db,
            work_restore.Request(
                **first.model_dump(exclude={"decision", "issued_at", "reviewed_hash"}),
                decision="quarantine_restored_workspace",
                issued_at=datetime.fromisoformat(plan["issued_at"]),
                reviewed_hash=plan["reviewed_hash"],
            ),
        )


def pending(case, *, count=1, target=None):
    target = target or case["item"].id
    content = work_capture.Payload(
        policy_id=case["policy"],
        draft=work_capture.Draft(
            kind="action",
            marker="synthetic:pending-suppressed",
            source_ids=(case["source"],),
            retain_until=case["item"].retain_until,
        ),
    ).model_dump(mode="json")
    with connect() as db:
        for _ in range(count):
            db.execute(
                "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,intent,target_record_id,expected_revision,payload,expires_at) VALUES(%s,%s,%s,%s,'correct_note',%s,1,%s,clock_timestamp()+interval '4 minutes')",
                (case["workspace"], case["actor"], uuid4(), uuid4(), target, Jsonb(content)),
            )


def state(case):
    with connect() as db:
        return tuple(
            db.execute(q, (case["workspace"],)).fetchone()[0]
            for q in (
                "SELECT count(*) FROM work.drafts WHERE workspace_id=%s AND state='forgotten'",
                "SELECT count(*) FROM work.parties WHERE workspace_id=%s AND state='forgotten'",
                "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND payload IS NOT NULL",
                "SELECT count(*) FROM public.audit_events WHERE entity_id=%s::text AND event_type='admin.work_suppression_applied'",
            )
        )


def test_unexpired_older_content_and_linked_copies_are_scrubbed_atomically(case):
    pending(case)
    with connect() as db:
        review = db.execute(
            "INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash) SELECT workspace_id,id,revision,%s,%s,%s,'confirm_note',encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') FROM work.drafts WHERE id=%s RETURNING id,session_id,expires_at",
            (case["actor"], uuid4(), uuid4(), case["item"].id),
        ).fetchone()
        db.execute(
            "INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) VALUES(%s,%s,%s,1,%s,%s,%s,%s)",
            (
                case["workspace"],
                case["item"].id,
                review[0],
                case["actor"],
                review[1],
                uuid4(),
                review[2],
            ),
        )
    value = manifest(case)
    quarantine(case)
    plan = run(case, value)
    assert plan["linked_count"] == 3 and len(plan["items"]) == 2
    assert run(case, value, issued_at=datetime.fromisoformat(plan["issued_at"])) == plan
    encoded = json.dumps(plan)
    for secret in (
        "review-note",
        "suppressed-person",
        "pending-suppressed",
        "payload_hash",
        str(case["source"]),
        str(case["policy"]),
    ):
        assert secret not in encoded
    result = apply(case, value, plan)
    assert state(case) == (1, 1, 0, 1) and result["recovery_complete"] is False
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_revisions WHERE workspace_id=%s AND snapshot IS NOT NULL",
                (case["workspace"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NOT NULL",
                (case["workspace"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM public.work_confirmation_requests WHERE workspace_id=%s AND state='pending'",
                (case["workspace"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT is_active FROM public.work_workspaces WHERE id=%s", (case["workspace"],)
            ).fetchone()[0]
            is False
        )
        assert (
            db.execute(
                "SELECT count(*) FROM public.work_access_grants WHERE workspace_id=%s",
                (case["workspace"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s", (result["receipt_id"],)
            ).fetchone()[0]
            == result
        )
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, value, plan)
    no_op = run(case, value)
    with pytest.raises(ValueError, match="No changes"):
        apply(case, value, no_op)
    assert_downgrade_refused(
        "0016_work_retention", "0017_work_suppression", "Suppression reconciliation evidence exists"
    )


def test_export_uses_real_terminal_decisions_and_prepared_audit(case):
    with connect() as db, db.transaction():
        work_drafts.transition(db, case["workspace"], case["actor"], case["item"].id, 1, "forget")
        work_parties.transition(db, case["workspace"], case["party"].id, 1, "forget")
    with case["maker"].begin() as db:
        administer(db, "disable", case["slug"])
    with connect() as db, db.transaction():
        value = suppression.prepare(db, request(case, decision="export"))
    assert [entry.kind for entry in value.body.items] == ["note", "party"]
    assert [entry.forgotten_revision for entry in value.body.items] == [2, 2]
    assert "review-note" not in value.model_dump_json()
    with connect() as db:
        meta = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE event_type='admin.work_suppression_manifest_prepared' AND entity_id=%s",
            (str(case["workspace"]),),
        ).fetchone()[0]
        assert meta["manifest_hash"] == value.digest and meta["saved_file_proven"] is False


@pytest.mark.parametrize(
    "fault",
    ["active", "grants", "operator", "target", "workspace", "future", "role", "isolation", "idle"],
)
def test_closed_target_identity_manifest_and_role(case, fault):
    value = manifest(case)
    if fault != "active":
        quarantine(case)
    if fault == "grants":
        with connect() as db:
            db.execute(
                "INSERT INTO public.work_access_grants(user_id,workspace_id,capability,created_at) VALUES(%s,%s,'work_private',clock_timestamp())",
                (case["actor"], case["workspace"]),
            )
    if fault == "operator":
        with case["maker"].begin() as db:
            set_scope(db, db.get(User, case["actor"]), "technical_admin", False)
    if fault == "workspace":
        value = manifest(case, workspace_id=uuid4())
    if fault == "future":
        value = manifest(case, generated_at=value.body.generated_at + timedelta(minutes=2))
    before = state(case)
    with pytest.raises((ValueError, psycopg.Error)):
        if fault in {"role", "isolation", "idle"}:
            with connect(
                case["login"] if fault == "role" else None, PASSWORD if fault == "role" else None
            ) as db:
                if fault != "idle":
                    db.execute("BEGIN")
                if fault == "isolation":
                    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                suppression.reconcile(db, request(case), value)
        else:
            run(case, value, **({"database": "butler_test_wrong"} if fault == "target" else {}))
    assert state(case) == before


@pytest.mark.parametrize("fault", ["conflict", "old", "future", "linked", "stale"])
def test_plan_conflict_time_caps_and_staleness(case, fault):
    if fault == "linked":
        pending(case, count=101)
    elif fault == "stale":
        pending(case)
    value = manifest(case)
    if fault == "conflict":
        with connect() as db, db.transaction():
            work_drafts.transition(
                db, case["workspace"], case["actor"], case["item"].id, 1, "confirm"
            )
    quarantine(case)
    before = state(case)
    if fault == "stale":
        plan = run(case, value)
        with connect() as db:
            db.execute(
                "UPDATE work.capture_intents SET state='denied',payload=NULL,reason_code='expired',finished_at=clock_timestamp() WHERE workspace_id=%s AND state='pending'",
                (case["workspace"],),
            )
        before = state(case)
        with pytest.raises(ValueError, match="Plan changed"):
            apply(case, value, plan)
    else:
        changes = (
            {"issued_at": value.body.generated_at + timedelta(minutes=-6 if fault == "old" else 2)}
            if fault in {"old", "future"}
            else {}
        )
        with pytest.raises(ValueError):
            run(case, value, **changes)
    assert state(case) == before


@pytest.mark.parametrize("target", ["private", "public"])
def test_audit_failure_rolls_back_all_redaction(case, target):
    pending(case)
    value = manifest(case)
    quarantine(case)
    plan = run(case, value)
    before = state(case)
    name = "synthetic_suppression_" + uuid4().hex
    table = "work.draft_audit" if target == "private" else "public.audit_events"
    event = "draft.forgotten" if target == "private" else "admin.work_suppression_applied"
    with connect() as db:
        db.execute(
            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} CHECK(event_type<>{}) NOT VALID").format(
                sql.SQL(table), sql.Identifier(name), sql.Literal(event)
            )
        )
    try:
        with pytest.raises(psycopg.Error):
            apply(case, value, plan)
        assert state(case) == before
        assert run(case, value, issued_at=datetime.fromisoformat(plan["issued_at"])) == plan
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                    sql.SQL(table), sql.Identifier(name)
                )
            )


def test_absent_decision_cleans_orphans_and_preserves_unselected_content(case):
    missing = uuid4()
    with connect() as db:
        db.execute(
            "INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) VALUES(%s,%s,%s,1,%s,%s,%s,clock_timestamp()+interval '4 minutes')",
            (case["workspace"], missing, uuid4(), case["actor"], uuid4(), uuid4()),
        )
    with connect() as db:
        now = work_drafts._now(db)
    value = manifest(
        case,
        items=[
            {
                "kind": "note",
                "id": missing,
                "forgotten_revision": 2,
                "forgotten_at": now - timedelta(seconds=1),
            }
        ],
    )
    quarantine(case)
    result = apply(case, value, run(case, value))
    assert result["outcomes"][0]["previous_state"] == "absent"
    assert state(case) == (0, 0, 0, 1)
    with connect() as db:
        assert (
            db.execute(
                "SELECT snapshot->>'marker' FROM work.drafts WHERE id=%s", (case["item"].id,)
            ).fetchone()[0]
            == "synthetic:review-note"
        )


def test_restore_modes_cannot_correct_confirm_or_bypass_grants(case):
    with pytest.raises(ValueError), connect() as db, db.transaction():
        work_drafts.transition(
            db, case["workspace"], case["actor"], case["item"].id, 1, "confirm", restore=True
        )
    with case["maker"].begin() as db:
        administer(db, "disable", case["slug"])
    with pytest.raises(ValueError), connect() as db, db.transaction():
        work_drafts.transition(
            db, case["workspace"], case["actor"], case["item"].id, 1, "forget", restore=True
        )
    with pytest.raises(psycopg.Error), case["storage"]["session"]() as db:
        db.execute("SET LOCAL butler.restore_suppression='reviewed'")
        db.execute("SELECT work.restore_suppression_allowed(%s)", (case["workspace"],))
    with connect() as db:
        assert (
            db.execute(
                "SELECT work.restore_suppression_allowed(%s)", (case["workspace"],)
            ).fetchone()[0]
            is False
        )


def test_expiry_during_apply_rolls_back(case, monkeypatch):
    value = manifest(case)
    quarantine(case)
    plan = run(case, value)
    before = state(case)
    original = work_drafts._now
    calls = 0

    def late(db):
        nonlocal calls
        calls += 1
        return original(db) + timedelta(minutes=6) if calls >= 4 else original(db)

    monkeypatch.setattr(work_drafts, "_now", late)
    with pytest.raises(ValueError, match="current server"):
        apply(case, value, plan)
    assert state(case) == before


def test_concurrent_reconciliation_and_bounded_registry_wait(case):
    value = manifest(case)
    quarantine(case)
    plan = run(case, value)
    ready, release = Event(), Event()

    def reader():
        with connect() as db:
            db.execute("SELECT pg_advisory_xact_lock_shared(1508310,1)")
            ready.set()
            assert release.wait(8)

    with ThreadPoolExecutor(1) as pool:
        held = pool.submit(reader)
        assert ready.wait(4)
        try:
            with pytest.raises(psycopg.errors.LockNotAvailable):
                apply(case, value, plan)
        finally:
            release.set()
        held.result(timeout=5)
    start = Event()

    def cleaner():
        assert start.wait(4)
        try:
            apply(case, value, plan)
            return "applied"
        except ValueError:
            return "stale"

    with ThreadPoolExecutor(2) as pool:
        first, second = pool.submit(cleaner), pool.submit(cleaner)
        start.set()
        assert sorted([first.result(timeout=8), second.result(timeout=8)]) == ["applied", "stale"]
    assert state(case) == (1, 1, 0, 1)


def test_export_refuses_partial_large_source_ledger(case):
    with connect() as db, db.transaction():
        now = work_drafts._now(db)
        for _ in range(26):
            item = work_parties.create(
                db,
                case["workspace"],
                case["policy"],
                "synthetic:cap-party",
                now + timedelta(hours=1),
            )
            work_parties.transition(db, case["workspace"], item.id, 1, "forget")
    with case["maker"].begin() as db:
        administer(db, "disable", case["slug"])
    with pytest.raises(ValueError, match="no partial"), connect() as db, db.transaction():
        suppression.prepare(db, request(case, decision="export"))
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM public.audit_events WHERE event_type='admin.work_suppression_manifest_prepared' AND entity_id=%s",
                (str(case["workspace"]),),
            ).fetchone()[0]
            == 0
        )


def test_direct_sql_without_restore_mode_cannot_forget_live_quarantined_party(case):
    quarantine(case)
    with pytest.raises(psycopg.Error), connect() as db:
        db.execute(
            "UPDATE work.parties SET state='forgotten',revision=revision+1,marker=NULL WHERE workspace_id=%s AND id=%s",
            (case["workspace"], case["party"].id),
        )
    assert state(case) == (0, 0, 0, 0)


@pytest.mark.parametrize("tampered", [False, True, "older"])
def test_authenticated_cli_and_receipt_preserve_owner_quarantine_boundaries(
    case, tmp_path, tampered
):
    import sys

    from app import work_suppression_auth as auth

    value = manifest(case)
    quarantine(case)
    key = auth.generate_key(case["workspace"])
    key_path = tmp_path / "key.json"
    path = tmp_path / "manifest.json"
    auth.write_key(key_path, key)
    auth.write_signed(path, value, key)
    raw = json.loads(path.read_text())
    mac = raw["mac"]
    if tampered == "older":
        older_body = value.body.model_copy(update={"items": value.body.items[:1]})
        older = Manifest(body=older_body, digest=digest(older_body))
        path.unlink()
        auth.write_signed(path, older, key)
        assert auth.read_signed(path, key, case["workspace"]) == older
    elif tampered:
        # Recompute the old unkeyed digest: this must still fail HMAC before writes.
        other = manifest(case)
        raw["manifest"] = other.model_dump(mode="json")
        path.write_text(json.dumps(raw))
    base = [
        sys.executable,
        "-m",
        "app.work_suppression",
        "--environment",
        "test",
        "--database",
        settings.postgres_db,
        "--workspace",
        str(case["workspace"]),
        "--operator",
        str(case["actor"]),
        "--recovery-key",
        str(key_path),
        "--expected-key-fingerprint",
        auth.fingerprint(key),
        "--expected-manifest-hash",
        value.digest,
    ]
    before = state(case)
    preview = subprocess.run(
        [*base, "preview", "--manifest", str(path)], capture_output=True, text=True, check=False
    )
    if tampered:
        assert preview.returncode != 0 and not preview.stdout
        assert state(case) == before
        return
    assert preview.returncode == 0, preview.stderr
    plan = json.loads(preview.stdout)
    assert plan["authentication"]["key_fingerprint"] == auth.fingerprint(key)
    applied = subprocess.run(
        [
            *base,
            "apply",
            "--manifest",
            str(path),
            "--issued-at",
            plan["issued_at"],
            "--reviewed-hash",
            plan["reviewed_hash"],
            "--decision",
            "reconcile_restored_suppressions",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert applied.returncode == 0, applied.stderr
    result = json.loads(applied.stdout)
    assert state(case) == (1, 1, 0, 1)
    assert result["checkpoint"] == {
        "mode": "independently_pinned_manifest",
        "manifest_hash": value.digest,
    }
    assert result["authentication"]["key_id"] == str(key.key_id)
    with connect() as db:
        metadata = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE id=%s", (result["receipt_id"],)
        ).fetchone()[0]
        assert metadata == result
        assert key.material.get_secret_value() not in json.dumps(metadata)
        assert mac not in json.dumps(metadata)


def test_review_hash_binds_public_key_reference(case):
    from app import work_suppression_auth as auth

    value = manifest(case)
    quarantine(case)
    first, second = auth.generate_key(case["workspace"]), auth.generate_key(case["workspace"])
    issued = value.body.generated_at
    plan = run(
        case,
        value,
        issued_at=issued,
        auth_key_id=first.key_id,
        auth_key_fingerprint=auth.fingerprint(first),
    )
    with pytest.raises(ValueError, match="Plan changed"):
        run(
            case,
            value,
            decision="reconcile_restored_suppressions",
            issued_at=issued,
            reviewed_hash=plan["reviewed_hash"],
            auth_key_id=second.key_id,
            auth_key_fingerprint=auth.fingerprint(second),
        )
    assert state(case) == (0, 0, 0, 0)


def test_review_hash_binds_checkpoint_context(case):
    value = manifest(case)
    quarantine(case)
    plan = run(case, value)
    assert plan["checkpoint"] == {"mode": "trusted_owner_input"}
    with pytest.raises(ValueError, match="Plan changed"):
        run(
            case,
            value,
            decision="reconcile_restored_suppressions",
            issued_at=datetime.fromisoformat(plan["issued_at"]),
            reviewed_hash=plan["reviewed_hash"],
            expected_manifest_hash=value.digest,
        )
    with pytest.raises(ValueError, match="checkpoint"):
        run(case, value, expected_manifest_hash="0" * 64)
    assert state(case) == (0, 0, 0, 0)
