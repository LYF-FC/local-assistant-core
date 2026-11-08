from uuid import uuid4

import pytest
from test_memory import signin
from test_work_access import URL, setup_work

from app import work_adapter, work_review
from app.config import settings


def body(**changes):
    value = {
        "expected_revision": 1,
        "reviewed_hash": "a" * 64,
        "request_id": str(uuid4()),
        "decision": "approve",
    }
    value.update(changes)
    return value


def test_default_disabled_routes_keep_identity_csrf_and_workspace_boundary(auth_client, auth_store):
    ids = setup_work(auth_store)
    url = f"{URL}/{ids['synthetic-team-a']}/drafts/{uuid4()}"
    assert auth_client.post(url + "/preview", json={}).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url + "/preview", json={}).status_code == 403
    for suffix, payload in (("preview", {}), ("review", body())):
        response = auth_client.post(url + "/" + suffix, json=payload, headers=headers)
        assert response.status_code == 503 and response.json() == {
            "detail": "Synthetic review unavailable"
        }
        assert response.headers["cache-control"] == "no-store"
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/drafts/{uuid4()}/review", json=body(), headers=headers
        ).status_code
        == 404
    )
    assert (
        auth_client.post(
            url + "/review", json=body(), headers=dict(headers, Origin="https://unapproved.invalid")
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_revision": True},
        {"expected_revision": 0},
        {"expected_revision": 101},
        {"reviewed_hash": "A" * 64},
        {"reviewed_hash": "short"},
        {"request_id": "not-a-uuid"},
        {"decision": "execute"},
        {"actor_id": str(uuid4())},
        {"session_id": str(uuid4())},
        {"marker": "synthetic:forged"},
        {"sql": "SELECT 1"},
        {"intent": "send"},
    ],
)
def test_review_body_cannot_forge_identity_content_or_action(auth_client, auth_store, changes):
    ids = setup_work(auth_store)
    headers = signin(auth_client)
    response = auth_client.post(
        f"{URL}/{ids['synthetic-team-a']}/drafts/{uuid4()}/review",
        json=body(**changes),
        headers=headers,
    )
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}


def test_preview_accepts_no_client_payload_and_review_requires_explicit_approval(
    auth_client, auth_store
):
    ids = setup_work(auth_store)
    headers = signin(auth_client)
    url = f"{URL}/{ids['synthetic-team-a']}/drafts/{uuid4()}"
    assert (
        auth_client.post(
            url + "/preview", json={"record_id": str(uuid4())}, headers=headers
        ).status_code
        == 422
    )
    value = body()
    del value["decision"]
    assert auth_client.post(url + "/review", json=value, headers=headers).status_code == 422


def test_review_opt_in_is_independent_of_existing_adapter(monkeypatch):
    monkeypatch.setattr(settings, "work_synthetic_adapter_enabled", True)
    monkeypatch.setattr(settings, "work_draft_review_enabled", False)
    assert work_review.get_review_engines() is None


def test_denied_requests_never_load_private_review_credentials(
    auth_client, auth_store, monkeypatch, tmp_path
):
    ids = setup_work(auth_store)
    monkeypatch.setattr(settings, "work_synthetic_adapter_enabled", True)
    monkeypatch.setattr(settings, "work_draft_review_enabled", True)
    monkeypatch.setattr(settings, "work_synthetic_secret_directory", tmp_path)
    calls = []

    def unavailable(directory):
        calls.append(True)
        raise FileNotFoundError("synthetic-private-file-location")

    monkeypatch.setattr(work_adapter, "load_bundle", unavailable)
    url = f"{URL}/{ids['synthetic-team-a']}/drafts/{uuid4()}/preview"
    assert auth_client.post(url, json={}).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json={}).status_code == 403
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/drafts/{uuid4()}/preview", json={}, headers=headers
        ).status_code
        == 404
    )
    assert calls == []
    response = auth_client.post(url, json={}, headers=headers)
    assert response.status_code == 503 and calls == [True]
    assert "synthetic-private-file-location" not in response.text
