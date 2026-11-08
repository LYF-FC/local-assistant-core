"""Actual owner-only party lifecycle, scoped read denial and explicit note ownership."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from test_work_authority_postgres import wait_for_advisory
from work_storage_helpers import connect

from app import work_drafts, work_lifecycle, work_parties

pytestmark = pytest.mark.integration


def party(case, **changes):
    values = {
        "workspace_id": case["workspace"],
        "policy_id": case["policy"],
        "marker": "synthetic:explicit-owner",
        "retain_until": datetime.now(UTC) + timedelta(hours=1),
    }
    values.update(changes)
    with connect() as db, db.transaction():
        return work_parties.create(db, **values)


def change(case, item, action, expected=None):
    with connect() as db, db.transaction():
        return work_parties.transition(
            db,
            case["workspace"],
            item.id,
            expected if expected is not None else item.revision,
            action,
        )


def note(case, owner=None):
    with connect() as db, db.transaction():
        return work_drafts.create(
            db,
            case["workspace"],
            case["actor"],
            case["policy"],
            work_lifecycle.Draft(
                kind="action",
                marker="synthetic:owned-note",
                owner_id=owner,
                source_ids=(case["source"],),
                retain_until=datetime.now(UTC) + timedelta(hours=1),
            ),
        )


def test_explicit_owner_unknown_state_retire_forget_history_and_audit(review_case):
    case = review_case
    owner = party(case)
    assert note(case).owner_id is None
    item = note(case, owner.id)
    assert item.owner_id == owner.id and item.actor_id == case["actor"]
    retired = change(case, owner, "retire")
    assert retired.state == "retired" and retired.revision == 2
    with pytest.raises((ValueError, psycopg.Error)):
        note(case, owner.id)
    with connect() as db, db.transaction():
        # Historical UUID remains meaningful without claiming new assignment authority.
        assert (
            work_drafts.read(db, case["workspace"], case["actor"], item.id).items[0].owner_id
            == owner.id
        )
        with pytest.raises(ValueError), db.transaction():
            work_drafts.transition(db, case["workspace"], case["actor"], item.id, 1, "confirm")
        forgotten = work_drafts.transition(
            db, case["workspace"], case["actor"], item.id, 1, "forget"
        )
        assert forgotten.owner_id is None
    erased = change(case, retired, "forget")
    assert erased.state == "forgotten" and erased.marker is None and erased.revision == 3
    with connect() as db:
        assert db.execute(
            "SELECT array_agg(event_type ORDER BY revision) FROM work.party_audit WHERE party_id=%s",
            (owner.id,),
        ).fetchone()[0] == ["party.created", "party.retired", "party.forgotten"]
        assert (
            db.execute(
                "SELECT count(*) FROM public.audit_events WHERE event_type='admin.work_party_changed' AND entity_id=%s",
                (str(case["workspace"]),),
            ).fetchone()[0]
            == 3
        )
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_revisions WHERE record_id=%s AND snapshot IS NOT NULL",
                (item.id,),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("fault", ["missing", "other_workspace", "retired", "forgotten", "expired"])
def test_owner_eligibility_cannot_be_forged(review_case, fault):
    case = review_case
    until = (
        datetime.now(UTC) + timedelta(seconds=2)
        if fault == "expired"
        else datetime.now(UTC) + timedelta(hours=1)
    )
    item = party(case, retain_until=until)
    if fault == "retired":
        change(case, item, "retire")
    elif fault == "forgotten":
        change(case, item, "forget")
    elif fault == "expired":
        with connect() as db:
            db.execute(
                "SELECT pg_sleep(GREATEST(0,extract(epoch FROM (%s-clock_timestamp()))))",
                (until + timedelta(milliseconds=30),),
            )
    elif fault == "other_workspace":
        foreign_workspace = case["storage"]["b"]["workspace"]
        foreign_policy = uuid4()
        with connect() as db:
            db.execute(
                "INSERT INTO work.retention_policies VALUES(%s,%s,86400)",
                (foreign_workspace, foreign_policy),
            )
        item = party(dict(case, workspace=foreign_workspace, policy=foreign_policy))
    with pytest.raises((ValueError, psycopg.Error)):
        note(case, uuid4() if fault == "missing" else item.id)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE work.parties SET marker='synthetic:replacement',revision=revision+1",
        "UPDATE work.parties SET state='active',revision=revision+1",
        "UPDATE work.parties SET retain_until=retain_until+interval '1 day',state='retired',revision=revision+1",
        "UPDATE work.parties SET id=gen_random_uuid(),state='retired',revision=revision+1",
        "DELETE FROM work.parties",
        "TRUNCATE work.parties CASCADE",
        "UPDATE work.party_audit SET revision=revision",
        "DELETE FROM work.party_audit",
    ],
)
def test_direct_owner_sql_cannot_bypass_lifecycle_or_audit(review_case, statement):
    party(review_case)
    with pytest.raises(psycopg.Error), connect() as db:
        db.execute(statement)


def test_stale_revision_and_reactivation_rejected(review_case):
    owner = party(review_case)
    retired = change(review_case, owner, "retire")
    with pytest.raises(ValueError):
        change(review_case, owner, "forget")
    forgotten = change(review_case, retired, "forget")
    with pytest.raises((ValueError, psycopg.Error)):
        change(review_case, forgotten, "forget", expected=2)


@pytest.mark.parametrize("target", ["private", "public"])
def test_party_and_both_audits_roll_back_together(review_case, target):
    case = review_case
    name = "synthetic_party_fail_" + uuid4().hex
    table = "work.party_audit" if target == "private" else "public.audit_events"
    check = (
        "event_type<>'party.created'"
        if target == "private"
        else "event_type<>'admin.work_party_changed'"
    )
    with connect() as db:
        db.execute(
            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} CHECK({}) NOT VALID").format(
                sql.SQL(table), sql.Identifier(name), sql.SQL(check)
            )
        )
    try:
        with pytest.raises(psycopg.Error):
            party(case)
        with connect() as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM work.parties WHERE workspace_id=%s", (case["workspace"],)
                ).fetchone()[0]
                == 0
            )
            assert (
                db.execute(
                    "SELECT count(*) FROM work.party_audit WHERE workspace_id=%s",
                    (case["workspace"],),
                ).fetchone()[0]
                == 0
            )
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                    sql.SQL(table), sql.Identifier(name)
                )
            )


def test_normal_roles_have_no_party_grants_and_explicit_inspector_is_workspace_scoped(review_case):
    case = review_case
    owner = party(case)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), case["storage"]["session"]() as db:
        db.execute("SELECT * FROM work.parties")
    with connect() as db:
        for letter in ("a", "b"):
            db.execute(
                sql.SQL("GRANT SELECT ON work.parties,work.party_audit TO {}").format(
                    sql.Identifier(case["storage"][letter]["role"])
                )
            )
    with case["storage"]["session"]() as db:
        assert db.execute("SELECT id FROM work.parties").fetchall() == [(owner.id,)]
    with case["storage"]["session"]("b") as db:
        assert db.execute("SELECT id FROM work.parties").fetchall() == []
    # Even an accidental write grant cannot turn an assumed workspace role into an owner.
    with connect() as db:
        db.execute(
            sql.SQL("GRANT UPDATE ON work.parties TO {}").format(sql.Identifier(case["role"]))
        )
    with pytest.raises(psycopg.Error), case["storage"]["session"]() as db:
        db.execute("UPDATE work.parties SET state='retired',revision=revision+1")


def test_direct_sql_rejects_unknown_party_owner(review_case):
    case = review_case
    with pytest.raises(psycopg.Error), connect() as db:
        db.execute(
            "UPDATE work.drafts SET revision=revision+1,snapshot=snapshot||jsonb_build_object('revision',revision+1,'owner_id',%s::text) WHERE workspace_id=%s AND id=%s",
            (str(uuid4()), case["workspace"], case["item"].id),
        )


def test_retirement_waits_for_note_transaction_then_prevents_new_owner(
    review_case, postgres_engine
):
    case = review_case
    owner = party(case)
    ready, release, writer_ready = Event(), Event(), Event()
    pid = []

    def hold_note():
        with connect() as db, db.transaction():
            work_drafts.create(
                db,
                case["workspace"],
                case["actor"],
                case["policy"],
                work_lifecycle.Draft(
                    kind="action",
                    marker="synthetic:held-note",
                    owner_id=owner.id,
                    source_ids=(case["source"],),
                    retain_until=datetime.now(UTC) + timedelta(hours=1),
                ),
            )
            ready.set()
            assert release.wait(8)

    def retire():
        with connect() as db, db.transaction():
            pid.append(db.execute("SELECT pg_backend_pid()").fetchone()[0])
            writer_ready.set()
            return work_parties.transition(db, case["workspace"], owner.id, 1, "retire")

    with ThreadPoolExecutor(2) as pool:
        note_future = pool.submit(hold_note)
        assert ready.wait(5)
        retirement = pool.submit(retire)
        try:
            assert writer_ready.wait(5)
            wait_for_advisory(postgres_engine, pid[0])
        finally:
            release.set()
        note_future.result(timeout=10)
        assert retirement.result(timeout=10).state == "retired"
    with pytest.raises(ValueError):
        note(case, owner.id)


@pytest.mark.parametrize("fault", ["policy", "retention", "expired"])
def test_party_requires_explicit_current_retention_policy(review_case, fault):
    changes = (
        {"policy_id": uuid4()}
        if fault == "policy"
        else {
            "retain_until": datetime.now(UTC) + timedelta(days=2)
            if fault == "retention"
            else datetime.now(UTC) - timedelta(seconds=1)
        }
    )
    with pytest.raises((psycopg.Error, ValueError)):
        party(review_case, **changes)


@pytest.mark.parametrize("state", ["retired", "forgotten"])
def test_direct_sql_rejects_ineligible_owner(review_case, state):
    case = review_case
    owner = party(case)
    change(case, owner, "retire" if state == "retired" else "forget")
    with pytest.raises(psycopg.Error), connect() as db:
        db.execute(
            "UPDATE work.drafts SET revision=revision+1,snapshot=snapshot||jsonb_build_object('revision',revision+1,'owner_id',%s::text) WHERE workspace_id=%s AND id=%s",
            (str(owner.id), case["workspace"], case["item"].id),
        )
