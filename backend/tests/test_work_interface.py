from uuid import uuid4

import pytest
from test_memory import signin
from test_work_access import URL, setup_work

from app import work_adapter, work_interface
from app.config import settings


def test_default_interface_identity_csrf_scope_and_no_store(auth_client, auth_store):
    ids = setup_work(auth_store)
    url = f"{URL}/{ids['synthetic-team-a']}/notes/catalogue"
    assert auth_client.post(url, json={}).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json={}).status_code == 403
    response = auth_client.post(url, json={}, headers=headers)
    assert response.status_code == 503 and response.json() == {
        "detail": "Synthetic notes unavailable"
    }
    assert response.headers["cache-control"] == "no-store"
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/notes/catalogue", json={}, headers=headers
        ).status_code
        == 404
    )
    assert (
        auth_client.post(
            url, json={}, headers=dict(headers, Origin="https://unapproved.invalid")
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "body",
    [
        {"section": "everything"},
        {"limit": True},
        {"limit": 26},
        {"limit": 0},
        {"section": "setup", "after": str(uuid4())},
        {"actor_id": str(uuid4())},
        {"section": "requests", "request_id": str(uuid4())},
        {"operation": "capture_draft"},
        {"section": "sources", "request_id": str(uuid4()), "operation": "capture_draft"},
        {"section": "requests", "request_id": str(uuid4()), "operation": "execute"},
        {
            "section": "requests",
            "request_id": str(uuid4()),
            "operation": "capture_draft",
            "after": str(uuid4()),
        },
    ],
)
def test_strict_bounded_catalogue_body(auth_client, auth_store, body):
    ids = setup_work(auth_store)
    response = auth_client.post(
        f"{URL}/{ids['synthetic-team-a']}/notes/catalogue", json=body, headers=signin(auth_client)
    )
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}


def test_interface_denials_precede_credential_loading(
    auth_client, auth_store, monkeypatch, tmp_path
):
    ids = setup_work(auth_store)
    for name, value in (
        ("work_notes_interface_enabled", True),
        ("work_synthetic_adapter_enabled", True),
        ("postgres_db", "butler_test"),
        ("work_synthetic_secret_directory", tmp_path),
    ):
        monkeypatch.setattr(settings, name, value)
    calls = []

    def missing(directory):
        calls.append(True)
        raise FileNotFoundError("private-interface-secret")

    monkeypatch.setattr(work_adapter, "load_bundle", missing)
    url = f"{URL}/{ids['synthetic-team-a']}/notes/catalogue"
    assert auth_client.post(url, json={}).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json={}).status_code == 403
    assert calls == []
    response = auth_client.post(url, json={}, headers=headers)
    assert (
        response.status_code == 503
        and calls == [True]
        and "private-interface-secret" not in response.text
    )


def test_interface_opt_in_is_independent_and_dev_test_only(monkeypatch):
    monkeypatch.setattr(settings, "work_synthetic_capture_enabled", True)
    monkeypatch.setattr(settings, "work_notes_interface_enabled", False)
    assert work_interface.get_interface_engines() is None
    monkeypatch.setattr(settings, "work_notes_interface_enabled", True)
    monkeypatch.setattr(settings, "env", "production")
    assert work_interface.get_interface_engines() is None
