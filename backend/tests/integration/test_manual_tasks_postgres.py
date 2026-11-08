"""Actual restricted runtime, SQL invariants, revocation and row-wait evidence."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from conftest import SYNTHETIC_PASSWORD, client_for
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from test_manual_tasks import call, create, query

from app import identity
from app.manage import provision, set_scope
from app.models import AuthSession, ManualTask, ManualTaskRevision, User

pytestmark = pytest.mark.integration


def test_runtime_full_lifecycle_and_scrub(scenario):
    client, h, _, admin, _ = scenario
    row = create(client, h, assignment="me", due_at=identity.now_utc().isoformat()).json()
    assert row["revision"] == 1
    row = call(client, h, row, "correct", title="Synthetic SQL task", assignment="me").json()
    row = call(client, h, row, "transition", status="done").json()
    row = call(client, h, row, "correct", title="Synthetic closed correction").json()
    assert row["status"] == "done" and row["completed_at"]
    row = call(client, h, row, "transition", status="open").json()
    row = call(client, h, row, "transition", status="cancelled").json()
    assert len(call(client, h, row, "history").json()["items"]) == 6
    tomb = call(client, h, row, "forget")
    assert tomb.status_code == 200 and tomb.json()["revision"] == 7
    with admin() as db:
        assert (
            list(
                db.scalars(
                    select(ManualTaskRevision.snapshot).where(
                        ManualTaskRevision.task_id == UUID(row["id"])
                    )
                )
            )
            == [None] * 7
        )
    assert call(client, h, tomb.json(), "correct").status_code == 410


@pytest.mark.parametrize(
    "change",
    [
        "owner_id=:other,revision=revision+1",
        "scope_key='member_a_private',revision=revision+1",
        "id=:other,revision=revision+1",
        "created_at=created_at+interval '1s',revision=revision+1",
        "revision=revision+2",
        "title='Synthetic bypass'",
        "status='done',revision=revision+1",
        "completed_at=now(),revision=revision+1",
        "assignee_id=:other,revision=revision+1",
        "title=NULL,revision=revision+1",
        "title='Synthetic combined',status='cancelled',cancelled_at=updated_at,revision=revision+1",
        "revision=revision+1",
        "updated_at=updated_at-interval '1s',title='Synthetic reversed',revision=revision+1",
    ],
)
def test_raw_task_mutations_fail(scenario, runtime_engine, change):
    client, h, _, _, _ = scenario
    row = create(client, h).json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(f"UPDATE manual_tasks SET {change} WHERE id=:id"),
            {"id": UUID(row["id"]), "other": uuid4()},
        )
    assert call(client, h, row, "read").json()["revision"] == 1


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM manual_tasks WHERE id=:id",
        "TRUNCATE manual_tasks CASCADE",
        "DELETE FROM manual_task_revisions WHERE task_id=:id",
        "TRUNCATE manual_task_revisions",
        "UPDATE manual_task_revisions SET snapshot=NULL WHERE task_id=:id",
        "UPDATE manual_task_revisions SET revision=2 WHERE task_id=:id",
        "UPDATE user_scopes SET created_at=created_at",
        "SELECT metadata_json FROM audit_events",
        "DELETE FROM users WHERE id=:id",
    ],
)
def test_runtime_least_privilege_and_history_seal(scenario, runtime_engine, statement):
    client, h, _, _, _ = scenario
    row = create(client, h).json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(statement), {"id": UUID(row["id"])})


def test_forged_history_and_inserted_closed_task_fail(scenario, runtime_engine):
    client, h, _, _, uid = scenario
    row = create(client, h).json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "INSERT INTO manual_task_revisions(id,task_id,revision,actor_id,operation,snapshot,created_at) VALUES(:new,:id,2,:owner,'corrected','{}',now())"
            ),
            {"new": uuid4(), "id": UUID(row["id"]), "owner": uid},
        )
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "INSERT INTO manual_tasks(id,owner_id,scope_key,state,revision,title,details,source_reference,status,completed_at,created_at,updated_at) VALUES(:id,:owner,'household_shared','active',1,'Synthetic bypass','','Synthetic','done',now(),now(),now())"
            ),
            {"id": uuid4(), "owner": uid},
        )
    tomb = call(client, h, row, "forget").json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "UPDATE manual_tasks SET state='active',title='Synthetic resurrection',details='',source_reference='Synthetic',status='open',revision=revision+1 WHERE id=:id"
            ),
            {"id": UUID(tomb["id"])},
        )


def test_other_reader_and_same_private_scope_do_not_gain_owner_authority(scenario, runtime_engine):
    client, h, _, admin, uid = scenario
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "member_a_private", True)
        other = provision(
            db,
            "synthetic-task-reader-" + uuid4().hex,
            "Synthetic reader",
            SYNTHETIC_PASSWORD,
            {"household_shared", "member_a_private"},
        )
        slug = other.slug
    shared = create(client, h).json()
    private = create(client, h, scope="member_a_private").json()
    with client_for(sessionmaker(bind=runtime_engine, expire_on_commit=False)) as reader:
        response = reader.post(
            "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
        )
        rh = {"X-CSRF-Token": response.json()["csrf_token"]}
        assert call(reader, rh, shared, "read").status_code == 200
        for operation, body in [
            ("correct", {}),
            ("transition", {"status": "done"}),
            ("forget", {}),
            ("history", {}),
        ]:
            assert call(reader, rh, shared, operation, **body).status_code == 403
        assert call(reader, rh, private, "read").status_code == 404
        assert query(reader, rh, scope="member_a_private").json()["items"] == []


def wait_for_record_lock(admin):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with admin() as db:
            count = db.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%manual_tasks%FOR %'"
                )
            )
        if count:
            return
        time.sleep(0.02)
    raise AssertionError("Synthetic task request did not reach a real record lock wait")


@pytest.mark.parametrize("operation", ["read", "transition", "history", "export"])
def test_expiry_rechecked_after_actual_record_wait(scenario, monkeypatch, operation):
    client, h, _, admin, uid = scenario
    row = create(client, h, title="Synthetic expiry " + uuid4().hex).json()
    with admin() as db:
        expiry = db.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == uid))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(select(ManualTask).where(ManualTask.id == UUID(row["id"])).with_for_update())
            if operation == "export":
                pending = pool.submit(
                    client.post,
                    "/api/v1/tasks/export",
                    headers=h,
                    json={
                        "scope": "household_shared",
                        "acknowledge_copy_limits": True,
                        "search": row["title"],
                    },
                )
            else:
                pending = pool.submit(
                    call,
                    client,
                    h,
                    row,
                    operation,
                    **({"status": "done"} if operation == "transition" else {}),
                )
            wait_for_record_lock(admin)
            monkeypatch.setattr(
                identity, "now_utc", lambda: identity.aware(expiry) + timedelta(seconds=1)
            )
        response = pending.result(timeout=5)
    assert response.status_code == 401 and "items" not in response.json()
    with admin() as db:
        assert db.get(ManualTask, UUID(row["id"])).revision == 1


def test_stale_write_after_actual_row_wait_is_rejected(scenario):
    client, h, _, admin, _ = scenario
    row = create(client, h).json()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            record = db.scalar(
                select(ManualTask).where(ManualTask.id == UUID(row["id"])).with_for_update()
            )
            pending = pool.submit(call, client, h, row, "transition", status="done")
            wait_for_record_lock(admin)
            record.title = "Synthetic concurrent edit"
            record.revision += 1
            record.updated_at = identity.now_utc()
        response = pending.result(timeout=5)
    assert response.status_code == 409
    assert call(client, h, row, "read").json()["status"] == "open"


def test_user_and_scope_pinned_until_commit(scenario):
    client, h, _, admin, uid = scenario
    row = create(client, h).json()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(select(ManualTask).where(ManualTask.id == UUID(row["id"])).with_for_update())
            pending = pool.submit(call, client, h, row, "read")
            wait_for_record_lock(admin)
            for statement in [
                "UPDATE users SET is_active=false WHERE id=:id",
                "DELETE FROM user_scopes WHERE user_id=:id",
            ]:
                with admin.begin() as other, pytest.raises(DBAPIError) as error:
                    other.execute(text("SET LOCAL lock_timeout='100ms'"))
                    other.execute(text(statement), {"id": uid})
                assert error.value.orig.sqlstate == "55P03"
        assert pending.result(timeout=5).status_code == 200
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "household_shared", False)
    assert call(client, h, row, "read").status_code == 403


def test_audit_commit_failure_rolls_back_on_runtime(scenario, runtime_engine):
    client, h, _, admin, _ = scenario
    row = create(client, h).json()

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic task audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        assert call(client, h, row, "transition", status="done").status_code == 503
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert db.get(ManualTask, UUID(row["id"])).revision == 1
        assert (
            len(
                list(
                    db.scalars(
                        select(ManualTaskRevision).where(
                            ManualTaskRevision.task_id == UUID(row["id"])
                        )
                    )
                )
            )
            == 1
        )


def test_scope_helper_fixed_path_nonpublic_and_bounded(scenario, runtime_engine):
    _, _, _, admin, uid = scenario
    with admin() as db:
        assert db.scalar(
            text(
                "SELECT prosecdef AND proconfig @> ARRAY['search_path=pg_catalog'] FROM pg_proc WHERE proname='butler_lock_task_scope'"
            )
        )
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM pg_proc p,LATERAL aclexplode(p.proacl) a WHERE p.proname='butler_lock_task_scope' AND a.grantee=0"
                )
            )
            == 0
        )
    with runtime_engine.begin() as db:
        assert db.scalar(
            text("SELECT public.butler_lock_task_scope(:id,'household_shared')"), {"id": uid}
        )
        for scope in ["technical_admin", "finance_private", "work_private", "member_a_private"]:
            assert not db.scalar(
                text("SELECT public.butler_lock_task_scope(:id,:scope)"),
                {"id": uid, "scope": scope},
            )
