from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin

from app import identity, installation_catalog
from app.manage import set_scope
from app.models import AuditEvent, InstallationConfig, InstallationRevision, User

TEMPLATE = {"schema_version": 1, "defaults": {"languages": ["en", "fr"], "timezone": "UTC"}}


def admin_headers(client, store):
    with store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "technical_admin", True)
    return signin(client)


def call(client, h, op, record=None, **extra):
    payload = {"scope": "technical_admin"}
    if op in {"preview", "apply", "export"}:
        payload.update(
            expected_revision=record["revision"], expected_installation_id=record["installation_id"]
        )
    return client.post("/api/v1/installation/" + op, headers=h, json={**payload, **extra})


def current(client, h):
    r = call(client, h, "read")
    assert r.status_code == 200, r.json()
    return r.json()["record"]


def preview(client, h, record, template=None):
    r = call(client, h, "preview", record, template=TEMPLATE if template is None else template)
    assert r.status_code == 200, r.json()
    return r.json()


def apply_preview(client, h, p, **changes):
    body = {
        "template": p["template"],
        "preview_token": p["preview_token"],
        "expires_at": p["expires_at"],
        "confirm": True,
        **changes,
    }
    return call(client, h, "apply", p["record"], **body)


def configure(client, h, record, template=None):
    r = apply_preview(client, h, preview(client, h, record, template))
    assert r.status_code == 200, r.json()
    return r.json()["record"]


def test_explicit_initialization_revision_history_and_sanitized_template(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    r = current(auth_client, h)
    assert r["revision"] == 0 and r["installation_id"] is None
    p = preview(auth_client, h, r)
    assert p["creates_identity"] and p["changed_fields"] == ["languages", "timezone"]
    assert current(auth_client, h) == r
    saved = configure(auth_client, h, r)
    assert saved["revision"] == 1 and saved["installation_id"]
    assert apply_preview(auth_client, h, p).status_code == 409
    no_op = apply_preview(auth_client, h, preview(auth_client, h, saved))
    assert no_op.status_code == 200 and no_op.json()["changed"] is False
    exported = call(auth_client, h, "export", saved, acknowledge_copy_limits=True).json()
    assert exported == {
        "schema_version": 1,
        "export_kind": "setup_template",
        "template": TEMPLATE,
        "managed_copy": False,
    }
    assert saved["installation_id"] not in str(exported) and saved["updated_by"] not in str(
        exported
    )
    changed = configure(
        auth_client,
        h,
        saved,
        {"schema_version": 1, "defaults": {"languages": ["es"], "timezone": "Europe/Madrid"}},
    )
    assert changed["installation_id"] == saved["installation_id"] and changed["revision"] == 2
    history = call(auth_client, h, "history").json()
    assert len(history["items"]) == 2 and history["items"][0]["snapshot"] == saved
    assert call(auth_client, h, "export", changed, acknowledge_copy_limits=1).status_code == 422


@pytest.mark.parametrize(
    "template",
    [
        {"schema_version": 2, "defaults": {"languages": ["en"], "timezone": "UTC"}},
        {"schema_version": True, "defaults": {"languages": ["en"], "timezone": "UTC"}},
        {"schema_version": 1, "defaults": {"languages": [], "timezone": "UTC"}},
        {"schema_version": 1, "defaults": {"languages": ["en", "en"], "timezone": "UTC"}},
        {"schema_version": 1, "defaults": {"languages": ["de"], "timezone": "UTC"}},
        {"schema_version": 1, "defaults": {"languages": ["en"], "timezone": "../private"}},
        {"schema_version": 1, "defaults": {"languages": ["en"], "timezone": "Unknown/Zone"}},
        {"schema_version": 1, "defaults": {"languages": ["en"], "timezone": "UTC\n"}},
        {**TEMPLATE, "installation_id": str(uuid4())},
        {**TEMPLATE, "credential": "synthetic-secret-not-config"},
        {**TEMPLATE, "features": {"providers.live": True}},
        {
            "schema_version": 1,
            "defaults": {**TEMPLATE["defaults"], "endpoint": "https://invalid.example"},
        },
    ],
)
def test_template_unknown_private_or_unsupported_fields_refuse_atomically(
    auth_client, auth_store, template
):
    h = admin_headers(auth_client, auth_store)
    r = current(auth_client, h)
    response = call(auth_client, h, "preview", r, template=template)
    assert response.status_code == 422 and "synthetic-secret" not in str(response.json())
    assert current(auth_client, h) == r


@pytest.mark.parametrize("change", ["payload", "token", "expired", "foreign", "confirm"])
def test_preview_is_bound_to_current_payload_identity_session_and_expiry(
    auth_client, auth_store, change, monkeypatch
):
    h = admin_headers(auth_client, auth_store)
    r = current(auth_client, h)
    p = preview(auth_client, h, r)
    extra = {}
    if change == "payload":
        extra = {
            "template": {"schema_version": 1, "defaults": {"languages": ["es"], "timezone": "UTC"}}
        }
    if change == "token":
        extra = {"preview_token": "0" * 64}
    if change == "expired":
        from datetime import datetime

        expires = datetime.fromisoformat(p["expires_at"])
        monkeypatch.setattr(identity, "now_utc", lambda: expires + timedelta(seconds=1))
    if change == "foreign":
        p = deepcopy(p)
        p["record"]["installation_id"] = str(uuid4())
    if change == "confirm":
        extra = {"confirm": 1}
    assert apply_preview(auth_client, h, p, **extra).status_code == (
        422 if change == "confirm" else 409
    )
    with auth_store() as db:
        assert db.get(InstallationConfig, 1).revision == 0


def test_other_admin_session_cannot_reuse_preview_and_revocation_denies(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    p = preview(auth_client, h, current(auth_client, h))
    other = signin(auth_client)
    assert apply_preview(auth_client, other, p).status_code == 409
    with auth_store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "technical_admin", False)
    assert call(auth_client, other, "read").status_code == 403


def test_non_admin_csrf_origin_and_session_boundaries(auth_client, auth_store):
    h = signin(auth_client)
    assert call(auth_client, h, "read").status_code == 403
    h = admin_headers(auth_client, auth_store)
    r = current(auth_client, h)
    assert call(auth_client, {"X-CSRF-Token": "invalid"}, "read").status_code == 403
    assert call(auth_client, {**h, "Origin": "https://invalid.example"}, "read").status_code == 403
    auth_client.cookies.clear()
    assert call(auth_client, h, "export", r, acknowledge_copy_limits=True).status_code == 401


def test_audit_failure_rolls_back_identity_creation_and_keeps_values_out_of_audit(
    auth_client, auth_store
):
    h = admin_headers(auth_client, auth_store)
    p = preview(auth_client, h, current(auth_client, h))

    def fail(mapper, conn, target):
        if target.event_type == "installation.applied":
            raise SQLAlchemyError("Synthetic config audit failure")

    event.listen(AuditEvent, "before_insert", fail)
    try:
        assert apply_preview(auth_client, h, p).status_code == 503
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    with auth_store() as db:
        assert (
            db.get(InstallationConfig, 1).installation_id is None
            and list(db.scalars(select(InstallationRevision))) == []
        )
    saved = configure(auth_client, h, current(auth_client, h))
    with auth_store() as db:
        logs = list(
            db.scalars(select(AuditEvent).where(AuditEvent.event_type.like("installation.%")))
        )
        assert all(
            "timezone" not in str(log.metadata_json)
            and "preview_token" not in str(log.metadata_json)
            for log in logs
        )
    assert saved["revision"] == 1


def test_history_limit_keeps_read_export_and_noop_available(auth_client, auth_store):
    h = admin_headers(auth_client, auth_store)
    r = current(auth_client, h)
    for i in range(100):
        template = {
            "schema_version": 1,
            "defaults": {"languages": ["en" if i % 2 else "fr"], "timezone": "UTC"},
        }
        r = configure(auth_client, h, r, template)
    assert r["revision"] == 100
    assert apply_preview(auth_client, h, preview(auth_client, h, r)).status_code == 429
    assert (
        apply_preview(auth_client, h, preview(auth_client, h, r, r["configuration"])).json()[
            "changed"
        ]
        is False
    )
    assert call(auth_client, h, "export", r, acknowledge_copy_limits=True).status_code == 200
    history = call(auth_client, h, "history").json()
    assert len(history["items"]) == 5 and history["next_cursor"] == 5


def test_catalogue_is_honest_has_no_paths_probes_or_activation_and_rejects_graph_errors(
    monkeypatch,
):
    from pathlib import Path

    monkeypatch.setattr(
        installation_catalog.settings, "document_archive_directory", Path("/synthetic/private-root")
    )
    catalogue = installation_catalog.catalogue(False)
    assert all(
        not item["live_verified"] and item["activation_control"] == "not_provided"
        for item in catalogue
    )
    assert (
        next(x for x in catalogue if x["key"] == "documents.archive")["readiness"]
        == "configured_unverified"
    )
    assert "/synthetic/private-root" not in str(catalogue)
    for graph in (
        [("one", ("missing",))],
        [("one", ("two",)), ("two", ("one",))],
        [("one", ()), ("one", ())],
    ):
        with pytest.raises(ValueError):
            installation_catalog.validate_graph(graph)
