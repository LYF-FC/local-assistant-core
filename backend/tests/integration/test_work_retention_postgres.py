"""Actual guarded expiry cleanup, exact plans, audit rollback and serialization."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb
from work_migration_helpers import assert_downgrade_refused
from work_storage_helpers import PASSWORD, connect

from app import work_capture, work_drafts, work_lifecycle, work_parties, work_retention
from app.manage import set_scope
from app.models import User
from app.work_manage import administer

pytestmark = pytest.mark.integration


def run(case, **changes):
    with connect() as db, db.transaction():
        return work_retention.reconcile(
            db,
            work_retention.Request(
                workspace_id=case["workspace"], operator_id=case["actor"], **changes
            ),
        )


def apply(case, plan, **changes):
    return run(
        case,
        cutoff=datetime.fromisoformat(plan["cutoff"]),
        limit=plan["limit"],
        reviewed_hash=plan["reviewed_hash"],
        decision="apply_expired_cleanup",
        **changes,
    )


def disable(case):
    with case["maker"].begin() as db:
        administer(db, "disable", case["slug"])


def grant(case):
    with case["maker"].begin() as db:
        set_scope(db, db.get(User, case["actor"]), "technical_admin", True)


def seed(case, *, linked=1):
    """Real expiry, no guard bypass or historical payload resurrection."""
    grant(case)
    with connect() as db, db.transaction():
        short = datetime.now(UTC) + timedelta(seconds=2)
        live = datetime.now(UTC) + timedelta(hours=1)
        payload = work_lifecycle.Draft(
            kind="action",
            marker="synthetic:expiry-secret",
            source_ids=(case["source"],),
            retain_until=short,
        )
        note = work_drafts.create(db, case["workspace"], case["actor"], case["policy"], payload)
        party = work_parties.create(
            db, case["workspace"], case["policy"], "synthetic:expiry-person", short
        )
        content = work_capture.Payload(
            policy_id=case["policy"],
            draft=work_capture.Draft(
                kind="action",
                marker="synthetic:pending-secret",
                source_ids=(case["source"],),
                retain_until=live,
            ),
        ).model_dump(mode="json")
        for intent in ("capture_draft", "correct_note", "forget_note"):
            db.execute(
                "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,intent,target_record_id,expected_revision,payload,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    case["workspace"],
                    case["actor"],
                    uuid4(),
                    uuid4(),
                    intent,
                    note.id if intent != "capture_draft" else None,
                    1 if intent != "capture_draft" else None,
                    Jsonb({"forget": True} if intent == "forget_note" else content),
                    short,
                ),
            )
        for _ in range(linked):
            db.execute(
                "INSERT INTO work.capture_intents(workspace_id,actor_id,session_id,request_id,intent,target_record_id,expected_revision,payload,expires_at) VALUES(%s,%s,%s,%s,'correct_note',%s,1,%s,%s)",
                (
                    case["workspace"],
                    case["actor"],
                    uuid4(),
                    uuid4(),
                    note.id,
                    Jsonb(content),
                    datetime.now(UTC) + timedelta(minutes=4),
                ),
            )
        for record in (note, case["item"]):
            digest = db.execute(
                "SELECT encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') FROM work.drafts WHERE workspace_id=%s AND id=%s",
                (case["workspace"], record.id),
            ).fetchone()[0]
            review = db.execute(
                "INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash,expires_at) VALUES(%s,%s,1,%s,%s,%s,'confirm_note',%s,%s) RETURNING id,session_id",
                (case["workspace"], record.id, case["actor"], uuid4(), uuid4(), digest, short),
            ).fetchone()
            db.execute(
                "INSERT INTO public.work_confirmation_requests(workspace_id,record_id,review_preparation_id,reviewed_revision,actor_id,session_id,request_id,expires_at) VALUES(%s,%s,%s,1,%s,%s,%s,%s)",
                (case["workspace"], record.id, review[0], case["actor"], review[1], uuid4(), short),
            )
        # One unrelated unexpired preparation must survive.
        db.execute(
            "INSERT INTO work.draft_reviews(workspace_id,record_id,revision,actor_id,session_id,request_id,intent,payload_hash) SELECT workspace_id,id,revision,%s,%s,%s,'confirm_note',encode(sha256(convert_to(snapshot::text,'UTF8')),'hex') FROM work.drafts WHERE workspace_id=%s AND id=%s",
            (case["actor"], uuid4(), uuid4(), case["workspace"], case["item"].id),
        )
    disable(case)
    with connect() as db:
        db.execute(
            "SELECT pg_sleep(GREATEST(0,extract(epoch FROM (%s-clock_timestamp()))))",
            (short + timedelta(milliseconds=30),),
        )
    return note, party


def counts(case):
    with connect() as db:
        return tuple(
            db.execute(query, (case["workspace"],)).fetchone()[0]
            for query in (
                "SELECT count(*) FROM work.drafts WHERE workspace_id=%s AND state='forgotten'",
                "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND state='pending'",
                "SELECT count(*) FROM work.draft_reviews WHERE workspace_id=%s AND payload_hash IS NOT NULL",
                "SELECT count(*) FROM public.audit_events WHERE entity_id=%s::text AND event_type='admin.work_retention_applied'",
            )
        )


def test_mixed_expiry_scrubs_histories_orphan_requests_and_preserves_live(review_case):
    case = review_case
    note, party = seed(case)
    plan = run(case)
    assert len(plan["items"]) == 9 and plan["linked_count"] == 4
    encoded = json.dumps(plan)
    for hidden in (
        "expiry-secret",
        "expiry-person",
        "pending-secret",
        "payload_hash",
        str(case["source"]),
        str(case["policy"]),
    ):
        assert hidden not in encoded
    assert run(case, cutoff=datetime.fromisoformat(plan["cutoff"])) == plan
    result = apply(case, plan)
    assert len(result["outcomes"]) == 9 and result["workspace_enabled"] is False
    assert counts(case) == (1, 0, 1, 1)
    with connect() as db:
        assert (
            db.execute(
                "SELECT snapshot->>'marker' FROM work.drafts WHERE id=%s", (case["item"].id,)
            ).fetchone()[0]
            == "synthetic:review-note"
        )
        assert db.execute(
            "SELECT marker,state FROM work.parties WHERE id=%s", (party.id,)
        ).fetchone() == (None, "forgotten")
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_revisions WHERE record_id=%s AND snapshot IS NOT NULL",
                (note.id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM work.capture_intents WHERE workspace_id=%s AND (payload IS NOT NULL OR payload_hash IS NOT NULL)",
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
                "SELECT count(*) FROM work.draft_audit WHERE workspace_id=%s AND event_type='draft.review_expired'",
                (case["workspace"],),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT metadata_json FROM public.audit_events WHERE id=%s",
                (UUID(result["receipt_id"]),),
            ).fetchone()[0]
            == result
        )
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    assert_downgrade_refused(
        "0015_work_note_changes", "0016_work_retention", "Retention evidence exists"
    )


def test_bounded_batch_replay_never_advances_to_another_batch(review_case):
    case = review_case
    seed(case)
    plan = run(case, limit=1)
    assert plan["has_more"] and len(plan["items"]) == 1
    apply(case, plan)
    before = counts(case)
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    assert counts(case) == before
    assert run(case, limit=1)["reviewed_hash"] != plan["reviewed_hash"]


@pytest.mark.parametrize(
    "fault",
    [
        "active",
        "operator",
        "missing_workspace",
        "non_synthetic",
        "isolation",
        "role",
        "login",
        "cutoff_future",
        "cutoff_old",
    ],
)
def test_closed_target_and_clean_owner_checks(review_case, fault):
    case = review_case
    grant(case)
    if fault != "active":
        disable(case)
    if fault == "operator":
        with case["maker"].begin() as db:
            set_scope(db, db.get(User, case["actor"]), "technical_admin", False)
    if fault == "non_synthetic":
        with connect() as db:
            db.execute(
                "UPDATE public.work_workspaces SET slug='ordinary-workspace-'||id::text WHERE id=%s",
                (case["workspace"],),
            )
    changes = {}
    if fault == "missing_workspace":
        case = dict(case, workspace=uuid4())
    if fault.startswith("cutoff_"):
        changes["cutoff"] = datetime.now(UTC) + timedelta(
            minutes=1 if fault == "cutoff_future" else -6
        )
    with (
        pytest.raises((ValueError, psycopg.Error)),
        connect(
            case["login"] if fault == "login" else None, PASSWORD if fault == "login" else None
        ) as db,
        db.transaction(),
    ):
        if fault == "isolation":
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        if fault == "role":
            db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(case["role"])))
        work_retention.reconcile(
            db,
            work_retention.Request(
                workspace_id=case["workspace"], operator_id=case["actor"], **changes
            ),
        )


def test_empty_apply_cannot_create_success_receipt(review_case):
    case = review_case
    grant(case)
    disable(case)
    plan = run(case)
    assert not plan["items"]
    with pytest.raises(ValueError, match="No expired"):
        apply(case, plan)
    assert counts(case) == (0, 0, 0, 0)


def test_changed_linked_set_and_lost_operator_reject_without_changes(review_case):
    case = review_case
    seed(case)
    plan = run(case)
    with connect() as db:
        db.execute(
            "UPDATE work.capture_intents SET state='denied',reason_code='expired',payload=NULL,finished_at=clock_timestamp() WHERE workspace_id=%s AND intent='correct_note' AND expires_at>clock_timestamp()",
            (case["workspace"],),
        )
    before = counts(case)
    with pytest.raises(ValueError, match="Plan changed"):
        apply(case, plan)
    assert counts(case) == before
    plan = run(case)
    with case["maker"].begin() as db:
        set_scope(db, db.get(User, case["actor"]), "technical_admin", False)
    with pytest.raises(ValueError, match="technical-admin"):
        apply(case, plan)
    assert counts(case) == before


def test_dependency_cap_rejects_before_writing(review_case):
    seed(review_case, linked=101)
    before = counts(review_case)
    with pytest.raises(ValueError, match="Too many linked"):
        run(review_case)
    assert counts(review_case) == before


@pytest.mark.parametrize("target", ["public", "private"])
def test_audit_failure_rolls_back_entire_cleanup(review_case, target):
    case = review_case
    seed(case)
    plan = run(case)
    before = counts(case)
    table = "public.audit_events" if target == "public" else "work.draft_audit"
    event = "admin.work_retention_applied" if target == "public" else "draft.review_expired"
    name = "synthetic_retention_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} CHECK(event_type<>{}) NOT VALID").format(
                sql.SQL(table), sql.Identifier(name), sql.Literal(event)
            )
        )
    try:
        with pytest.raises(psycopg.Error):
            apply(case, plan)
        assert counts(case) == before
        assert run(case, cutoff=datetime.fromisoformat(plan["cutoff"])) == plan
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                    sql.SQL(table), sql.Identifier(name)
                )
            )


def test_unexpired_forgetting_and_review_hash_changes_rejected_in_maintenance(review_case):
    case = review_case
    grant(case)
    disable(case)
    with pytest.raises(ValueError, match="expired"), connect() as db, db.transaction():
        work_drafts.transition(
            db, case["workspace"], case["actor"], case["item"].id, 1, "forget", maintenance=True
        )
    with pytest.raises(ValueError), connect() as db, db.transaction():
        work_drafts.transition(
            db, case["workspace"], case["actor"], case["item"].id, 1, "confirm", maintenance=True
        )


def test_global_barrier_times_out_without_partial_cleanup(review_case):
    case = review_case
    seed(case)
    plan = run(case)
    before = counts(case)
    held, release = Event(), Event()

    def reader():
        with connect() as db:
            db.execute("SELECT pg_advisory_xact_lock_shared(1508310,1)")
            held.set()
            assert release.wait(8)

    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(reader)
        assert held.wait(4)
        try:
            with pytest.raises(psycopg.errors.LockNotAvailable):
                apply(case, plan)
        finally:
            release.set()
        pending.result(timeout=5)
    assert counts(case) == before
    apply(case, plan)


def test_forged_setting_and_accidental_write_grant_do_not_enable_scoped_cleanup(review_case):
    case = review_case
    seed(case)
    with connect() as db:
        db.execute(
            sql.SQL("GRANT UPDATE ON work.draft_reviews TO {}").format(sql.Identifier(case["role"]))
        )
    try:
        with case["storage"]["session"]() as db:
            db.execute("SET LOCAL butler.retention_cleanup='expired'")
            assert (
                db.execute(
                    "UPDATE work.draft_reviews SET payload_hash=NULL WHERE workspace_id=%s",
                    (case["workspace"],),
                ).rowcount
                == 0
            )
    except psycopg.Error:
        pass  # Guard denial or RLS-invisible rows are both fail-closed.
    assert counts(case) == (0, 4, 3, 0)


def test_direct_owner_sql_rejects_early_review_erasure_and_party_forget(review_case):
    case = review_case
    with connect() as db, db.transaction():
        live_party = work_parties.create(
            db,
            case["workspace"],
            case["policy"],
            "synthetic:retained-person",
            datetime.now(UTC) + timedelta(hours=1),
        )
    seed(case)
    # Only the unexpired review remains after legitimate cleanup.
    apply(case, run(case))
    with pytest.raises(psycopg.Error), connect() as db:
        db.execute("SET LOCAL butler.retention_cleanup='expired'")
        db.execute(
            "UPDATE work.draft_reviews SET payload_hash=NULL WHERE workspace_id=%s AND payload_hash IS NOT NULL",
            (case["workspace"],),
        )
    with pytest.raises(ValueError, match="expired party"), connect() as db, db.transaction():
        work_parties.transition(db, case["workspace"], live_party.id, 1, "forget", maintenance=True)
    with pytest.raises(psycopg.Error), connect() as db:
        db.execute("SET LOCAL butler.retention_cleanup='expired'")
        db.execute(
            "UPDATE work.parties SET state='forgotten',marker=NULL,revision=revision+1 WHERE workspace_id=%s AND id=%s",
            (case["workspace"], live_party.id),
        )
    assert counts(case) == (1, 0, 1, 1)


def test_reenabled_workspace_and_unknown_operator_invalidate_review(review_case):
    case = review_case
    seed(case)
    plan = run(case)
    with connect() as db:
        db.execute(
            "UPDATE public.work_workspaces SET is_active=true WHERE id=%s", (case["workspace"],)
        )
    with pytest.raises(ValueError, match="Disabled synthetic"):
        apply(case, plan)
    disable(case)
    with pytest.raises(ValueError, match="technical-admin"):
        run(dict(case, actor=uuid4()))
    assert counts(case) == (0, 4, 3, 0)


def test_two_cleaners_cannot_consume_one_plan_twice(review_case):
    case = review_case
    seed(case)
    plan = run(case, limit=1)
    start = Event()

    def cleaner():
        assert start.wait(4)
        try:
            apply(case, plan)
            return "applied"
        except ValueError:
            return "stale"

    with ThreadPoolExecutor(2) as pool:
        first, second = pool.submit(cleaner), pool.submit(cleaner)
        start.set()
        assert sorted([first.result(timeout=8), second.result(timeout=8)]) == ["applied", "stale"]
    assert counts(case)[-1] == 1


def test_expiry_during_apply_rolls_back_every_change(review_case, monkeypatch):
    case = review_case
    seed(case)
    plan = run(case)
    before = counts(case)
    original = work_drafts._now
    calls = 0

    def late(db):
        nonlocal calls
        calls += 1
        value = original(db)
        # begin, note-forget clock, end-of-apply clock
        return value + timedelta(minutes=6) if calls >= 3 else value

    monkeypatch.setattr(work_drafts, "_now", late)
    with pytest.raises(ValueError, match="expired during cleanup"):
        apply(case, plan)
    assert counts(case) == before
