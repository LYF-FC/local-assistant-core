from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from test_memory import signin
from test_work_access import URL, setup_work

from app import work_adapter, work_capture
from app.config import settings


def body(**changes):
    data = {
        "request_id": str(uuid4()),
        "decision": "capture_draft",
        "policy_id": str(uuid4()),
        "draft": {
            "kind": "action",
            "marker": "synthetic:capture-input",
            "source_ids": [str(uuid4())],
            "retain_until": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
    }
    data.update(changes)
    return data


def test_default_denial_and_permission_boundary(auth_client, auth_store):
    ids = setup_work(auth_store)
    url = f"{URL}/{ids['synthetic-team-a']}/captures"
    assert auth_client.post(url, json=body()).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json=body()).status_code == 403
    result = auth_client.post(url, json=body(), headers=headers)
    assert result.status_code == 503 and result.json() == {
        "detail": "Synthetic capture unavailable"
    }
    assert result.headers["cache-control"] == "no-store"
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/captures", json=body(), headers=headers
        ).status_code
        == 404
    )
    assert (
        auth_client.post(
            url, json=body(), headers=dict(headers, Origin="https://unapproved.invalid")
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "fault",
    [
        "request_id",
        "decision",
        "actor_id",
        "session_id",
        "workspace_id",
        "marker",
        "source_empty",
        "source_duplicate",
        "source_many",
        "source_unknown",
        "owner",
        "retain",
        "due",
        "state",
        "policy",
    ],
)
def test_strict_body_rejects_forged_identity_and_unbounded_content(auth_client, auth_store, fault):
    ids = setup_work(auth_store)
    headers = signin(auth_client)
    value = body()
    if fault in {"actor_id", "session_id", "workspace_id"}:
        value[fault] = str(uuid4())
    elif fault == "request_id":
        value[fault] = "invalid"
    elif fault == "decision":
        value[fault] = "execute"
    elif fault == "marker":
        value["draft"]["marker"] = "real-content-is-not-supported"
    elif fault == "source_empty":
        value["draft"]["source_ids"] = []
    elif fault == "source_duplicate":
        value["draft"]["source_ids"] *= 2
    elif fault == "source_many":
        value["draft"]["source_ids"] = [str(uuid4()) for _ in range(11)]
    elif fault == "source_unknown":
        value["draft"]["source_ids"] = ["not-an-id"]
    elif fault == "owner":
        value["draft"]["owner_id"] = "not-an-id"
    elif fault == "retain":
        value["draft"]["retain_until"] = "2026-11-05T12:00:00"
    elif fault == "due":
        value["draft"]["due_at"] = "2026-11-05T12:00:00"
    elif fault == "state":
        value["draft"]["state"] = "confirmed"
    elif fault == "policy":
        value["policy_id"] = "not-an-id"
    response = auth_client.post(
        f"{URL}/{ids['synthetic-team-a']}/captures", json=value, headers=headers
    )
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}


def test_denied_requests_never_load_capture_credentials(
    auth_client, auth_store, monkeypatch, tmp_path
):
    ids = setup_work(auth_store)
    for key, value in (
        ("work_synthetic_capture_enabled", True),
        ("work_synthetic_adapter_enabled", True),
        ("postgres_db", "butler_test"),
        ("work_synthetic_secret_directory", tmp_path),
    ):
        monkeypatch.setattr(settings, key, value)
    calls = []

    def missing(directory):
        calls.append(True)
        raise FileNotFoundError("private-capture-secret-path")

    monkeypatch.setattr(work_adapter, "load_bundle", missing)
    url = f"{URL}/{ids['synthetic-team-a']}/captures"
    assert auth_client.post(url, json=body()).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json=body()).status_code == 403
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/captures", json=body(), headers=headers
        ).status_code
        == 404
    )
    assert calls == []
    response = auth_client.post(url, json=body(), headers=headers)
    assert response.status_code == 503 and calls == [True]
    assert "private-capture-secret-path" not in response.text


def test_capture_flag_and_environment_are_independent(monkeypatch):
    monkeypatch.setattr(settings, "work_synthetic_adapter_enabled", True)
    monkeypatch.setattr(settings, "work_synthetic_capture_enabled", False)
    assert work_capture.get_capture_engines() is None
    monkeypatch.setattr(settings, "work_synthetic_capture_enabled", True)
    monkeypatch.setattr(settings, "env", "production")
    assert work_capture.get_capture_engines() is None


def test_non_synthetic_workspace_is_denied_before_private_access(auth_client, auth_store):
    from app.models import WorkWorkspace

    ids = setup_work(auth_store)
    with auth_store.begin() as db:
        workspace = db.get(WorkWorkspace, UUID(ids["synthetic-team-a"]))
        workspace.slug = "unsupported-real-workspace"
    headers = signin(auth_client)
    response = auth_client.post(
        f"{URL}/{ids['synthetic-team-a']}/captures", json=body(), headers=headers
    )
    assert response.status_code == 404
