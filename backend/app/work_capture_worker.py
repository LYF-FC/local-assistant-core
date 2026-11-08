"""Manual local synthetic draft capture; no daemon, API owner connection or inference."""

import argparse
from datetime import timedelta
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app import work_capture, work_drafts
from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import validate_target


def _one(db, query, values=()):
    with db.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, values).fetchone()


def _result(row):
    return {
        "state": row["state"],
        "record_id": str(row["record_id"]) if row["record_id"] else None,
        "revision": 1 if row["state"] == "applied" else None,
    }


def _finish(db, row, reason=None, record_id=None):
    state = "denied" if reason else "applied"
    updated = _one(
        db,
        "UPDATE work.capture_intents SET state=%s,record_id=%s,reason_code=%s,payload=NULL,finished_at=clock_timestamp() WHERE workspace_id=%s AND id=%s RETURNING *",
        (state, record_id, reason, row["workspace_id"], row["id"]),
    )
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(gen_random_uuid(),clock_timestamp(),%s,'local_admin','trusted_host_operator','synthetic_draft_capture','technical_admin','work.capture_finished','work_access_registry',%s,%s,'{}',%s)",
        (
            settings.env,
            str(row["workspace_id"]),
            "denied" if reason else "success",
            Jsonb({"capture_preparation_id": str(row["id"]), "state": state}),
        ),
    )
    return _result(updated)


def _expired(db, row, session, *deadlines):
    now = work_drafts._now(db)
    return now >= min(row["expires_at"], session["expires_at"], *deadlines) or now - session[
        "last_seen_at"
    ] >= timedelta(minutes=30)


def execute(db, command: UUID):
    validate_target(settings.env)
    if (
        not isinstance(command, UUID)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Explicit typed local capture transaction required")
    if db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.drafts'::regclass),current_user=(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.capture_intents'::regclass)"
    ).fetchone() != (True, "read committed", True, True):
        raise ValueError("Clean local draft/capture storage owner required")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    hint = _one(
        db,
        "SELECT actor_id,session_id FROM work.capture_intents WHERE intent='capture_draft' AND id=%s",
        (command,),
    )
    if hint is None:
        raise ValueError("Synthetic capture unavailable")
    db.execute("SELECT pg_advisory_xact_lock_shared(%s,%s)", REGISTRY_KEY)
    user = _one(db, "SELECT is_active FROM public.users WHERE id=%s FOR SHARE", (hint["actor_id"],))
    session = _one(
        db, "SELECT * FROM public.auth_sessions WHERE id=%s FOR UPDATE", (hint["session_id"],)
    )
    row = _one(
        db,
        "SELECT * FROM work.capture_intents WHERE intent='capture_draft' AND id=%s FOR UPDATE",
        (command,),
    )
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
    proof = db.execute(
        "SELECT 1 FROM public.audit_events WHERE environment=%s AND initiator_type='human' AND initiator_id=%s AND event_type='work.capture_requested' AND result_status='success' AND entity_type='work_access_registry' AND entity_id=%s AND metadata_json::jsonb @> %s LIMIT 1",
        (
            settings.env,
            str(row["actor_id"]),
            str(row["workspace_id"]),
            Jsonb({"capture_preparation_id": str(row["id"]), "session_id": str(row["session_id"])}),
        ),
    ).fetchone()
    if not proof:
        return _finish(db, row, "evidence")
    try:
        content = work_capture.Payload.model_validate(row["payload"])
    except ValidationError:
        return _finish(db, row, "stale")
    policy = db.execute(
        "SELECT max_age_seconds FROM work.retention_policies WHERE workspace_id=%s AND id=%s FOR SHARE",
        (row["workspace_id"], content.policy_id),
    ).fetchone()
    now = work_drafts._now(db)
    if not policy or not now < content.draft.retain_until <= now + timedelta(seconds=policy[0]):
        return _finish(db, row, "stale")
    sources = db.execute(
        "SELECT id FROM work.source_registry WHERE workspace_id=%s AND is_active AND id=ANY(%s) ORDER BY id FOR SHARE",
        (row["workspace_id"], list(content.draft.source_ids)),
    ).fetchall()
    if {item[0] for item in sources} != set(content.draft.source_ids):
        return _finish(db, row, "stale")
    deadlines = [content.draft.retain_until]
    if content.draft.owner_id is not None:
        party = db.execute(
            "SELECT retain_until FROM work.parties WHERE workspace_id=%s AND id=%s AND state='active' AND retain_until>clock_timestamp() FOR SHARE",
            (row["workspace_id"], content.draft.owner_id),
        ).fetchone()
        if party is None:
            return _finish(db, row, "stale")
        deadlines.append(party[0])
    if _expired(db, row, session, *deadlines):
        return _finish(db, row, "expired")
    item = work_drafts.create(
        db, row["workspace_id"], row["actor_id"], content.policy_id, content.draft
    )
    result = _finish(db, row, record_id=item.id)
    if _expired(db, row, session, *deadlines):
        raise ValueError("Capture expired during write; roll back")
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
            1, "Synthetic capture failed; rolled back, reconcile metadata before deliberate retry\n"
        )
    print(
        f"Synthetic capture outcome: {result['state']}; record {result['record_id']}; no confirmation or execution"
    )


if __name__ == "__main__":
    main()
