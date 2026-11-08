"""Disposable CI-only retention CLI and restore sentinel; no owner-host acceptance."""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
from app import work_capture, work_drafts, work_lifecycle, work_parties
from app.config import settings
from psycopg.types.json import Jsonb

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
workspace = UUID("dadadada-dada-4ada-8ada-dadadadadada")
policy = UUID("dbdbdbdb-dbdb-4bdb-8bdb-dbdbdbdbdbdb")
source = UUID("dcdcdcdc-dcdc-4cdc-8cdc-dcdcdcdcdcdc")
actor = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)


def command(*args, success=True):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.work_retention",
            "--environment",
            "test",
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
    assert (result.returncode == 0) == success, "Synthetic retention CLI failed"
    if success:
        return json.loads(result.stdout)
    assert not result.stdout and "rolled back" in result.stderr


if sys.argv[1] == "seed":
    with psycopg.connect(url) as db:
        db.execute(
            "INSERT INTO public.users(id,slug,display_name,is_active,created_at,updated_at) VALUES(%s,'synthetic-retention-restore','Synthetic retention',true,clock_timestamp(),clock_timestamp())",
            (actor,),
        )
        db.execute(
            "INSERT INTO public.user_scopes(user_id,scope_id,created_at) SELECT %s,id,clock_timestamp() FROM public.scopes WHERE key='technical_admin'",
            (actor,),
        )
        db.execute(
            "INSERT INTO public.work_workspaces(id,slug,is_active,created_at) VALUES(%s,'synthetic-retention-restore',true,clock_timestamp())",
            (workspace,),
        )
        db.execute(
            "INSERT INTO work.retention_policies VALUES(%s,%s,86400)",
            (workspace, policy),
        )
        db.execute(
            "INSERT INTO work.validation_records(workspace_id,id,marker) VALUES(%s,%s,'synthetic:retention-source')",
            (workspace, source),
        )
        db.execute(
            "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
            (workspace, source),
        )
    with psycopg.connect(url) as db, db.transaction():
        short = datetime.now(UTC) + timedelta(seconds=3)
        live = datetime.now(UTC) + timedelta(hours=1)
        for marker, until in (
            ("synthetic:retention-expired-note", short),
            ("synthetic:retention-live-note", live),
        ):
            note = work_drafts.create(
                db,
                workspace,
                actor,
                policy,
                work_lifecycle.Draft(
                    kind="action",
                    marker=marker,
                    source_ids=(source,),
                    retain_until=until,
                ),
            )
            digest = db.execute(
                "SELECT encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') FROM work.drafts WHERE workspace_id=%s AND id=%s",
                (workspace, note.id),
            ).fetchone()[0]
            review = db.execute(
                "INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash,expires_at) VALUES(%s,%s,1,%s,%s,%s,'confirm_note',%s,%s) RETURNING id,session_id",
                (workspace, note.id, actor, uuid4(), uuid4(), digest, short),
            ).fetchone()
            db.execute(
                "INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) VALUES(%s,%s,%s,1,%s,%s,%s,%s)",
                (workspace, note.id, review[0], actor, review[1], uuid4(), short),
            )
        work_parties.create(
            db, workspace, policy, "synthetic:retention-expired-party", short
        )
        payload = work_capture.Payload(
            policy_id=policy,
            draft=work_capture.Draft(
                kind="action",
                marker="synthetic:retention-pending",
                source_ids=(source,),
                retain_until=live,
            ),
        ).model_dump(mode="json")
        db.execute(
            "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,payload,expires_at) VALUES(%s,%s,%s,%s,%s,%s)",
            (workspace, actor, uuid4(), uuid4(), Jsonb(payload), short),
        )
    with psycopg.connect(url) as db:
        db.execute(
            "UPDATE public.work_workspaces SET is_active=false WHERE id=%s",
            (workspace,),
        )
        db.execute(
            "SELECT pg_sleep(GREATEST(0,extract(epoch FROM (%s-clock_timestamp()))))",
            (short + timedelta(milliseconds=50),),
        )
    plan = command()
    assert len(plan["items"]) == 7 and not plan["has_more"]
    arguments = (
        "--cutoff",
        plan["cutoff"],
        "--reviewed-hash",
        plan["reviewed_hash"],
        "--decision",
        "apply_expired_cleanup",
    )
    result = command(*arguments)
    assert result["workspace_enabled"] is False and len(result["outcomes"]) == 7
    command(*arguments, success=False)
    assert command()["items"] == []
else:
    assert sys.argv[1] == "check"
with psycopg.connect(url) as db:
    assert (
        db.execute(
            "SELECT is_active FROM public.work_workspaces WHERE id=%s", (workspace,)
        ).fetchone()[0]
        is False
    )
    assert (
        db.execute(
            "SELECT count(*) FROM work.drafts WHERE workspace_id=%s AND state='forgotten'",
            (workspace,),
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT count(*) FROM work.draft_revisions r JOIN work.drafts d ON (r.workspace_id,r.record_id)=(d.workspace_id,d.id) WHERE d.workspace_id=%s AND d.state='forgotten' AND r.snapshot IS NOT NULL",
            (workspace,),
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT count(*) FROM work.drafts WHERE workspace_id=%s AND snapshot->>'marker'='synthetic:retention-live-note'",
            (workspace,),
        ).fetchone()[0]
        == 1
    )
    assert db.execute(
        "SELECT marker,state FROM work.parties WHERE workspace_id=%s", (workspace,)
    ).fetchone() == (None, "forgotten")
    assert (
        db.execute(
            "SELECT count(*) FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NOT NULL",
            (workspace,),
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND state='denied' AND payload IS NULL AND payload_hash IS NULL",
            (workspace,),
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT count(*) FROM public.work_confirmation_requests WHERE workspace_id=%s AND state='denied'",
            (workspace,),
        ).fetchone()[0]
        == 2
    )
    receipt = db.execute(
        "SELECT metadata_json FROM public.audit_events WHERE event_type='admin.work_retention_applied' AND entity_id=%s",
        (str(workspace),),
    ).fetchone()[0]
    assert receipt["workspace_enabled"] is False and len(receipt["outcomes"]) == 7
    assert (
        db.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname='draft_review_retention_barrier' AND tgenabled='O'",
            (),
        ).fetchone()[0]
        == 1
    )
print(
    "Synthetic retention CLI/receipt/redactions/disabled-workspace sentinel verified; no payloads displayed"
)
