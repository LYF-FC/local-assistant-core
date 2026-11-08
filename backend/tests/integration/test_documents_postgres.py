"""Actual restricted PostgreSQL role, seals, atomic content lifecycle and row waits."""

import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_documents import call, lifecycle, upload

from app.models import DocumentVersion

pytestmark = pytest.mark.integration


def test_runtime_originals_versions_search_citations_and_scrub(scenario):
    client, h, _, admin, _ = scenario
    tomb = lifecycle(client, h)
    with admin() as db:
        versions = list(
            db.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == UUID(tomb["id"]))
            )
        )
        assert len(versions) == 4 and all(
            v.snapshot is None and v.original_bytes is None for v in versions
        )


@pytest.mark.parametrize(
    "change",
    [
        "owner_id=:other,revision=revision+1",
        "scope_key='member_a_private',revision=revision+1",
        "id=:other,revision=revision+1",
        "created_at=created_at+interval '1s',revision=revision+1",
        "revision=revision+2",
        "title='Synthetic bypass'",
        "title=NULL,revision=revision+1",
        "sha256=repeat('0',64),revision=revision+1",
        "content_text='tampered',revision=revision+1",
        "byte_size=99,revision=revision+1",
        "filename='../escape.txt',revision=revision+1",
        "filename=E'back\\\\slash.txt',revision=revision+1",
        "filename='source.pdf',revision=revision+1",
        "updated_at=updated_at-interval '1s',revision=revision+1",
    ],
)
def test_raw_record_bypass_is_sealed(scenario, runtime_engine, change):
    client, h, _, _, _ = scenario
    row = upload(client, h).json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(f"UPDATE document_records SET {change} WHERE id=:id"),
            {"id": UUID(row["id"]), "other": uuid4()},
        )
    assert call(client, h, row, "read").json()["revision"] == 1


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM document_records WHERE id=:id",
        "TRUNCATE document_records CASCADE",
        "DELETE FROM document_versions WHERE document_id=:id",
        "TRUNCATE document_versions",
        "UPDATE document_versions SET snapshot=NULL,original_bytes=NULL WHERE document_id=:id",
        "UPDATE document_versions SET original_bytes=convert_to('forged','UTF8') WHERE document_id=:id",
        "UPDATE document_versions SET revision=99 WHERE document_id=:id",
        "UPDATE user_scopes SET created_at=created_at",
        "SELECT metadata_json FROM audit_events",
    ],
)
def test_runtime_grants_and_active_history_are_sealed(scenario, runtime_engine, statement):
    client, h, _, _, _ = scenario
    row = upload(client, h).json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(statement), {"id": UUID(row["id"])})


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM document_records WHERE id=:id",
        "TRUNCATE document_records CASCADE",
        "DELETE FROM document_versions WHERE document_id=:id",
        "TRUNCATE document_versions",
        "UPDATE document_versions SET snapshot=NULL,original_bytes=NULL WHERE document_id=:id",
    ],
)
def test_ordinary_migration_owner_sql_also_has_seals(scenario, statement):
    client, h, _, admin, _ = scenario
    row = upload(client, h).json()
    with admin.begin() as db, pytest.raises(DBAPIError):
        db.execute(text(statement), {"id": UUID(row["id"])})


def test_forged_snapshot_and_bytes_cannot_be_appended(scenario):
    client, h, _, admin, _ = scenario
    row = upload(client, h).json()
    with admin.begin() as db:
        db.execute(
            text(
                "UPDATE document_records SET title='Synthetic second',revision=revision+1 WHERE id=:id"
            ),
            {"id": UUID(row["id"])},
        )
    for change in [
        "jsonb_set(snapshot,'{title}','\"forged\"')",
        "snapshot || jsonb_build_object('extra',true)",
        "jsonb_set(snapshot,'{sha256}','\"bad\"')",
    ]:
        with admin.begin() as db, pytest.raises(DBAPIError):
            db.execute(
                text(f"""INSERT INTO document_versions(id,document_id,revision,actor_id,operation,snapshot,original_bytes,created_at)
              SELECT :new,document_id,2,actor_id,'corrected',{change},original_bytes,created_at FROM document_versions WHERE document_id=:id"""),
                {"new": uuid4(), "id": UUID(row["id"])},
            )


def test_forget_terminal_and_redacted_versions_cannot_resurrect(scenario, runtime_engine):
    client, h, _, _, _ = scenario
    row = upload(client, h).json()
    tomb = call(client, h, row, "forget").json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text("UPDATE document_records SET revision=revision+1 WHERE id=:id"),
            {"id": UUID(row["id"])},
        )
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "UPDATE document_versions SET snapshot='{}',original_bytes=''::bytea WHERE document_id=:id"
            ),
            {"id": UUID(row["id"])},
        )
    assert call(client, h, tomb, "original").status_code == 410


def test_current_revision_rechecked_after_actual_row_wait(scenario, postgres_engine):
    client, h, _, admin, _ = scenario
    row = upload(client, h).json()
    with admin.begin() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.execute(
            text("SELECT id FROM document_records WHERE id=:id FOR UPDATE"), {"id": UUID(row["id"])}
        )
        future = pool.submit(call, client, h, row, "original")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with postgres_engine.connect() as inspect:
                waiting = inspect.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE usename='butler_runtime' AND wait_event_type='Lock' AND query LIKE '%document_records%'"
                    )
                )
            if waiting:
                break
            time.sleep(0.02)
        assert waiting and not future.done()
        blocker.execute(
            text(
                "UPDATE document_records SET title='Synthetic concurrent',revision=revision+1 WHERE id=:id"
            ),
            {"id": UUID(row["id"])},
        )
        blocker.commit()
        response = future.result(timeout=5)
    assert response.status_code == 409


@pytest.mark.parametrize("operation", ["read", "original", "excerpt", "history", "export"])
def test_expiry_rechecked_after_real_document_lock_wait(
    scenario, postgres_engine, monkeypatch, operation
):
    from datetime import timedelta

    from app import identity
    from app.models import AuthSession

    client, h, _, admin, uid = scenario
    row = upload(client, h, title="Synthetic expiry " + uuid4().hex).json()
    row = call(client, h, row, "correct", title=row["title"]).json()
    with admin() as db:
        expiry = db.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == uid))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as blocker:
            blocker.execute(
                text("SELECT id FROM document_records WHERE id=:id FOR UPDATE"),
                {"id": UUID(row["id"])},
            )
            if operation == "export":
                future = pool.submit(
                    client.post,
                    "/api/v1/documents/export",
                    headers=h,
                    json={
                        "scope": row["scope"],
                        "search": row["title"],
                        "acknowledge_copy_limits": True,
                    },
                )
            else:
                future = pool.submit(
                    call,
                    client,
                    h,
                    row,
                    operation,
                    **({"end_line": 1} if operation == "excerpt" else {}),
                )
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with postgres_engine.connect() as inspect:
                    waiting = inspect.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE usename='butler_runtime' AND wait_event_type='Lock' AND query LIKE '%document_records%'"
                        )
                    )
                if waiting:
                    break
                time.sleep(0.02)
            assert waiting
            monkeypatch.setattr(
                identity, "now_utc", lambda: identity.aware(expiry) + timedelta(seconds=1)
            )
        response = future.result(timeout=5)
    assert (
        response.status_code == 401
        and "original_base64" not in response.json()
        and "items" not in response.json()
    )


def test_owner_quota_serializes_concurrent_uploads(scenario, monkeypatch):
    from app import documents

    client, h, _, _, _ = scenario
    monkeypatch.setattr(documents, "MAX_ACTIVE", 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(upload, client, h, title="Synthetic quota " + str(i)) for i in range(2)
        ]
        assert sorted(f.result(timeout=10).status_code for f in futures) == [201, 409]


@pytest.mark.parametrize("operation", ["forget", "replace", "original"])
def test_audit_failure_preserves_original_history_and_releases_no_content(
    scenario, runtime_engine, operation
):
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError
    from test_documents import ORIGINAL

    from app.models import DocumentRecord

    client, h, _, admin, _ = scenario
    row = upload(client, h).json()

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic document audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        changes = (
            {"filename": "replacement.txt", "original_base64": "YQ=="}
            if operation == "replace"
            else {}
        )
        response = call(client, h, row, operation, **changes)
        assert response.status_code == 503 and "original_base64" not in response.json()
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    with admin() as db:
        assert db.get(DocumentRecord, UUID(row["id"])).revision == 1
        versions = list(
            db.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == UUID(row["id"]))
            )
        )
        assert (
            len(versions) == 1
            and versions[0].original_bytes == ORIGINAL
            and versions[0].snapshot["title"] == row["title"]
        )


def test_null_original_size_cannot_bypass_content_shape(scenario, runtime_engine):
    client, h, _, _, _ = scenario
    row = upload(client, h).json()
    with runtime_engine.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text("UPDATE document_records SET byte_size=NULL,revision=revision+1 WHERE id=:id"),
            {"id": UUID(row["id"])},
        )


def test_multibyte_character_boundary_and_excerpt_byte_budget(scenario):
    import base64
    import hashlib

    client, h, _, _, _ = scenario
    original = ("é😀" * 16000).encode("utf-8")
    response = upload(
        client, h, filename="café.md", original_base64=base64.b64encode(original).decode()
    )
    assert response.status_code == 201
    row = response.json()
    assert len(row["content_text"]) == 32000 and row["byte_size"] == 96000
    assert row["sha256"] == hashlib.sha256(original).hexdigest()
    row = call(client, h, row, "correct").json()
    assert call(client, h, row, "excerpt", end_line=1).status_code == 422
    assert base64.b64decode(call(client, h, row, "original").json()["original_base64"]) == original
