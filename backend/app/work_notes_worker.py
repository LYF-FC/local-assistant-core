"""Manual atomic synthetic correction/forget; no API owner credentials or daemon."""

import argparse
from datetime import timedelta
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app import work_capture, work_drafts
from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_capture_worker import _expired, _one
from app.work_credentials import validate_target


def _result(row):
    return {
        "state": row["state"],
        "record_id": str(row["record_id"]) if row["record_id"] else None,
        "revision": row["result_revision"],
    }


def _finish(db, row, reason=None):
    state = "denied" if reason else "applied"
    updated = _one(
        db,
        "UPDATE work.capture_intents SET state=%s,record_id=%s,reason_code=%s,payload=NULL,finished_at=clock_timestamp() WHERE id=%s RETURNING *",
        (state, None if reason else row["target_record_id"], reason, row["id"]),
    )
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(gen_random_uuid(),clock_timestamp(),%s,'local_admin','trusted_host_operator','synthetic_note_change','technical_admin','work.note_change_finished','work_access_registry',%s,%s,'{}',%s)",
        (
            settings.env,
            str(row["workspace_id"]),
            "denied" if reason else "success",
            Jsonb({"change_request_id": str(row["id"]), "state": state}),
        ),
    )
    return _result(updated)


def _content(db, row, current):
    try:
        content = work_capture.Payload.model_validate(row["payload"])
    except ValidationError:
        return None
    if (
        str(content.policy_id) != current["snapshot"]["policy_id"]
        or content.draft.kind != current["snapshot"]["kind"]
        or current["retain_until"] is None
        or not work_drafts._now(db) < content.draft.retain_until <= current["retain_until"]
    ):
        return None
    policy = db.execute(
        "SELECT max_age_seconds FROM work.retention_policies WHERE workspace_id=%s AND id=%s FOR SHARE",
        (row["workspace_id"], content.policy_id),
    ).fetchone()
    if not policy or content.draft.retain_until > work_drafts._now(db) + timedelta(
        seconds=policy[0]
    ):
        return None
    selected_sources = set(content.draft.source_ids) | {
        UUID(value) for value in current["snapshot"]["source_ids"]
    }
    sources = db.execute(
        "SELECT id FROM work.source_registry WHERE workspace_id=%s AND is_active AND id=ANY(%s) ORDER BY id FOR SHARE",
        (row["workspace_id"], list(selected_sources)),
    ).fetchall()
    if {value[0] for value in sources} != selected_sources:
        return None
    deadlines = [content.draft.retain_until, current["retain_until"]]
    if content.draft.owner_id is not None:
        party = db.execute(
            "SELECT retain_until FROM work.parties WHERE workspace_id=%s AND id=%s AND state='active' AND retain_until>clock_timestamp() FOR SHARE",
            (row["workspace_id"], content.draft.owner_id),
        ).fetchone()
        if party is None:
            return None
        deadlines.append(party[0])
    return content, deadlines


def execute(db, command: UUID):
    validate_target(settings.env)
    if (
        not isinstance(command, UUID)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Explicit typed local note-change transaction required")
    if db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.drafts'::regclass),current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.capture_intents'::regclass)"
    ).fetchone() != (True, "read committed", True, True):
        raise ValueError("Clean local note/intent storage owner required")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    # Exclusive before all row locks: forgetting can cancel other sessions' pending corrections.
    db.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
    hint = _one(
        db,
        "SELECT actor_id,session_id FROM work.capture_intents WHERE id=%s AND intent IN ('correct_note','forget_note')",
        (command,),
    )
    if hint is None:
        raise ValueError("Synthetic note change unavailable")
    user = _one(db, "SELECT is_active FROM public.users WHERE id=%s FOR SHARE", (hint["actor_id"],))
    session = _one(
        db, "SELECT * FROM public.auth_sessions WHERE id=%s FOR UPDATE", (hint["session_id"],)
    )
    row = _one(db, "SELECT * FROM work.capture_intents WHERE id=%s FOR UPDATE", (command,))
    if row["state"] != "pending":
        return _result(row)
    if (
        not user
        or not user["is_active"]
        or not session
        or session["user_id"] != row["actor_id"]
        or session["revoked_at"] is not None
        or not db.execute(
            "SELECT 1 FROM public.work_workspaces w JOIN public.work_access_grants g ON g.workspace_id=w.id WHERE w.id=%s AND w.is_active AND w.slug LIKE 'synthetic-%%' AND g.user_id=%s AND g.capability='work_private'",
            (row["workspace_id"], row["actor_id"]),
        ).fetchone()
    ):
        return _finish(db, row, "authority")
    if _expired(db, row, session):
        return _finish(db, row, "expired")
    if not db.execute(
        "SELECT 1 FROM public.audit_events WHERE environment=%s AND initiator_type='human' AND initiator_id=%s AND event_type='work.note_change_requested' AND result_status='success' AND entity_type='work_access_registry' AND entity_id=%s AND metadata_json::jsonb @> %s LIMIT 1",
        (
            settings.env,
            str(row["actor_id"]),
            str(row["workspace_id"]),
            Jsonb({"change_request_id": str(row["id"]), "session_id": str(row["session_id"])}),
        ),
    ).fetchone():
        return _finish(db, row, "evidence")
    current = _one(
        db,
        "SELECT * FROM work.drafts WHERE workspace_id=%s AND id=%s FOR UPDATE",
        (row["workspace_id"], row["target_record_id"]),
    )
    if (
        current is None
        or current["state"] == "forgotten"
        or current["revision"] != row["expected_revision"]
    ):
        return _finish(db, row, "stale")
    deadlines = []
    payload = None
    if row["intent"] == "correct_note":
        validated = _content(db, row, current)
        if validated is None:
            return _finish(db, row, "stale")
        content, deadlines = validated
        payload = content.draft
    elif row["payload"] != {"forget": True}:
        return _finish(db, row, "stale")
    if _expired(db, row, session, *deadlines):
        return _finish(db, row, "expired")
    item = work_drafts.transition(
        db,
        row["workspace_id"],
        row["actor_id"],
        row["target_record_id"],
        row["expected_revision"],
        "correct" if payload is not None else "forget",
        payload,
    )
    if item.revision != row["expected_revision"] + 1:
        raise ValueError("Unexpected note result revision; roll back")
    result = _finish(db, row)
    if _expired(db, row, session, *deadlines):
        raise ValueError("Note change expired during write; roll back")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--request", required=True, type=UUID)
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        with (
            psycopg.connect(
                settings.database_url.replace("postgresql+psycopg", "postgresql", 1),
                connect_timeout=3,
            ) as db,
            db.transaction(),
        ):
            result = execute(db, args.request)
    except (psycopg.Error, ValueError):
        parser.exit(
            1, "Synthetic note change failed; rolled back, reconcile before deliberate retry\n"
        )
    print(
        f"Synthetic note change: {result['state']}; revision {result['revision']}; no execution authorized"
    )


if __name__ == "__main__":
    main()
