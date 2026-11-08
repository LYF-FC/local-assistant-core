"""Real runtime role, immutable obligations and current-authority archive locks."""

import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_document_archiving import archive_call, lifecycle
from test_documents import call, upload

pytestmark = pytest.mark.integration


def test_runtime_archive_lifecycle(scenario, configured_archive):
    client, h, _, _, _ = scenario
    lifecycle(client, h, configured_archive)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM document_archive_bindings WHERE document_id=:id",
        "UPDATE document_archive_bindings SET root_id=:other WHERE document_id=:id",
        "TRUNCATE document_archive_bindings",
    ],
)
def test_binding_is_sealed_for_runtime_and_ordinary_owner(
    scenario, runtime_engine, configured_archive, sql
):
    client, h, _, admin, _ = scenario
    row = upload(client, h).json()
    assert archive_call(client, h, row, True).status_code == 200
    for maker in [runtime_engine, admin.kw["bind"]]:
        with maker.begin() as db, pytest.raises(DBAPIError):
            db.execute(text(sql), {"id": UUID(row["id"]), "other": uuid4()})
    assert call(client, h, row, "forget").status_code == 200


def test_stale_revision_after_real_lock_wait_never_copies(
    scenario, postgres_engine, configured_archive
):
    client, h, _, admin, _ = scenario
    row = upload(client, h).json()
    with admin.begin() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.execute(
            text("SELECT id FROM document_records WHERE id=:id FOR UPDATE"), {"id": UUID(row["id"])}
        )
        future = pool.submit(archive_call, client, h, row, True)
        waiting = 0
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with postgres_engine.connect() as db:
                waiting = db.scalar(
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
        assert future.result(timeout=5).status_code == 409
    assert not list(configured_archive.glob("*.original"))
    current = call(client, h, row, "read").json()
    assert call(client, h, current, "forget").status_code == 200


def test_binding_to_forgotten_document_is_refused(scenario, configured_archive):
    client, h, _, admin, _ = scenario
    row = upload(client, h).json()
    assert call(client, h, row, "forget").status_code == 200
    with admin.begin() as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "INSERT INTO document_archive_bindings(document_id,root_id,created_at) VALUES(:id,:root,now())"
            ),
            {"id": UUID(row["id"]), "root": uuid4()},
        )
