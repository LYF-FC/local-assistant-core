"""Actual runtime-role restrictions and committed work-grant revocation."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models import User
from app.work_manage import administer

pytestmark = pytest.mark.integration


def test_runtime_reads_explicit_workspace_and_current_admin_revocation(scenario):
    client, _, _, admin, user_id = scenario
    slug = "synthetic-" + uuid4().hex
    with admin.begin() as db:
        user_slug = db.get(User, user_id).slug
        administer(db, "create-workspace", slug)
        administer(db, "grant", slug, user_slug)
    page = client.get("/api/v1/work/workspaces").json()
    assert len(page["items"]) == 1 and page["items"][0]["slug"] == slug
    workspace_id = page["items"][0]["id"]
    url = f"/api/v1/work/workspaces/{workspace_id}/status"
    assert client.get(url).json()["ingestion_allowed"] is False
    with admin.begin() as db:
        administer(db, "revoke", slug, user_slug)
    assert client.get(url).status_code == 404
    assert client.get("/api/v1/work/workspaces").json()["items"] == []


@pytest.mark.parametrize("table", ["work_workspaces", "work_access_grants"])
@pytest.mark.parametrize("operation", ["INSERT", "UPDATE", "DELETE", "TRUNCATE"])
def test_runtime_cannot_administer_work_registry(runtime_engine, table, operation):
    with runtime_engine.begin() as connection:
        allowed = connection.execute(
            text("SELECT has_table_privilege(current_user, :table, :operation)"),
            {"table": table, "operation": operation},
        ).scalar_one()
        assert allowed is False
    statement = {
        "INSERT": f"INSERT INTO {table} DEFAULT VALUES",
        "UPDATE": f"UPDATE {table} SET created_at=created_at WHERE false",
        "DELETE": f"DELETE FROM {table} WHERE false",
        "TRUNCATE": f"TRUNCATE {table}",
    }[operation]
    with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
        connection.execute(text(statement))
