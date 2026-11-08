"""Explicit one-shot local synthetic executor; never an API dependency or daemon."""

import argparse
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import work_drafts
from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import validate_target


def _one(db, query, parameters=()):
    with db.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, parameters).fetchone()


def _proof(db, request, event, *, enqueue=False):
    metadata = {
        "record_id": str(request["record_id"]),
        "revision": request["reviewed_revision"],
        "review_preparation_id": str(request["review_preparation_id"]),
        "session_id": str(request["session_id"]),
    }
    if enqueue:
        metadata["confirmation_request_id"] = str(request["id"])
    return (
        db.execute(
            "SELECT 1 FROM public.audit_events WHERE environment=%s AND initiator_type='human' AND initiator_id=%s AND entity_type='work_access_registry' AND entity_id=%s AND event_type=%s AND result_status='success' AND metadata_json::jsonb @> %s LIMIT 1",
            (
                settings.env,
                str(request["actor_id"]),
                str(request["workspace_id"]),
                event,
                Jsonb(metadata),
            ),
        ).fetchone()
        is not None
    )


def _finish(db, request, *, reason=None, revision=None):
    state = "denied" if reason else "applied"
    db.execute(
        "UPDATE public.work_confirmation_requests SET state=%s,reason_code=%s,applied_revision=%s,finished_at=clock_timestamp() WHERE id=%s",
        (state, reason, revision, request["id"]),
    )
    db.execute(
        "INSERT INTO public.audit_events(id,occurred_at,environment,initiator_type,initiator_id,worker,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES(gen_random_uuid(),clock_timestamp(),%s,'local_admin','trusted_host_operator','synthetic_note_confirmation','technical_admin','work.draft_confirmation_finished','work_access_registry',%s,%s,'{}',%s)",
        (
            settings.env,
            str(request["workspace_id"]),
            "success" if state == "applied" else "denied",
            Jsonb({"confirmation_request_id": str(request["id"]), "state": state}),
        ),
    )
    return {"state": state, "applied_revision": revision}


def _expired(db, request, session, *deadlines):
    now = work_drafts._now(db)
    return (
        now >= min(request["expires_at"], session["expires_at"], *deadlines)
        or (now - session["last_seen_at"]).total_seconds() >= 1800
    )


def execute(db, request_id: UUID):
    """Caller owns commit/rollback; business and outcome changes share one transaction."""
    validate_target(settings.env)
    if (
        not isinstance(request_id, UUID)
        or db.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS
    ):
        raise ValueError("Explicit typed local transaction required")
    if db.execute(
        "SELECT session_user=current_user,current_setting('transaction_isolation'),current_user=pg_get_userbyid(relowner) FROM pg_class WHERE oid='work.drafts'::regclass"
    ).fetchone() != (True, "read committed", True):
        raise ValueError("Clean local storage owner required")
    db.execute("SET LOCAL lock_timeout='2s'")
    db.execute("SET LOCAL statement_timeout='5s'")
    hint = _one(
        db,
        "SELECT actor_id,session_id FROM public.work_confirmation_requests WHERE id=%s",
        (request_id,),
    )
    if hint is None:
        raise ValueError("Synthetic request unavailable")
    db.execute("SELECT pg_advisory_xact_lock_shared(%s,%s)", REGISTRY_KEY)
    user = _one(db, "SELECT is_active FROM public.users WHERE id=%s FOR SHARE", (hint["actor_id"],))
    session = _one(
        db, "SELECT * FROM public.auth_sessions WHERE id=%s FOR UPDATE", (hint["session_id"],)
    )
    request = _one(
        db, "SELECT * FROM public.work_confirmation_requests WHERE id=%s FOR UPDATE", (request_id,)
    )
    if request["state"] != "pending":
        return {"state": request["state"], "applied_revision": request["applied_revision"]}
    if (
        not user
        or not user["is_active"]
        or not session
        or session["user_id"] != request["actor_id"]
        or session["revoked_at"] is not None
        or not db.execute(
            "SELECT 1 FROM public.work_workspaces w JOIN public.work_access_grants g ON g.workspace_id=w.id WHERE w.id=%s AND w.is_active AND w.slug LIKE 'synthetic-%%' AND g.user_id=%s AND g.capability='work_private'",
            (request["workspace_id"], request["actor_id"]),
        ).fetchone()
    ):
        return _finish(db, request, reason="authority")
    if _expired(db, request, session):
        return _finish(db, request, reason="expired")
    if not _proof(db, request, "work.draft_review_recorded") or not _proof(
        db, request, "work.draft_confirmation_requested", enqueue=True
    ):
        return _finish(db, request, reason="evidence")
    item = _one(
        db,
        "SELECT *,encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') AS payload_hash FROM work.drafts WHERE workspace_id=%s AND id=%s FOR UPDATE",
        (request["workspace_id"], request["record_id"]),
    )
    receipt = _one(
        db,
        "SELECT * FROM work.draft_reviews WHERE workspace_id=%s AND id=%s FOR UPDATE",
        (request["workspace_id"], request["review_preparation_id"]),
    )
    if _expired(db, request, session):
        return _finish(db, request, reason="expired")
    now = work_drafts._now(db)
    if (
        not item
        or not receipt
        or item["state"] != "draft"
        or item["revision"] != request["reviewed_revision"]
        or item["retain_until"] <= now
        or receipt["expires_at"] <= now
        or receipt["record_id"] != request["record_id"]
        or receipt["revision"] != request["reviewed_revision"]
        or receipt["actor_id"] != request["actor_id"]
        or receipt["session_id"] != request["session_id"]
        or receipt["intent"] != "confirm_note"
        or receipt["payload_hash"] is None
        or receipt["payload_hash"] != item["payload_hash"]
        or not item["snapshot"]["source_ids"]
        or db.execute(
            "SELECT 1 FROM work.draft_confirmations WHERE workspace_id=%s AND review_preparation_id=%s",
            (request["workspace_id"], request["review_preparation_id"]),
        ).fetchone()
    ):
        return _finish(db, request, reason="stale")
    sources = db.execute(
        "SELECT id FROM work.source_registry WHERE workspace_id=%s AND is_active AND id=ANY(%s::uuid[]) ORDER BY id FOR SHARE",
        (request["workspace_id"], item["snapshot"]["source_ids"]),
    ).fetchall()
    if {str(row[0]) for row in sources} != set(item["snapshot"]["source_ids"]):
        return _finish(db, request, reason="stale")
    owner_id = item["snapshot"]["owner_id"]
    if (
        owner_id is not None
        and not db.execute(
            "SELECT 1 FROM work.parties WHERE workspace_id=%s AND id=%s AND state='active' AND retain_until>clock_timestamp() FOR SHARE",
            (request["workspace_id"], owner_id),
        ).fetchone()
    ):
        return _finish(db, request, reason="stale")
    if _expired(db, request, session, receipt["expires_at"], item["retain_until"]):
        return _finish(db, request, reason="expired")
    confirmed = work_drafts.transition(
        db,
        request["workspace_id"],
        request["actor_id"],
        request["record_id"],
        request["reviewed_revision"],
        "confirm",
    )
    db.execute(
        "INSERT INTO work.draft_confirmations(workspace_id,request_id,review_preparation_id,record_id,reviewed_revision,confirmed_revision,actor_id,session_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            request["workspace_id"],
            request_id,
            request["review_preparation_id"],
            request["record_id"],
            request["reviewed_revision"],
            confirmed.revision,
            request["actor_id"],
            request["session_id"],
        ),
    )
    result = _finish(db, request, revision=confirmed.revision)
    if _expired(db, request, session, receipt["expires_at"], item["retain_until"]):
        raise ValueError("Confirmation expired during write; roll back")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--request", required=True, type=UUID)
    args = parser.parse_args()
    validate_target(args.environment)
    try:
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
            1,
            "Synthetic confirmation failed; transaction rolled back, inspect metadata before deliberate retry\n",
        )
    print(f"Synthetic confirmation outcome: {result['state']}; no execution authorized")


if __name__ == "__main__":
    main()
