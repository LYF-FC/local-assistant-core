"""Synthetic old-dump source withdrawal and post-cleanup restore verification."""

import json
import subprocess
import sys
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

import psycopg
from psycopg.types.json import Jsonb

from app import identity, work_drafts, work_lifecycle
from app.config import settings

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
phase = sys.argv[1]
assert phase in {"seed", "check", "preserved", "container"}
url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)


def identifier(label):
    return uuid5(NAMESPACE_URL, "butler-synthetic-source-withdrawal-" + label)


workspace, actor, policy, source, other = [
    identifier(label) for label in ("workspace", "actor", "policy", "source", "other")
]


def draft(db, selected, marker):
    return work_lifecycle.Draft(
        kind="decision",
        marker=marker,
        source_ids=(selected,),
        retain_until=work_drafts._now(db) + timedelta(hours=1),
    )


if phase in {"seed", "container"}:
    with psycopg.connect(url) as db, db.transaction():
        db.execute(
            "INSERT INTO public.users(id,slug,display_name,is_active,created_at,updated_at) VALUES(%s,'synthetic-source-withdrawal','Synthetic',true,now(),now())",
            (actor,),
        )
        db.execute(
            "INSERT INTO public.user_scopes(user_id,scope_id,created_at) SELECT %s,id,now() FROM public.scopes WHERE key='technical_admin'",
            (actor,),
        )
        db.execute(
            "INSERT INTO public.auth_sessions(id,user_id,token_hash,csrf_hash,created_at,last_seen_at,expires_at) VALUES(%s,%s,%s,%s,now(),now(),now()+interval '1 hour')",
            (
                identifier("session"),
                actor,
                identity.digest("synthetic-source-session-only-" + "a" * 48),
                identity.digest("synthetic-source-csrf-only-" + "b" * 48),
            ),
        )
        db.execute(
            "INSERT INTO public.work_workspaces(id,slug,is_active,created_at) VALUES(%s,'synthetic-source-withdrawal',true,now())",
            (workspace,),
        )
        db.execute("INSERT INTO work.retention_policies VALUES(%s,%s,86400)", (workspace, policy))
        for selected in (source, other):
            db.execute(
                "INSERT INTO work.validation_records(workspace_id,id,marker) VALUES(%s,%s,'synthetic:source-reference')",
                (workspace, selected),
            )
            db.execute(
                "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
                (workspace, selected),
            )
        direct = work_drafts.create(
            db, workspace, actor, policy, draft(db, source, "synthetic:source-derived-current")
        )
        historical = work_drafts.create(
            db, workspace, actor, policy, draft(db, source, "synthetic:source-derived-history")
        )
        work_drafts.transition(
            db,
            workspace,
            actor,
            historical.id,
            1,
            "correct",
            work_lifecycle.Draft(
                kind="decision",
                marker="synthetic:source-corrected-other",
                source_ids=(other,),
                retain_until=historical.retain_until,
            ),
        )
        work_drafts.create(
            db, workspace, actor, policy, draft(db, other, "synthetic:source-unrelated-control")
        )
        for name, selected in (("capture", source), ("control-capture", other)):
            db.execute(
                "INSERT INTO work.capture_intents(id,workspace_id,actor_id,session_id,request_id,payload,expires_at) VALUES(%s,%s,%s,%s,%s,%s,now()+interval '4 minutes')",
                (
                    identifier(name),
                    workspace,
                    actor,
                    identifier("session"),
                    uuid4(),
                    Jsonb(
                        {
                            "policy_id": str(policy),
                            "draft": draft(
                                db, selected, "synthetic:source-pending-copy"
                            ).model_dump(mode="json"),
                        }
                    ),
                ),
            )


def verify():
    with psycopg.connect(url) as db:
        assert db.execute(
            "SELECT is_active FROM public.work_workspaces WHERE id=%s", (workspace,)
        ).fetchone() == (False,)
        assert not db.execute(
            "SELECT 1 FROM public.work_access_grants WHERE workspace_id=%s", (workspace,)
        ).fetchone()
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (workspace, source),
        ).fetchone() == (False,)
        assert db.execute(
            "SELECT is_active FROM work.source_registry WHERE workspace_id=%s AND id=%s",
            (workspace, other),
        ).fetchone() == (True,)
        assert db.execute(
            "SELECT count(*) FROM work.drafts WHERE workspace_id=%s AND state='forgotten' AND snapshot->>'marker' IS NULL AND snapshot->'source_ids'='[]'::jsonb",
            (workspace,),
        ).fetchone() == (2,)
        assert db.execute(
            "SELECT count(*) FROM work.drafts WHERE workspace_id=%s AND state='draft' AND snapshot->>'marker'='synthetic:source-unrelated-control'",
            (workspace,),
        ).fetchone() == (1,)
        assert db.execute(
            "SELECT count(*) FROM work.draft_revisions r JOIN work.drafts d ON d.workspace_id=r.workspace_id AND d.id=r.record_id WHERE d.workspace_id=%s AND d.state='forgotten' AND r.snapshot IS NOT NULL",
            (workspace,),
        ).fetchone() == (0,)
        assert db.execute(
            "SELECT state,payload,payload_hash FROM work.capture_intents WHERE id=%s",
            (identifier("capture"),),
        ).fetchone() == ("denied", None, None)
        assert db.execute(
            "SELECT state,payload IS NOT NULL FROM work.capture_intents WHERE id=%s",
            (identifier("control-capture"),),
        ).fetchone() == ("pending", True)
        assert db.execute(
            "SELECT count(*) FROM work.validation_records WHERE workspace_id=%s AND marker='synthetic:source-reference'",
            (workspace,),
        ).fetchone() == (2,)
        receipt = db.execute(
            "SELECT metadata_json FROM public.audit_events WHERE entity_id=%s AND event_type='admin.work_sources_withdrawn'",
            (str(workspace),),
        ).fetchall()
        assert len(receipt) == 1 and len(receipt[0][0]["forgotten_notes"]) == 2
        assert not receipt[0][0]["recovery_complete"] and not receipt[0][0]["activation_authorized"]


if phase in {"check", "container"}:
    with psycopg.connect(url) as db:
        db.execute("UPDATE public.work_workspaces SET is_active=false WHERE id=%s", (workspace,))
        db.execute("DELETE FROM public.work_access_grants WHERE workspace_id=%s", (workspace,))
    base = [
        sys.executable,
        "-m",
        "app.work_source_withdrawal",
        "--environment",
        "test",
        "--database",
        settings.postgres_db,
        "--operator",
        str(actor),
        "--workspace",
        str(workspace),
        "--source",
        str(source),
    ]

    def cli(flags=(), success=True):
        result = subprocess.run([*base, *flags], capture_output=True, text=True, timeout=30)
        assert (result.returncode == 0) == success, "Synthetic source command failed"
        assert "synthetic:source-" not in result.stdout + result.stderr
        return json.loads(result.stdout) if success else None

    plan = cli()
    assert len(plan["notes"]) == 2 and len(plan["linked"]) == 1
    assert any(
        item["historical_reference"] and not item["current_reference"] for item in plan["notes"]
    )
    flags = [
        "--issued-at",
        plan["issued_at"],
        "--reviewed-hash",
        plan["reviewed_hash"],
        "--decision",
        "withdraw_sources",
    ]
    receipt = cli(flags)
    assert len(receipt["forgotten_notes"]) == 2
    cli(flags, success=False)
    after = cli()
    assert not after["notes"] and not after["linked"]
    verify()
    print(
        "Synthetic source withdrawal CLI/current-history redaction/pending-copy/control/receipt verified"
    )
elif phase == "preserved":
    verify()
    print(
        "Post-withdrawal source flags, redacted history, pending-copy denial and unrelated controls preserved in new restore"
    )
