"""Disposable restored pending-input cleanup; no operator content or credentials."""

import json
import subprocess
import sys
from datetime import timedelta
from uuid import UUID, uuid4

import psycopg
from app import work_capture_worker, work_drafts, work_lifecycle
from app.config import settings
from psycopg.types.json import Jsonb

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
phase = sys.argv[1]
assert phase in {"seed", "check", "container"}
workspace = UUID("c5c5c5c5-c5c5-45c5-85c5-c5c5c5c5c5c5")
actor = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
policy = UUID("c3c3c3c3-c3c3-43c3-83c3-c3c3c3c3c3c3")
source = UUID("c4c4c4c4-c4c4-44c4-84c4-c4c4c4c4c4c4")
url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)
if phase in {"seed", "container"}:
    with psycopg.connect(url) as db:
        db.execute(
            "INSERT INTO public.work_workspaces(id,slug,is_active,created_at) VALUES(%s,'synthetic-restored-pending-input',true,clock_timestamp())",
            (workspace,),
        )
        db.execute(
            "INSERT INTO public.work_access_grants(user_id,workspace_id,capability,created_at) VALUES(%s,%s,'work_private',clock_timestamp())",
            (actor, workspace),
        )
        db.execute(
            "INSERT INTO work.retention_policies VALUES(%s,%s,86400)",
            (workspace, policy),
        )
        db.execute(
            "INSERT INTO work.validation_records(workspace_id,id,marker) VALUES(%s,%s,'synthetic:pending-input-source')",
            (workspace, source),
        )
        db.execute(
            "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
            (workspace, source),
        )
        until = work_drafts._now(db) + timedelta(hours=1)
        note = work_drafts.create(
            db,
            workspace,
            actor,
            policy,
            work_lifecycle.Draft(
                kind="decision",
                marker="synthetic:pending-input-live-control",
                source_ids=(source,),
                retain_until=until,
            ),
        )
        session = uuid4()
        payload = {
            "policy_id": str(policy),
            "draft": {
                "kind": "decision",
                "marker": "synthetic:pending-input-unsaved",
                "source_ids": [str(source)],
                "retain_until": until.isoformat(),
            },
        }
        for intent in ("capture_draft", "correct_note", "forget_note", "capture_draft"):
            identifier = db.execute(
                "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,intent,target_record_id,expected_revision,payload,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp()+interval '4 minutes') RETURNING id",
                (
                    workspace,
                    actor,
                    session,
                    uuid4(),
                    intent,
                    None if intent == "capture_draft" else note.id,
                    None if intent == "capture_draft" else 1,
                    Jsonb({"forget": True} if intent == "forget_note" else payload),
                ),
            ).fetchone()[0]
        work_capture_worker._finish(
            db, {"id": identifier, "workspace_id": workspace}, reason="expired"
        )
        review = db.execute(
            "INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash) SELECT workspace_id,id,revision,%s,%s,%s,'confirm_note',encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') FROM work.drafts WHERE workspace_id=%s AND id=%s RETURNING id,expires_at",
            (actor, session, uuid4(), workspace, note.id),
        ).fetchone()
        db.execute(
            "INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) VALUES(%s,%s,%s,1,%s,%s,%s,%s)",
            (workspace, note.id, review[0], actor, session, uuid4(), review[1]),
        )


def command(module, *args, success=True):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            module,
            "--environment",
            "test",
            "--restored-database",
            settings.postgres_db,
            "--workspace",
            str(workspace),
            "--operator",
            str(actor),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == success, "Synthetic restored-request CLI failed"
    if success:
        return json.loads(result.stdout)
    assert not result.stdout and "rolled back" in result.stderr


if phase != "seed":
    with psycopg.connect(url) as db:
        notes = db.execute(
            "SELECT * FROM work.drafts ORDER BY workspace_id,id"
        ).fetchall()
        parties = db.execute(
            "SELECT * FROM work.parties ORDER BY workspace_id,id"
        ).fetchall()
        completed = db.execute(
            "SELECT * FROM work.capture_intents WHERE workspace_id=%s AND reason_code='expired'",
            (workspace,),
        ).fetchall()
        foreign = db.execute(
            "SELECT * FROM work.capture_intents WHERE workspace_id<>%s ORDER BY workspace_id,id",
            (workspace,),
        ).fetchall()
        assert (
            db.execute(
                "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND state='pending'",
                (workspace,),
            ).fetchone()[0]
            == 3
        )
        if phase == "check":
            assert (
                db.execute(
                    "SELECT count(*) FROM public.audit_events WHERE event_type='admin.work_restore_requests_discarded' AND entity_id=%s",
                    (str(workspace),),
                ).fetchone()[0]
                == 0
            )
    quarantine = command("app.work_restore")
    command(
        "app.work_restore",
        "--issued-at",
        quarantine["issued_at"],
        "--reviewed-hash",
        quarantine["reviewed_hash"],
        "--decision",
        "quarantine_restored_workspace",
    )
    plan = command("app.work_restore_requests")
    assert len(plan["items"]) == 5
    assert {item["intent"] for item in plan["items"] if item["kind"] == "capture"} == {
        "capture_draft",
        "correct_note",
        "forget_note",
    }
    assert "payload_hash" not in json.dumps(
        plan
    ) and "synthetic:pending-input-unsaved" not in json.dumps(plan)
    args = (
        "--issued-at",
        plan["issued_at"],
        "--reviewed-hash",
        plan["reviewed_hash"],
        "--decision",
        "discard_restored_requests",
    )
    result = command("app.work_restore_requests", *args)
    command("app.work_restore_requests", *args, success=False)
    assert (
        not result["recovery_complete"]
        and not result["workspace_enabled"]
        and result["work_grants"] == 0
    )
    with psycopg.connect(url) as db:
        assert (
            db.execute("SELECT * FROM work.drafts ORDER BY workspace_id,id").fetchall()
            == notes
        )
        assert (
            db.execute("SELECT * FROM work.parties ORDER BY workspace_id,id").fetchall()
            == parties
        )
        assert (
            db.execute(
                "SELECT * FROM work.capture_intents WHERE workspace_id=%s AND reason_code='expired'",
                (workspace,),
            ).fetchall()
            == completed
        )
        assert (
            db.execute(
                "SELECT * FROM work.capture_intents WHERE workspace_id<>%s ORDER BY workspace_id,id",
                (workspace,),
            ).fetchall()
            == foreign
        )
        assert (
            db.execute(
                "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND (state='pending' OR payload IS NOT NULL OR payload_hash IS NOT NULL)",
                (workspace,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM public.work_confirmation_requests WHERE workspace_id=%s AND state='pending'",
                (workspace,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NOT NULL",
                (workspace,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s",
                (result["receipt_id"],),
            ).fetchone()[0]
            == result
        )
        assert (
            db.execute(
                "SELECT is_active FROM public.work_workspaces WHERE id=%s", (workspace,)
            ).fetchone()[0]
            is False
        )
        assert (
            db.execute(
                "SELECT count(*) FROM public.work_access_grants WHERE workspace_id=%s",
                (workspace,),
            ).fetchone()[0]
            == 0
        )
print(
    "Synthetic restored pending-input fixture seeded; no payloads displayed"
    if phase == "seed"
    else "Synthetic restored pending-input cleanup/receipt/live-control preservation verified; no payloads/hashes displayed"
)
