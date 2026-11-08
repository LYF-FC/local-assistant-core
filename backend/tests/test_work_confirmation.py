from uuid import uuid4

import pytest
from test_memory import signin
from test_work_access import URL, setup_work

from app import work_confirmation
from app.config import settings


def payload(**changes):
    value = {
        "review_preparation_id": str(uuid4()),
        "expected_revision": 1,
        "request_id": str(uuid4()),
        "decision": "confirm_note",
    }
    value.update(changes)
    return value


def test_confirmation_is_independently_disabled(monkeypatch):
    monkeypatch.setattr(settings, "work_synthetic_adapter_enabled", True)
    monkeypatch.setattr(settings, "work_draft_review_enabled", True)
    monkeypatch.setattr(settings, "work_draft_confirmation_enabled", False)
    assert work_confirmation.get_confirmation_engines() is None


def test_confirmation_identity_before_default_disabled_storage(auth_client, auth_store):
    ids = setup_work(auth_store)
    url = f"{URL}/{ids['synthetic-team-a']}/drafts/{uuid4()}/confirm"
    assert auth_client.post(url, json=payload()).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json=payload()).status_code == 403
    response = auth_client.post(url, json=payload(), headers=headers)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert (
        auth_client.post(
            url.replace(str(ids["synthetic-team-a"]), str(ids["synthetic-team-b"])),
            json=payload(),
            headers=headers,
        ).status_code
        == 404
    )
    status = f"{URL}/{ids['synthetic-team-a']}/confirmations/{uuid4()}/status"
    assert auth_client.post(status, json={}, headers=headers).status_code == 503


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "approve"},
        {"expected_revision": True},
        {"expected_revision": 100},
        {"expected_revision": 0},
        {"request_id": "invalid"},
        {"review_preparation_id": "invalid"},
        {"actor_id": str(uuid4())},
        {"session_id": str(uuid4())},
        {"marker": "synthetic:forged"},
        {"payload_hash": "a" * 64},
        {"state": "applied"},
    ],
)
def test_confirmation_cannot_forge_binding(auth_client, changes):
    response = auth_client.post(
        f"{URL}/{uuid4()}/drafts/{uuid4()}/confirm", json=payload(**changes)
    )
    assert response.status_code == 422


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_confirmation_cannot_activate_outside_local_synthetic_target(monkeypatch, environment):
    monkeypatch.setattr(settings, "env", environment)
    monkeypatch.setattr(settings, "work_draft_confirmation_enabled", True)
    monkeypatch.setattr(settings, "work_draft_review_enabled", True)
    monkeypatch.setattr(settings, "work_synthetic_adapter_enabled", True)
    assert work_confirmation.get_confirmation_engines() is None
