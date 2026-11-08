"""Disposable old-snapshot/newer-file reconciliation fixture; no operator data."""

import json
import os
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from app import identity, work_capture, work_drafts, work_lifecycle, work_parties
from app import work_suppression_auth as auth
from app.config import settings
from app.work_suppression_file import Body, Manifest, digest
from psycopg.types.json import Jsonb
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
phase = sys.argv[1]
assert phase in {"seed", "export", "reconcile", "container"}
workspace = UUID("a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1")
actor = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
policy = UUID("a3a3a3a3-a3a3-43a3-83a3-a3a3a3a3a3a3")
source = UUID("a4a4a4a4-a4a4-44a4-84a4-a4a4a4a4a4a4")
session_id = UUID("a2a2a2a2-a2a2-42a2-82a2-a2a2a2a2a2a2")
token = "synthetic-suppression-restored-session-" + "f" * 40
url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)
recovery_key_path = os.environ.get("BUTLER_SUPPRESSION_KEY_FILE")
recovery_pin = os.environ.get("BUTLER_SUPPRESSION_KEY_FINGERPRINT")
expected_manifest_hash = os.environ.get("BUTLER_SUPPRESSION_EXPECTED_HASH")


def command(module, *args, success=True):
    target_flag = (
        "--restored-database" if module == "app.work_restore" else "--database"
    )
    auth_args = (
        []
        if module != "app.work_suppression"
        else [
            "--recovery-key",
            str(recovery_key_path),
            "--expected-key-fingerprint",
            recovery_pin,
        ]
    )
    if module == "app.work_suppression" and args[0] != "export":
        auth_args += ["--expected-manifest-hash", expected_manifest_hash]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            module,
            "--environment",
            "test",
            target_flag,
            settings.postgres_db,
            "--workspace",
            str(workspace),
            "--operator",
            str(actor),
            *auth_args,
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == success, "Synthetic suppression CLI failed"
    if success:
        return json.loads(result.stdout)
    assert not result.stdout and "inspect" in result.stderr


if phase in {"seed", "container"}:
    with psycopg.connect(url) as db:
        db.execute(
            "INSERT INTO public.work_workspaces(id,slug,is_active,created_at) VALUES(%s,'synthetic-old-backup-suppression',true,clock_timestamp())",
            (workspace,),
        )
        db.execute(
            "INSERT INTO public.work_access_grants(user_id,workspace_id,capability,created_at) VALUES(%s,%s,'work_private',clock_timestamp())",
            (actor, workspace),
        )
        db.execute(
            "INSERT INTO public.auth_sessions(id,user_id,token_hash,csrf_hash,created_at,last_seen_at,expires_at) VALUES(%s,%s,%s,%s,clock_timestamp(),clock_timestamp(),clock_timestamp()+interval '1 hour')",
            (
                session_id,
                actor,
                identity.digest(token),
                identity.digest("synthetic-suppression-csrf"),
            ),
        )
        db.execute(
            "INSERT INTO work.retention_policies VALUES(%s,%s,86400)",
            (workspace, policy),
        )
        db.execute(
            "INSERT INTO work.validation_records(workspace_id,id,marker) VALUES(%s,%s,'synthetic:old-backup-source')",
            (workspace, source),
        )
        db.execute(
            "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
            (workspace, source),
        )
    with psycopg.connect(url) as db, db.transaction():
        until = work_drafts._now(db) + timedelta(hours=1)
        party = work_parties.create(
            db, workspace, policy, "synthetic:old-backup-person", until
        )
        selected = work_drafts.create(
            db,
            workspace,
            actor,
            policy,
            work_lifecycle.Draft(
                kind="action",
                marker="synthetic:old-backup-forget",
                source_ids=(source,),
                owner_id=party.id,
                retain_until=until,
            ),
        )
        work_drafts.create(
            db,
            workspace,
            actor,
            policy,
            work_lifecycle.Draft(
                kind="decision",
                marker="synthetic:old-backup-control",
                source_ids=(source,),
                retain_until=until,
            ),
        )
        content = work_capture.Payload(
            policy_id=policy,
            draft=work_capture.Draft(
                kind="action",
                marker="synthetic:old-backup-pending",
                source_ids=(source,),
                retain_until=until,
            ),
        ).model_dump(mode="json")
        for intent in ("correct_note", "forget_note"):
            db.execute(
                "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,intent,target_record_id,expected_revision,payload,expires_at) VALUES(%s,%s,%s,%s,%s,%s,1,%s,clock_timestamp()+interval '4 minutes')",
                (
                    workspace,
                    actor,
                    session_id,
                    uuid4(),
                    intent,
                    selected.id,
                    Jsonb({"forget": True} if intent == "forget_note" else content),
                ),
            )
        review = db.execute(
            "INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash) SELECT workspace_id,id,revision,%s,%s,%s,'confirm_note',encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') FROM work.drafts WHERE workspace_id=%s AND id=%s RETURNING id,expires_at",
            (actor, session_id, uuid4(), workspace, selected.id),
        ).fetchone()
        db.execute(
            "INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) VALUES(%s,%s,%s,1,%s,%s,%s,%s)",
            (workspace, selected.id, review[0], actor, session_id, uuid4(), review[1]),
        )
    if phase == "seed":
        print("Synthetic pre-forgetting backup fixture seeded; no payloads displayed")


def current(db):
    selected = db.execute(
        "SELECT id,revision,state,retain_until FROM work.drafts WHERE workspace_id=%s AND state<>'forgotten' AND snapshot->>'marker'='synthetic:old-backup-forget'",
        (workspace,),
    ).fetchone()
    party = db.execute(
        "SELECT id,revision,state FROM work.parties WHERE workspace_id=%s", (workspace,)
    ).fetchone()
    return selected, party


if phase == "export":
    with psycopg.connect(url) as db, db.transaction():
        selected, party = current(db)
        work_drafts.transition(db, workspace, actor, selected[0], selected[1], "forget")
        db.execute(
            "UPDATE public.work_workspaces SET is_active=false WHERE id=%s",
            (workspace,),
        )
    older_saved = command(
        "app.work_suppression",
        "export",
        "--output",
        os.environ["BUTLER_SUPPRESSION_OLDER_FILE"],
    )
    assert older_saved["item_count"] == 1
    # Isolated source fixture only: create the later party decision and export B.
    with psycopg.connect(url) as db, db.transaction():
        db.execute(
            "UPDATE public.work_workspaces SET is_active=true WHERE id=%s", (workspace,)
        )
        work_parties.transition(db, workspace, party[0], party[1], "forget")
        db.execute(
            "UPDATE public.work_workspaces SET is_active=false WHERE id=%s",
            (workspace,),
        )
    saved = command(
        "app.work_suppression",
        "export",
        "--output",
        os.environ["BUTLER_SUPPRESSION_MANIFEST_FILE"],
    )
    assert saved["item_count"] == 2
    assert (
        len(
            auth.read_signed(
                os.environ["BUTLER_SUPPRESSION_MANIFEST_FILE"],
                auth.load_key(recovery_key_path, recovery_pin, workspace),
                workspace,
            ).body.items
        )
        == 2
    )
    assert saved["checkpoint"]["manifest_hash"] == saved["manifest_hash"]
    # Parent retains source checkpoint before opening candidate files.
    print(json.dumps(saved))


if phase in {"container", "reconcile"}:
    with tempfile.TemporaryDirectory(prefix="synthetic-suppression-") as directory:
        path = (
            Path(directory) / "manifest.json"
            if phase == "container"
            else Path(os.environ["BUTLER_SUPPRESSION_MANIFEST_FILE"])
        )
        older_path = (
            Path(directory) / "older.json"
            if phase == "container"
            else Path(os.environ["BUTLER_SUPPRESSION_OLDER_FILE"])
        )
        if phase == "container":
            recovery_key_path = Path(directory) / "primary-key.json"
            generated = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.work_suppression_auth",
                    "generate",
                    "--workspace",
                    str(workspace),
                    "--output",
                    str(recovery_key_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            assert generated.returncode == 0, "Synthetic key generation failed"
            recovery_pin = json.loads(generated.stdout)["fingerprint"]
        key = auth.load_key(recovery_key_path, recovery_pin, workspace)
        with psycopg.connect(url) as db:
            selected, party = current(db)
            assert (
                selected
                and selected[2] == "draft"
                and selected[3] > work_drafts._now(db)
                and party[2] == "active"
            )
            control = db.execute(
                "SELECT id,snapshot FROM work.drafts WHERE workspace_id=%s AND snapshot->>'marker'='synthetic:old-backup-control'",
                (workspace,),
            ).fetchone()
            if phase == "container":
                # Trusted synthetic input; the PG restore drill separately tests real newer export.
                now = work_drafts._now(db)
                body = Body(
                    export_id=uuid4(),
                    workspace_id=workspace,
                    exported_by=actor,
                    source_database_oid=db.execute(
                        "SELECT oid FROM pg_database WHERE datname=current_database()"
                    ).fetchone()[0],
                    generated_at=now,
                    items=(
                        {
                            "kind": "note",
                            "id": selected[0],
                            "forgotten_revision": 2,
                            "forgotten_at": now,
                        },
                        {
                            "kind": "party",
                            "id": party[0],
                            "forgotten_revision": 2,
                            "forgotten_at": now,
                        },
                    ),
                )
                expected_manifest_hash = digest(
                    body
                )  # Retained by trusted synthetic producer.
                auth.write_signed(
                    path, Manifest(body=body, digest=expected_manifest_hash), key
                )
                older_body = body.model_copy(
                    update={"export_id": uuid4(), "items": body.items[:1]}
                )
                auth.write_signed(
                    older_path,
                    Manifest(body=older_body, digest=digest(older_body)),
                    key,
                )
            else:
                assert (
                    db.execute(
                        "SELECT count(*) FROM public.audit_events WHERE entity_id=%s AND event_type='admin.work_suppression_manifest_prepared'",
                        (str(workspace),),
                    ).fetchone()[0]
                    == 0
                )
        if phase == "container":
            recovered = Path(directory) / "recovered-key.json"
            auth.write_key(recovered, key)
            recovery_key_path.unlink()
            recovery_key_path = recovered
            key = auth.load_key(recovery_key_path, recovery_pin, workspace)
        verify_argv = [
            sys.executable,
            "-m",
            "app.work_suppression_auth",
            "verify",
            "--workspace",
            str(workspace),
            "--recovery-key",
            str(recovery_key_path),
            "--expected-key-fingerprint",
            recovery_pin,
            "--expected-manifest-hash",
            expected_manifest_hash,
            "--manifest",
            str(path),
        ]
        older_verify = subprocess.run(
            [*verify_argv[:-1], str(older_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert older_verify.returncode != 0 and not older_verify.stdout
        verified = subprocess.run(
            verify_argv, capture_output=True, text=True, check=False
        )
        assert verified.returncode == 0, (
            "Offline authenticated manifest verification failed"
        )
        verified_metadata = json.loads(verified.stdout)
        assert (
            verified_metadata["key_fingerprint"] == recovery_pin
            and not verified_metadata["recovery_complete"]
        )
        assert key.material.get_secret_value() not in verified.stdout + verified.stderr
        engine = create_engine(settings.database_url)
        with Session(engine) as db, db.begin():
            assert identity.resolve(db, token) is not None
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
        older = auth.read_signed(older_path, key, workspace)
        assert len(older.body.items) == 1 and older.digest != expected_manifest_hash
        # Valid old A under the very same key cannot stand in for retained checkpoint B.
        command(
            "app.work_suppression",
            "preview",
            "--manifest",
            str(older_path),
            success=False,
        )
        with psycopg.connect(url) as db:
            unchanged_note, unchanged_party = current(db)
            assert unchanged_note == selected and unchanged_party == party
            assert (
                db.execute(
                    "SELECT count(*) FROM public.audit_events WHERE entity_id=%s AND event_type='admin.work_suppression_applied'",
                    (str(workspace),),
                ).fetchone()[0]
                == 0
            )
        plan = command("app.work_suppression", "preview", "--manifest", str(path))
        assert plan["checkpoint"] == {
            "mode": "independently_pinned_manifest",
            "manifest_hash": expected_manifest_hash,
        }
        assert len(plan["items"]) == 2 and plan["linked_count"] == 4
        assert plan["authentication"]["key_fingerprint"] == recovery_pin
        arguments = (
            "apply",
            "--manifest",
            str(path),
            "--issued-at",
            plan["issued_at"],
            "--reviewed-hash",
            plan["reviewed_hash"],
            "--decision",
            "reconcile_restored_suppressions",
        )
        result = command("app.work_suppression", *arguments)
        assert not result["workspace_enabled"] and not result["recovery_complete"]
        assert result["authentication"]["key_id"] == str(key.key_id)
        assert key.material.get_secret_value() not in json.dumps(result)
        command("app.work_suppression", *arguments, success=False)
        with psycopg.connect(url) as db:
            assert (
                db.execute(
                    "SELECT is_active FROM public.work_workspaces WHERE id=%s",
                    (workspace,),
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
            assert db.execute(
                "SELECT state,snapshot->>'marker' FROM work.drafts WHERE workspace_id=%s AND id=%s",
                (workspace, selected[0]),
            ).fetchone() == ("forgotten", None)
            assert (
                db.execute(
                    "SELECT count(*) FROM work.draft_revisions WHERE workspace_id=%s AND record_id=%s AND snapshot IS NOT NULL",
                    (workspace, selected[0]),
                ).fetchone()[0]
                == 0
            )
            assert db.execute(
                "SELECT marker,state FROM work.parties WHERE workspace_id=%s",
                (workspace,),
            ).fetchone() == (None, "forgotten")
            assert (
                db.execute(
                    "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND (payload IS NOT NULL OR payload_hash IS NOT NULL)",
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
                    "SELECT count(*) FROM public.work_confirmation_requests WHERE workspace_id=%s AND state='pending'",
                    (workspace,),
                ).fetchone()[0]
                == 0
            )
            assert (
                db.execute(
                    "SELECT id,snapshot FROM work.drafts WHERE workspace_id=%s AND id=%s",
                    (workspace, control[0]),
                ).fetchone()
                == control
            )
            assert (
                db.execute(
                    "SELECT metadata_json FROM public.audit_events WHERE id=%s",
                    (result["receipt_id"],),
                ).fetchone()[0]
                == result
            )
        with Session(engine) as db, db.begin():
            assert identity.resolve(db, token) is None
        engine.dispose()
        # Exercise actual CLI export of now-real terminal rows in the migration container too.
        if phase == "container":
            exported = Path(directory) / "new-export.json"
            assert (
                command("app.work_suppression", "export", "--output", str(exported))[
                    "item_count"
                ]
                == 2
            )
            assert len(auth.read_signed(exported, key, workspace).body.items) == 2
        print(
            "Synthetic authenticated old-backup suppression/recovered-key/checkpoint/receipt verified; no material/payloads displayed"
        )
