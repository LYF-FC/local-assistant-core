"""Disposable CI-only draft persistence/restore sentinel; never operator data."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from app import work_drafts, work_lifecycle, work_parties, work_capture
from app.config import settings
from app.work_storage import role_name

assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
workspace = UUID("88888888-8888-4888-8888-888888888888")
source = UUID("99999999-9999-4999-8999-999999999999")
policy = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
actor = UUID("22222222-2222-4222-8222-222222222222")
tables = ("retention_policies", "source_registry", "drafts", "draft_revisions", "draft_audit", "draft_tombstones", "draft_reviews", "draft_confirmations", "parties", "party_audit", "capture_intents", "capture_audit")
with psycopg.connect(settings.database_url.replace("postgresql+psycopg", "postgresql", 1)) as db:
    oid = db.execute("SELECT oid FROM pg_database WHERE datname=current_database()").fetchone()[0]
    role = role_name(oid, workspace)
    for table in tables:
        # Explicit synthetic restore inspector, not normal provisioning behavior.
        db.execute(sql.SQL("GRANT SELECT ON work.{} TO {}").format(sql.Identifier(table), sql.Identifier(role)))
    db.execute(sql.SQL("GRANT SELECT ON work.note_metadata TO {}").format(sql.Identifier(role)))
    if os.environ["BUTLER_DRAFT_RESTORE_PHASE"] == "seed":
        db.execute("INSERT INTO work.retention_policies VALUES(%s,%s,86400)", (workspace, policy))
        db.execute("INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)", (workspace, source))
        until = datetime.now(UTC) + timedelta(hours=1)
        active_party = work_parties.create(db, workspace, policy, "synthetic:restore-active-party", until)
        forgotten_party = work_parties.create(db, workspace, policy, "synthetic:restore-forgotten-party", until)
        retired_party = work_parties.create(db, workspace, policy, "synthetic:restore-retired-party", until)
        work_parties.transition(db, workspace, retired_party.id, 1, "retire")
        for marker in ("synthetic:restore-live-draft", "synthetic:restore-forgotten-draft"):
            payload = work_lifecycle.Draft(kind="decision", marker=marker, source_ids=(source,), owner_id=forgotten_party.id if "forgotten" in marker else active_party.id, retain_until=until)
            item = work_drafts.create(db, workspace, actor, policy, payload)
            digest = db.execute("SELECT encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') FROM work.drafts WHERE workspace_id=%s AND id=%s", (workspace,item.id)).fetchone()[0]
            receipt = db.execute("INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash) VALUES(%s,%s,%s,%s,%s,%s,'confirm_note',%s) RETURNING id,session_id,expires_at", (workspace,item.id,item.revision,actor,uuid4(),uuid4(),digest)).fetchone()
            command = db.execute("INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id", (workspace,item.id,receipt[0],1,actor,receipt[1],uuid4(),receipt[2])).fetchone()[0]
            if "forgotten" in marker:
                item = work_drafts.transition(db, workspace, actor, item.id, item.revision, "confirm")
                db.execute("INSERT INTO work.draft_confirmations(workspace_id,request_id,review_preparation_id,record_id,reviewed_revision,confirmed_revision,actor_id,session_id) VALUES(%s,%s,%s,%s,1,2,%s,%s)", (workspace,command,receipt[0],item.id,actor,receipt[1]))
                db.execute("UPDATE public.work_confirmation_requests SET state='applied',applied_revision=2,finished_at=clock_timestamp() WHERE id=%s", (command,))
                work_drafts.transition(db, workspace, actor, item.id, item.revision, "forget")
                work_parties.transition(db, workspace, forgotten_party.id, 1, "forget")
        live_id = db.execute("SELECT id FROM work.drafts WHERE workspace_id=%s AND state='draft'", (workspace,)).fetchone()[0]
        # Metadata-only issuance receipt sentinel; no archive payload is backed up here.
        db.execute("INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,scope_key,event_type,entity_type,entity_id,result_status,metadata_json) VALUES(%s,clock_timestamp(),'test','system','synthetic-export-restore','technical_admin','work.notes_export_download_prepared','work_access_registry',%s,'success',%s)", (UUID("edededed-eded-4ded-8ded-edededededed"),str(workspace),Jsonb({"export_id":"efefefef-efef-4fef-8fef-efefefefefef","records":[{"id":str(live_id),"revision":1}],"bundle_bytes":2048,"retain_until":until.isoformat(),"drafts_permitted":True})))
        capture_payload = work_capture.Payload(policy_id=policy, draft=work_capture.Draft(kind="action",marker="synthetic:restore-capture",source_ids=(source,),retain_until=until)).model_dump(mode="json")
        for outcome in ("pending","applied","denied"):
            capture_id = db.execute("INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,payload,expires_at) VALUES(%s,%s,%s,%s,%s,clock_timestamp()+interval '4 minutes') RETURNING id", (workspace,actor,uuid4(),uuid4(),Jsonb(capture_payload))).fetchone()[0]
            if outcome!='pending':
                db.execute("UPDATE work.capture_intents SET state=%s,payload=NULL,record_id=%s,reason_code=%s,finished_at=clock_timestamp() WHERE id=%s", (outcome,live_id if outcome=='applied' else None,'expired' if outcome=='denied' else None,capture_id))
        forgotten_id = db.execute("SELECT id FROM work.drafts WHERE workspace_id=%s AND state='forgotten'", (workspace,)).fetchone()[0]
        for intent,outcome in (("correct_note","pending"),("correct_note","denied"),("forget_note","applied")):
            request = db.execute("INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,intent,target_record_id,expected_revision,payload,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp()+interval '4 minutes') RETURNING id", (workspace,actor,uuid4(),uuid4(),intent,forgotten_id if intent=='forget_note' else live_id,2 if intent=='forget_note' else 1,Jsonb({"forget":True} if intent=='forget_note' else capture_payload))).fetchone()[0]
            if outcome!='pending':
                db.execute("UPDATE work.capture_intents SET state=%s,payload=NULL,record_id=%s,reason_code=%s,finished_at=clock_timestamp() WHERE id=%s", (outcome,forgotten_id if outcome=='applied' else None,'stale' if outcome=='denied' else None,request))
    else:
        export_meta = db.execute("SELECT metadata_json FROM public.audit_events WHERE id='edededed-eded-4ded-8ded-edededededed' AND event_type='work.notes_export_download_prepared' AND entity_id=%s", (str(workspace),)).fetchone()[0]
        assert export_meta["export_id"] == "efefefef-efef-4fef-8fef-efefefefefef" and export_meta["bundle_bytes"] == 2048
        assert len(export_meta["records"]) == 1 and export_meta["records"][0]["revision"] == 1
        assert set(export_meta) == {"export_id","records","bundle_bytes","retain_until","drafts_permitted"}
        assert db.execute("SELECT array_agg(state ORDER BY state) FROM work.capture_intents WHERE workspace_id=%s AND intent<>'capture_draft'", (workspace,)).fetchone()[0] == ['applied','denied','pending']
        assert db.execute("SELECT result_revision FROM work.capture_intents WHERE workspace_id=%s AND intent='forget_note'", (workspace,)).fetchone()[0] == 3
        assert db.execute("SELECT array_agg(state ORDER BY state) FROM work.capture_intents WHERE workspace_id=%s AND intent='capture_draft'", (workspace,)).fetchone()[0] == ['applied','denied','pending']
        assert db.execute("SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND state<>'pending' AND (payload IS NOT NULL OR payload_hash IS NOT NULL)", (workspace,)).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND state='pending' AND payload_hash IS NOT NULL", (workspace,)).fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM work.capture_audit WHERE workspace_id=%s", (workspace,)).fetchone()[0] == 10
        assert db.execute("SELECT array_agg(state ORDER BY state) FROM work.parties WHERE workspace_id=%s", (workspace,)).fetchone()[0] == ['active','forgotten','retired']
        assert db.execute("SELECT marker FROM work.parties WHERE workspace_id=%s AND state='forgotten'", (workspace,)).fetchone()[0] is None
        assert db.execute("SELECT count(*) FROM work.party_audit WHERE workspace_id=%s", (workspace,)).fetchone()[0] == 5
        assert db.execute("SELECT count(*) FROM work.drafts d JOIN work.parties p ON p.workspace_id=d.workspace_id AND p.id=(d.snapshot->>'owner_id')::uuid WHERE d.workspace_id=%s AND p.state='active'", (workspace,)).fetchone()[0] == 1
        try:
            with db.transaction():
                db.execute("UPDATE work.parties SET state='active',revision=revision+1 WHERE state='retired'")
        except psycopg.errors.CheckViolation:
            pass
        else:
            raise AssertionError("Restored party reactivation permitted")
        assert db.execute("SELECT count(*) FROM work.draft_confirmations WHERE workspace_id=%s", (workspace,)).fetchone()[0] == 1
        assert db.execute("SELECT array_agg(state ORDER BY state) FROM public.work_confirmation_requests WHERE workspace_id=%s", (workspace,)).fetchone()[0] == ['applied','pending']
        try:
            with db.transaction():
                db.execute("UPDATE work.draft_confirmations SET actor_id=actor_id")
        except psycopg.errors.CheckViolation:
            pass
        else:
            raise AssertionError("Restored consumption mutation permitted")
        assert db.execute("SELECT count(*) FROM work.drafts WHERE workspace_id=%s AND snapshot->>'marker'='synthetic:restore-live-draft'", (workspace,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM work.draft_tombstones WHERE workspace_id=%s", (workspace,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM work.draft_revisions r JOIN work.drafts d ON d.workspace_id=r.workspace_id AND d.id=r.record_id WHERE d.workspace_id=%s AND d.state='forgotten' AND r.snapshot IS NOT NULL", (workspace,)).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM work.draft_audit WHERE workspace_id=%s", (workspace,)).fetchone()[0] == 6
        assert db.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='work' AND c.relname=ANY(%s) AND c.relrowsecurity AND c.relforcerowsecurity", (list(tables),)).fetchone()[0] == 12
        assert db.execute("SELECT count(*) FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NULL", (workspace,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NOT NULL", (workspace,)).fetchone()[0] == 1
        source_oid = int(os.environ["BUTLER_DRAFT_SOURCE_OID"])
        db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role_name(source_oid, workspace))))
        for table in tables:
            assert db.execute(sql.SQL("SELECT count(*) FROM work.{}").format(sql.Identifier(table))).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM work.note_metadata").fetchone()[0] == 0
        db.execute("RESET ROLE")
        db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
        assert db.execute("SELECT count(*) FROM work.note_metadata").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM work.drafts").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM work.draft_revisions WHERE snapshot IS NULL").fetchone()[0] == 3
print("Synthetic draft/party/capture/note-change/export-receipt restore sentinel verified; no payloads displayed")
