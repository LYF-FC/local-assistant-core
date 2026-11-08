from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from test_memory import signin
from test_work_access import URL, setup_work

from app import work_adapter, work_notes
from app.config import settings


def body(action="correct", **changes):
    data = {"request_id": str(uuid4()), "decision": f"{action}_note", "expected_revision": 1}
    if action == "correct":
        data["draft"] = {
            "kind": "decision",
            "marker": "synthetic:corrected-input",
            "source_ids": [str(uuid4())],
            "retain_until": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }
    data.update(changes)
    return data


@pytest.mark.parametrize("action", ["correct", "forget"])
def test_default_disabled_identity_csrf_scope_boundary(auth_client, auth_store, action):
    ids = setup_work(auth_store)
    url = f"{URL}/{ids['synthetic-team-a']}/drafts/{uuid4()}/{action}"
    assert auth_client.post(url, json=body(action)).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json=body(action)).status_code == 403
    response = auth_client.post(url, json=body(action), headers=headers)
    assert response.status_code == 503 and response.json() == {
        "detail": "Synthetic note change unavailable"
    }
    assert response.headers["cache-control"] == "no-store"
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/drafts/{uuid4()}/{action}",
            json=body(action),
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        auth_client.post(
            url, json=body(action), headers=dict(headers, Origin="https://unapproved.invalid")
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "action,changes",
    [
        ("correct", {"expected_revision": True}),
        ("correct", {"expected_revision": 100}),
        ("forget", {"expected_revision": 101}),
        ("forget", {"expected_revision": 0}),
        ("forget", {"draft": {"marker": "synthetic:unexpected"}}),
        ("correct", {"actor_id": str(uuid4())}),
        ("forget", {"session_id": str(uuid4())}),
        ("forget", {"decision": "execute"}),
        ("correct", {"decision": "forget_note"}),
        ("correct", {"draft": None}),
        ("correct", {"policy_id": str(uuid4())}),
        ("forget", {"request_id": "invalid"}),
    ],
)
def test_strict_change_contract(auth_client, auth_store, action, changes):
    ids = setup_work(auth_store)
    headers = signin(auth_client)
    response = auth_client.post(
        f"{URL}/{ids['synthetic-team-a']}/drafts/{uuid4()}/{action}",
        json=body(action, **changes),
        headers=headers,
    )
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}


def test_denials_precede_note_change_secret_read(auth_client, auth_store, monkeypatch, tmp_path):
    ids = setup_work(auth_store)
    for key, value in (
        ("work_note_changes_enabled", True),
        ("work_synthetic_adapter_enabled", True),
        ("postgres_db", "butler_test"),
        ("work_synthetic_secret_directory", tmp_path),
    ):
        monkeypatch.setattr(settings, key, value)
    calls = []

    def missing(directory):
        calls.append(True)
        raise FileNotFoundError("private-note-change-secret")

    monkeypatch.setattr(work_adapter, "load_bundle", missing)
    url = f"{URL}/{ids['synthetic-team-a']}/drafts/{uuid4()}/forget"
    assert auth_client.post(url, json=body("forget")).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json=body("forget")).status_code == 403
    assert calls == []
    response = auth_client.post(url, json=body("forget"), headers=headers)
    assert (
        response.status_code == 503
        and calls == [True]
        and "private-note-change-secret" not in response.text
    )


def test_change_flag_and_environment_are_independent(monkeypatch):
    monkeypatch.setattr(settings, "work_synthetic_capture_enabled", True)
    monkeypatch.setattr(settings, "work_note_changes_enabled", False)
    assert work_notes.get_change_engines() is None
    monkeypatch.setattr(settings, "work_note_changes_enabled", True)
    monkeypatch.setattr(settings, "env", "production")
    assert work_notes.get_change_engines() is None
