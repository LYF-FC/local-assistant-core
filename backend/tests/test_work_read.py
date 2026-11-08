from dataclasses import FrozenInstanceError
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from test_memory import signin
from test_work_access import URL, setup_work

from app import work_read
from app.main import app


def test_engine_mapping_is_immutable_and_copies_input():
    engine = create_engine("sqlite://")
    identifier = uuid4()
    source = {identifier: engine}
    registry = work_read.WorkspaceEngines(source)
    source.clear()
    assert registry.engine_for(identifier) is engine
    with pytest.raises(FrozenInstanceError):
        registry._engines = {}
    assert "sqlite" not in repr(registry)
    with pytest.raises(TypeError):
        work_read.WorkspaceEngines({"untrusted": engine})
    assert work_read.get_work_engines() is None
    engine.dispose()


def test_disabled_route_still_requires_current_identity_csrf_and_workspace(auth_client, auth_store):
    ids = setup_work(auth_store)
    url = f"{URL}/{ids['synthetic-team-a']}/validation-read"
    assert auth_client.post(url, json={}).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json={}).status_code == 403
    assert (
        auth_client.post(
            url, json={}, headers=dict(headers, Origin="https://other.invalid")
        ).status_code
        == 403
    )
    response = auth_client.post(url, json={}, headers=headers)
    assert response.status_code == 503 and response.json() == {
        "detail": "Work validation unavailable"
    }
    assert response.headers["cache-control"] == "no-store"
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/validation-read", json={}, headers=headers
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "body",
    [
        {"limit": True},
        {"limit": 0},
        {"limit": 26},
        {"sql": "SELECT secret"},
        {"user_id": str(uuid4())},
        {"engine": "postgresql://untrusted"},
    ],
)
def test_caller_cannot_supply_sql_identity_connections_or_unbounded_read(
    auth_client, auth_store, body
):
    ids = setup_work(auth_store)
    headers = signin(auth_client)
    result = auth_client.post(
        f"{URL}/{ids['synthetic-team-a']}/validation-read", json=body, headers=headers
    )
    assert result.status_code == 422 and result.json() == {"detail": "Invalid request"}


def test_unassigned_request_never_reaches_an_injected_storage_engine(auth_client, auth_store):
    ids = setup_work(auth_store)
    engine = create_engine("sqlite://")
    mapping = work_read.WorkspaceEngines({UUID(ids["synthetic-team-b"]): engine})
    app.dependency_overrides[work_read.get_work_engines] = lambda: mapping
    try:
        headers = signin(auth_client)
        response = auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/validation-read", json={}, headers=headers
        )
        assert response.status_code == 404
        # Assigned-but-invalid adapter also fails closed, with no SQLite work query.
        app.dependency_overrides[work_read.get_work_engines] = lambda: work_read.WorkspaceEngines(
            {UUID(ids["synthetic-team-a"]): engine}
        )
        response = auth_client.post(
            f"{URL}/{ids['synthetic-team-a']}/validation-read", json={}, headers=headers
        )
        assert response.status_code == 503 and "items" not in response.json()
    finally:
        app.dependency_overrides.pop(work_read.get_work_engines, None)
        engine.dispose()


def test_engine_builder_requires_explicit_trusted_url():
    from sqlalchemy.engine import URL

    with pytest.raises(TypeError):
        work_read.workspace_engine("untrusted")
    with pytest.raises(work_read.BrokerUnavailable):
        work_read.workspace_engine(
            URL.create("postgresql+psycopg", host="localhost", database="butler_test")
        )
