"""Synthetic source and current/historical/pending derived-copy test fixtures."""

from datetime import timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb
from work_storage_helpers import connect, insert

from app import work_drafts, work_lifecycle
from app.manage import set_scope
from app.models import User


def prepare(case):
    with case["maker"].begin() as db:
        set_scope(db, db.get(User, case["actor"]), "technical_admin", True)
    other = insert(case["storage"])
    with connect() as db, db.transaction():
        db.execute(
            "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
            (case["workspace"], other),
        )

        def draft(source, marker):
            return work_lifecycle.Draft(
                kind="decision",
                marker=marker,
                source_ids=(source,),
                retain_until=case["item"].retain_until,
            )

        historical = work_drafts.create(
            db,
            case["workspace"],
            case["actor"],
            case["policy"],
            draft(case["source"], "synthetic:historical-dependency"),
        )
        historical = work_drafts.transition(
            db,
            case["workspace"],
            case["actor"],
            historical.id,
            1,
            "correct",
            draft(other, "synthetic:revised-other-source"),
        )
        control = work_drafts.create(
            db,
            case["workspace"],
            case["actor"],
            case["policy"],
            draft(other, "synthetic:unrelated-source"),
        )
        session = db.execute(
            "SELECT id FROM public.auth_sessions WHERE user_id=%s ORDER BY id LIMIT 1",
            (case["actor"],),
        ).fetchone()[0]

        def capture(source, target=None, intent="capture_draft"):
            payload = {
                "policy_id": str(case["policy"]),
                "draft": draft(source, "synthetic:pending-source-copy").model_dump(mode="json"),
            }
            return db.execute(
                "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,intent,target_record_id,expected_revision,payload,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp()+interval '4 minutes') RETURNING id",
                (
                    case["workspace"],
                    case["actor"],
                    session,
                    uuid4(),
                    intent,
                    target,
                    1 if target else None,
                    Jsonb(payload),
                ),
            ).fetchone()[0]

        pending = capture(case["source"])
        correction = capture(case["source"], control.id, "correct_note")
        unrelated = capture(other)
        review = db.execute(
            "INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash) SELECT workspace_id,id,revision,%s,%s,%s,'confirm_note',encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') FROM work.drafts WHERE workspace_id=%s AND id=%s RETURNING id,expires_at",
            (case["actor"], session, uuid4(), case["workspace"], case["item"].id),
        ).fetchone()
        confirmation = db.execute(
            "INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) VALUES(%s,%s,%s,1,%s,%s,%s,%s) RETURNING id",
            (
                case["workspace"],
                case["item"].id,
                review[0],
                case["actor"],
                session,
                uuid4(),
                review[1],
            ),
        ).fetchone()[0]
    case.update(
        other_source=other,
        historical=historical,
        control=control,
        pending=pending,
        correction=correction,
        unrelated=unrelated,
        review=review[0],
        confirmation=confirmation,
    )
    return case


def quarantine(case):
    with connect() as db:
        db.execute(
            "UPDATE public.work_workspaces SET is_active=false WHERE id=%s", (case["workspace"],)
        )
        db.execute(
            "DELETE FROM public.work_access_grants WHERE workspace_id=%s", (case["workspace"],)
        )


def extra_notes(case, count):
    with connect() as db, db.transaction():
        for _ in range(count):
            work_drafts.create(
                db,
                case["workspace"],
                case["actor"],
                case["policy"],
                work_lifecycle.Draft(
                    kind="observation",
                    marker="synthetic:capacity-case",
                    source_ids=(case["source"],),
                    retain_until=work_drafts._now(db) + timedelta(hours=1),
                ),
            )
