"""Actual quarantined storage, scoped SQL and separate-connection transactions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from test_work_authority_postgres import wait_for_advisory
from work_storage_helpers import connect, insert

from app import work_drafts as store
from app import work_lifecycle as lifecycle

pytestmark = pytest.mark.integration
TABLES = (
    "retention_policies",
    "source_registry",
    "drafts",
    "draft_revisions",
    "draft_audit",
    "draft_tombstones",
)
ACTOR = uuid4()


@pytest.fixture
def draft_case(storage_case):
    case = dict(storage_case["a"], storage=storage_case, actor=ACTOR, policy=uuid4())
    case["source"] = insert(storage_case)
    with connect() as db:
        db.execute(
            "INSERT INTO work.retention_policies VALUES(%s,%s,86400)",
            (case["workspace"], case["policy"]),
        )
        db.execute(
            "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
            (case["workspace"], case["source"]),
        )
        # Explicit read-only test inspection; ordinary provision grants no new domain access.
        for letter in ("a", "b"):
            for table in TABLES:
                db.execute(
                    sql.SQL("GRANT SELECT ON work.{} TO {}").format(
                        sql.Identifier(table), sql.Identifier(storage_case[letter]["role"])
                    )
                )
    return case


def payload(case, **changes):
    values = {
        "kind": "action",
        "marker": "synthetic:persisted-note",
        "source_ids": (case["source"],),
        "retain_until": datetime.now(UTC) + timedelta(hours=1),
    }
    values.update(changes)
    return lifecycle.Draft(**values)


def create(case, draft=None):
    with connect() as db, db.transaction():
        return store.create(
            db, case["workspace"], case["actor"], case["policy"], draft or payload(case)
        )


def change(case, item, action, draft=None, expected=None):
    with connect() as db, db.transaction():
        return store.transition(
            db,
            case["workspace"],
            case["actor"],
            item.id,
            expected if expected is not None else item.revision,
            action,
            draft,
        )


def counts(case, identifier):
    with connect() as db:
        return tuple(
            db.execute(
                sql.SQL("SELECT count(*) FROM work.{} WHERE workspace_id=%s AND {}=%s").format(
                    sql.Identifier(table), sql.Identifier(column)
                ),
                (case["workspace"], identifier),
            ).fetchone()[0]
            for table, column in (
                ("drafts", "id"),
                ("draft_revisions", "record_id"),
                ("draft_audit", "record_id"),
                ("draft_tombstones", "record_id"),
            )
        )


def test_persist_create_confirm_correct_read_preserves_history_unknowns_and_audit(draft_case):
    case = draft_case
    first = create(case)
    confirmed = change(case, first, "confirm")
    corrected = change(
        case,
        confirmed,
        "correct",
        payload(case, marker="synthetic:corrected-note", retain_until=first.retain_until),
    )
    assert corrected.state == "draft" and corrected.revision == 3
    assert corrected.owner_id is None and corrected.due_at is None
    with connect() as db, db.transaction():
        preview = store.read(db, case["workspace"], case["actor"], first.id)
        assert preview.items == (corrected,)
    assert counts(case, first.id) == (1, 3, 4, 0)
    with case["storage"]["session"]() as db:
        rows = db.execute(
            "SELECT snapshot->>'marker' FROM work.draft_revisions ORDER BY revision"
        ).fetchall()
        assert rows == [
            ("synthetic:persisted-note",),
            ("synthetic:persisted-note",),
            ("synthetic:corrected-note",),
        ]
        assert db.execute("SELECT * FROM work.draft_audit").description is not None


def test_forget_redacts_every_persisted_revision_and_prevents_resurrection(draft_case):
    case = draft_case
    first = create(case)
    second = change(case, first, "confirm")
    forgotten = change(case, second, "forget")
    assert forgotten.state == "forgotten" and forgotten.marker is None
    assert counts(case, first.id) == (1, 3, 3, 1)
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_revisions WHERE record_id=%s AND snapshot IS NOT NULL",
                (first.id,),
            ).fetchone()[0]
            == 0
        )
        assert db.execute(
            "SELECT snapshot->'source_ids',snapshot->>'owner_id',snapshot->>'due_at' FROM work.drafts WHERE id=%s",
            (first.id,),
        ).fetchone() == ([], None, None)
    assert change(case, forgotten, "forget") == forgotten
    assert counts(case, first.id) == (1, 3, 3, 1)
    for action in ("confirm", "correct"):
        with pytest.raises(lifecycle.LifecycleError):
            change(case, forgotten, action, payload(case) if action == "correct" else None)


@pytest.mark.parametrize(
    "fault",
    ["foreign_policy", "unknown_source", "peer_source", "revoked_source", "owner", "disabled"],
)
def test_source_policy_owner_workspace_refusal_leaves_no_draft(draft_case, fault):
    case = draft_case
    draft = payload(case)
    if fault == "foreign_policy":
        case = dict(case, policy=uuid4())
    elif fault == "unknown_source":
        draft = payload(case, source_ids=(uuid4(),))
    elif fault == "peer_source":
        draft = payload(case, source_ids=(insert(case["storage"], "b"),))
    elif fault == "revoked_source":
        with connect() as db:
            db.execute(
                "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
                (case["workspace"],),
            )
    elif fault == "owner":
        draft = payload(case, owner_id=uuid4())
    else:
        with connect() as db:
            db.execute(
                "UPDATE work_workspaces SET is_active=false WHERE id=%s", (case["workspace"],)
            )
    with pytest.raises(store.StoreError):
        create(case, draft)
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM work.drafts WHERE workspace_id=%s", (case["workspace"],)
            ).fetchone()[0]
            == 0
        )


def test_source_revocation_hides_current_and_each_historical_payload(draft_case):
    case = draft_case
    first = create(case)
    with connect() as db:
        db.execute(
            "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
            (case["workspace"],),
        )
    with case["storage"]["session"]() as db:
        assert db.execute("SELECT snapshot FROM work.drafts").fetchall() == []
        assert db.execute("SELECT snapshot FROM work.draft_revisions").fetchall() == []
    with pytest.raises(store.StoreError), connect() as db, db.transaction():
        store.read(db, case["workspace"], case["actor"], first.id)
    new_source = insert(case["storage"])
    with connect() as db:
        db.execute(
            "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
            (case["workspace"], new_source),
        )
    change(
        case,
        first,
        "correct",
        payload(case, source_ids=(new_source,), retain_until=first.retain_until),
    )
    with case["storage"]["session"]() as db:
        assert db.execute("SELECT revision FROM work.draft_revisions").fetchall() == [(2,)]


def test_expired_payloads_hidden_but_terminal_forget_allowed(draft_case):
    case = draft_case
    first = create(case, payload(case, retain_until=datetime.now(UTC) + timedelta(seconds=2)))
    with connect() as db:
        db.execute("SELECT pg_sleep(2.1)")  # expiry condition, not race scheduling evidence
    with case["storage"]["session"]() as db:
        assert db.execute("SELECT * FROM work.drafts").fetchall() == []
        assert db.execute("SELECT * FROM work.draft_revisions").fetchall() == []
    with pytest.raises(lifecycle.LifecycleError):
        change(case, first, "confirm")
    forgotten = change(case, first, "forget")
    assert forgotten.state == "forgotten"


@pytest.mark.parametrize("table", TABLES)
def test_peer_family_and_scoped_mutation_denied(draft_case, runtime_engine, table):
    case = draft_case
    create(case)
    with case["storage"]["session"]("b") as db:
        assert (
            db.execute(sql.SQL("SELECT * FROM work.{}").format(sql.Identifier(table))).fetchall()
            == []
        )
    with pytest.raises(psycopg.Error), case["storage"]["session"]() as db:
        db.execute(sql.SQL("DELETE FROM work.{}").format(sql.Identifier(table)))
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError), runtime_engine.begin() as db:
        db.execute(text(f"SELECT * FROM work.{table}"))


@pytest.mark.parametrize("table", ["draft_revisions", "draft_audit", "draft_tombstones"])
def test_trigger_failure_rolls_back_whole_forget(draft_case, table):
    case = draft_case
    item = create(case)
    constraint = "synthetic_fail_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL("ALTER TABLE work.{} ADD CONSTRAINT {} CHECK(false) NOT VALID").format(
                sql.Identifier(table), sql.Identifier(constraint)
            )
        )
    try:
        with pytest.raises(psycopg.Error):
            change(case, item, "forget")
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE work.{} DROP CONSTRAINT {}").format(
                    sql.Identifier(table), sql.Identifier(constraint)
                )
            )
    assert counts(case, item.id) == (1, 1, 1, 0)
    with connect() as db:
        assert db.execute(
            "SELECT state,snapshot->>'marker' FROM work.drafts WHERE id=%s", (item.id,)
        ).fetchone() == ("draft", "synthetic:persisted-note")


def test_caller_rollback_never_persists_prepared_return_value(draft_case):
    case = draft_case
    with pytest.raises(RuntimeError), connect() as db, db.transaction():
        item = store.create(db, case["workspace"], case["actor"], case["policy"], payload(case))
        raise RuntimeError("synthetic rollback")
    assert counts(case, item.id) == (0, 0, 0, 0)


def test_concurrent_same_revision_has_one_winner(draft_case):
    case = draft_case
    item = create(case)
    start = Barrier(2)

    def writer():
        start.wait(timeout=5)
        try:
            return change(
                case, item, "correct", payload(case, retain_until=item.retain_until)
            ).revision
        except lifecycle.LifecycleError:
            return "stale"

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(writer), pool.submit(writer)
        assert sorted([a.result(timeout=10), b.result(timeout=10)], key=str) == [2, "stale"]
    assert counts(case, item.id) == (1, 2, 2, 0)


def test_source_revocation_waits_for_reader_transaction_commit(draft_case, postgres_engine):
    case = draft_case
    item = create(case)
    started, release, revoking = Event(), Event(), Event()
    pid = []

    def reader():
        with connect() as db, db.transaction():
            store.read(db, case["workspace"], case["actor"], item.id)
            started.set()
            assert release.wait(8)

    def revoke():
        with connect() as db:
            pid.append(db.execute("SELECT pg_backend_pid()").fetchone()[0])
            revoking.set()
            db.execute(
                "UPDATE work.source_registry SET is_active=false WHERE workspace_id=%s",
                (case["workspace"],),
            )

    with ThreadPoolExecutor(2) as pool:
        held = pool.submit(reader)
        assert started.wait(5)
        writer = pool.submit(revoke)
        try:
            assert revoking.wait(5)
            wait_for_advisory(postgres_engine, pid[0])
        finally:
            release.set()
        held.result(timeout=10)
        writer.result(timeout=10)
    with pytest.raises(store.StoreError), connect() as db, db.transaction():
        store.read(db, case["workspace"], case["actor"], item.id)


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM work.drafts WHERE id=%s",
        "TRUNCATE work.drafts",
        "TRUNCATE work.draft_revisions",
        "TRUNCATE work.draft_audit",
        "TRUNCATE work.draft_tombstones",
        "UPDATE work.draft_audit SET event_type=event_type",
        "UPDATE work.draft_tombstones SET revision=revision",
        "UPDATE work.draft_revisions SET snapshot=NULL WHERE record_id=%s",
        "UPDATE work.draft_revisions SET snapshot=jsonb_set(snapshot,'{marker}','\"synthetic:forged\"') WHERE record_id=%s",
        "UPDATE work.drafts SET revision=revision WHERE id=%s",
        'UPDATE work.drafts SET revision=2,state=\'confirmed\',snapshot=snapshot || \'{"state":"confirmed","revision":2,"marker":"synthetic:forged"}\' WHERE id=%s',
        "UPDATE work.drafts SET revision=2,retain_until=retain_until+interval '1 hour',snapshot=snapshot || jsonb_build_object('revision',2,'retain_until',retain_until+interval '1 hour') WHERE id=%s",
    ],
)
def test_raw_owner_sql_cannot_bypass_core_history_and_lifecycle_guards(draft_case, statement):
    case = draft_case
    item = create(case)
    with pytest.raises(psycopg.Error), connect() as db:
        db.execute(statement, (item.id,) if "%s" in statement else None)
    assert counts(case, item.id) == (1, 1, 1, 0)


@pytest.mark.parametrize("table", ["draft_revisions", "draft_audit"])
def test_create_event_failure_rolls_back_current_and_history(draft_case, table):
    case = draft_case
    constraint = "synthetic_create_fail_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL("ALTER TABLE work.{} ADD CONSTRAINT {} CHECK(false) NOT VALID").format(
                sql.Identifier(table), sql.Identifier(constraint)
            )
        )
    try:
        with pytest.raises(psycopg.Error):
            create(case)
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("ALTER TABLE work.{} DROP CONSTRAINT {}").format(
                    sql.Identifier(table), sql.Identifier(constraint)
                )
            )
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM work.drafts WHERE workspace_id=%s", (case["workspace"],)
            ).fetchone()[0]
            == 0
        )


def test_normal_provision_does_not_grant_domain_reads_or_writes(storage_case):
    with storage_case["session"]() as db:
        for table in TABLES:
            assert db.execute(
                "SELECT has_table_privilege(current_user,%s,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')",
                ("work." + table,),
            ).fetchone() == (False,)


def test_expiry_during_read_audit_prevents_prepared_payload_release(draft_case):
    case = draft_case
    item = create(case, payload(case, retain_until=datetime.now(UTC) + timedelta(seconds=2)))
    name = "synthetic_expiry_" + uuid4().hex
    with connect() as db:
        db.execute(
            sql.SQL(
                "CREATE FUNCTION work.{}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(2.1); RETURN NEW; END; $$"
            ).format(sql.Identifier(name))
        )
        db.execute(
            sql.SQL(
                "CREATE TRIGGER {} BEFORE INSERT ON work.draft_audit FOR EACH ROW WHEN (NEW.event_type='draft.read_prepared') EXECUTE FUNCTION work.{}()"
            ).format(sql.Identifier(name), sql.Identifier(name))
        )
    try:
        with pytest.raises(store.StoreError), connect() as db, db.transaction():
            store.read(db, case["workspace"], case["actor"], item.id)
    finally:
        with connect() as db:
            db.execute(sql.SQL("DROP TRIGGER {} ON work.draft_audit").format(sql.Identifier(name)))
            db.execute(sql.SQL("DROP FUNCTION work.{}()").format(sql.Identifier(name)))
    assert counts(case, item.id) == (1, 1, 1, 0)


def test_persisted_history_limit_still_allows_complete_forgetting(draft_case):
    case = draft_case
    item = create(case)
    original = item
    with connect() as db, db.transaction():
        for _ in range(99):
            item = store.transition(
                db,
                case["workspace"],
                case["actor"],
                item.id,
                item.revision,
                "correct",
                payload(case, retain_until=original.retain_until),
            )
    with pytest.raises(lifecycle.LifecycleError):
        change(case, item, "correct", payload(case, retain_until=original.retain_until))
    forgotten = change(case, item, "forget")
    assert forgotten.revision == 101
    assert counts(case, item.id) == (1, 101, 101, 1)
    with connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM work.draft_revisions WHERE record_id=%s AND snapshot IS NOT NULL",
                (item.id,),
            ).fetchone()[0]
            == 0
        )


def test_connection_loss_before_commit_does_not_persist_prepared_draft(draft_case):
    case = draft_case
    with pytest.raises(psycopg.Error), connect() as db, db.transaction():
        item = store.create(db, case["workspace"], case["actor"], case["policy"], payload(case))
        db.close()
        db.commit()  # an attempted commit on the lost connection must fail
    assert counts(case, item.id) == (0, 0, 0, 0)
