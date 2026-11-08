from uuid import uuid4

import pytest
from test_memory import signin
from test_work_access import URL, setup_work

from app import work_adapter, work_context
from app.config import settings


def selection(**changes):
    value = {"selections": [{"id": str(uuid4()), "expected_revision": 2}]}
    value.update(changes)
    return value


def test_context_denials_precede_secret_access(auth_client, auth_store, monkeypatch, tmp_path):
    ids = setup_work(auth_store)
    monkeypatch.setattr(settings, "postgres_db", "butler_test")
    monkeypatch.setattr(settings, "work_synthetic_adapter_enabled", True)
    monkeypatch.setattr(settings, "work_context_preview_enabled", True)
    monkeypatch.setattr(settings, "work_synthetic_secret_directory", tmp_path)
    calls = []

    def missing(directory):
        calls.append(True)
        raise FileNotFoundError("private-context-secret-path")

    monkeypatch.setattr(work_adapter, "load_bundle", missing)
    url = f"{URL}/{ids['synthetic-team-a']}/context/preview"
    assert auth_client.post(url, json=selection()).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json=selection()).status_code == 403
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/context/preview", json=selection(), headers=headers
        ).status_code
        == 404
    )
    assert (
        auth_client.post(
            url, json=selection(), headers=dict(headers, Origin="https://unapproved.invalid")
        ).status_code
        == 403
    )
    assert calls == []
    response = auth_client.post(url, json=selection(), headers=headers)
    assert response.status_code == 503 and calls == [True]
    assert "private-context-secret-path" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "changes",
    [
        {"selections": []},
        {"selections": [{"id": str(uuid4()), "expected_revision": 2}] * 2},
        {"selections": [{"id": str(uuid4()), "expected_revision": 2} for _ in range(11)]},
        *(
            {"selections": [{"id": str(uuid4()), "expected_revision": rev}]}
            for rev in (True, 0, 101, "2")
        ),
        {"selections": [{"id": "invalid", "expected_revision": 2}]},
        {
            "selections": [
                {"id": str(uuid4()), "expected_revision": 2, "marker": "synthetic:forged"}
            ]
        },
        {"max_bytes": 255},
        {"max_bytes": 16385},
        {"max_bytes": True},
        {"actor_id": str(uuid4())},
        {"scope": "household_shared"},
        {"dispatch": True},
    ],
)
def test_strict_context_selection(auth_client, auth_store, changes):
    ids = setup_work(auth_store)
    headers = signin(auth_client)
    response = auth_client.post(
        f"{URL}/{ids['synthetic-team-a']}/context/preview",
        json=selection(**changes),
        headers=headers,
    )
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}


def test_default_and_environment_gates(monkeypatch):
    monkeypatch.setattr(settings, "work_synthetic_adapter_enabled", True)
    monkeypatch.setattr(settings, "work_context_preview_enabled", False)
    assert work_context.get_context_engines() is None
    monkeypatch.setattr(settings, "work_context_preview_enabled", True)
    monkeypatch.setattr(settings, "env", "production")
    assert work_context.get_context_engines() is None
    monkeypatch.setattr(settings, "env", "test")
    monkeypatch.setattr(settings, "postgres_db", "butler_production")
    assert work_context.get_context_engines() is None


def test_default_disabled_authenticated_context(auth_client, auth_store):
    ids = setup_work(auth_store)
    headers = signin(auth_client)
    response = auth_client.post(
        f"{URL}/{ids['synthetic-team-a']}/context/preview", json=selection(), headers=headers
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Synthetic context unavailable"}
