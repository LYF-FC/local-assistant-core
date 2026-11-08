from uuid import uuid4

import pytest
from test_memory import signin
from test_work_access import URL, setup_work

from app import work_adapter, work_interface
from app.config import settings


def request_body(**changes):
    return {
        "selections": [{"id": str(uuid4()), "expected_revision": 1}],
        "purpose": "preview",
        **changes,
    }


def test_export_default_auth_csrf_scope_and_no_store(auth_client, auth_store):
    ids = setup_work(auth_store)
    url = f"{URL}/{ids['synthetic-team-a']}/notes/export"
    body = request_body()
    assert auth_client.post(url, json=body).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json=body).status_code == 403
    response = auth_client.post(url, json=body, headers=headers)
    assert response.status_code == 503 and "bundle" not in response.json()
    assert response.headers["cache-control"] == "no-store"
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/notes/export", json=body, headers=headers
        ).status_code
        == 404
    )
    assert (
        auth_client.post(
            url, json=body, headers=dict(headers, Origin="https://unapproved.invalid")
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "change",
    [
        {"selections": []},
        {"selections": [{"id": str(uuid4()), "expected_revision": 1}] * 2},
        {"selections": [{"id": str(uuid4()), "expected_revision": 1} for _ in range(11)]},
        {"selections": [{"id": str(uuid4()), "expected_revision": True}]},
        {"selections": [{"id": str(uuid4()), "expected_revision": 101}]},
        {"include_drafts": "true"},
        {"purpose": "write"},
        {"purpose": "download"},
        {"purpose": "download", "acknowledge_copy_limits": True},
        {"purpose": "download", "reviewed_hash": "a" * 64},
        {"purpose": "download", "reviewed_hash": "a" * 64, "acknowledge_copy_limits": "yes"},
        {"reviewed_hash": "a" * 64},
        {"acknowledge_copy_limits": True},
        {"actor_id": str(uuid4())},
    ],
)
def test_export_strict_bounded_review_decision(auth_client, auth_store, change):
    ids = setup_work(auth_store)
    result = auth_client.post(
        f"{URL}/{ids['synthetic-team-a']}/notes/export",
        json=request_body(**change),
        headers=signin(auth_client),
    )
    assert result.status_code == 422 and result.json() == {"detail": "Invalid request"}


def test_export_authority_precedes_secret_loading(auth_client, auth_store, monkeypatch, tmp_path):
    ids = setup_work(auth_store)
    for name, value in (
        ("work_notes_export_enabled", True),
        ("work_notes_interface_enabled", True),
        ("work_synthetic_adapter_enabled", True),
        ("postgres_db", "butler_test"),
        ("work_synthetic_secret_directory", tmp_path),
    ):
        monkeypatch.setattr(settings, name, value)
    calls = []

    def missing(directory):
        calls.append(True)
        raise FileNotFoundError("private-export-secret-sentinel")

    monkeypatch.setattr(work_adapter, "load_bundle", missing)
    url = f"{URL}/{ids['synthetic-team-a']}/notes/export"
    body = request_body()
    assert auth_client.post(url, json=body).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json=body).status_code == 403
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/notes/export", json=body, headers=headers
        ).status_code
        == 404
    )
    assert calls == []
    result = auth_client.post(url, json=body, headers=headers)
    assert (
        result.status_code == 503 and calls == [True] and "private-export-secret" not in result.text
    )


def test_export_flag_is_independent_and_local_only(monkeypatch):
    monkeypatch.setattr(settings, "work_notes_interface_enabled", True)
    monkeypatch.setattr(settings, "work_notes_export_enabled", False)
    assert work_interface.get_export_engines() is None
    monkeypatch.setattr(settings, "work_notes_export_enabled", True)
    monkeypatch.setattr(settings, "env", "production")
    assert work_interface.get_export_engines() is None
