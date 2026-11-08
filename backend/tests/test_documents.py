import base64
import hashlib
import json
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin

from app import documents
from app.manage import set_scope
from app.models import AuditEvent, DocumentRecord, DocumentVersion, User

ORIGINAL = b"\xef\xbb\xbfSynthetic source\r\n100%_literal\r\n<script>source only</script>\n"


def upload(client, headers, **changes):
    return client.post(
        "/api/v1/documents",
        headers={**headers, "Content-Type": "application/json"},
        content=json.dumps(
            {
                "scope": "household_shared",
                "title": "Synthetic document",
                "filename": "source.md",
                "source_reference": "Synthetic manual source",
                "original_base64": base64.b64encode(ORIGINAL).decode(),
                **changes,
            }
        ),
    )


def call(client, headers, row, operation, **changes):
    body = {"scope": row["scope"]}
    if operation in {"correct", "replace", "forget", "original", "excerpt"}:
        body["expected_revision"] = row["revision"]
    if operation == "correct":
        body.update(
            title="Synthetic document", source_reference="Synthetic manual source", reviewed=True
        )
    if operation == "original":
        body["acknowledge_copy_limits"] = True
    body.update(changes)
    return client.post(f"/api/v1/documents/{row['id']}/{operation}", headers=headers, json=body)


def query(client, headers, **changes):
    return client.post(
        "/api/v1/documents/query", headers=headers, json={"scope": "household_shared", **changes}
    )


def lifecycle(client, h):
    response = upload(client, h)
    assert response.status_code == 201, response.text
    row = response.json()
    assert not row["reviewed"] and row["content_text"] == ORIGINAL.decode()
    assert row["sha256"] == hashlib.sha256(ORIGINAL).hexdigest()
    assert query(client, h).json()["items"] == []
    assert len(query(client, h, reviewed_only=False).json()["items"]) == 1
    assert call(client, h, row, "excerpt", end_line=2).status_code == 409
    row = call(client, h, row, "correct").json()
    assert row["reviewed"] and row["revision"] == 2
    assert len(query(client, h, search="100%_literal").json()["items"]) == 1
    assert query(client, h, search="100__literal").json()["items"] == []
    cited = call(client, h, row, "excerpt", start_line=2, end_line=2)
    assert cited.status_code == 200 and cited.json()["excerpt"] == "100%_literal\r"
    assert cited.json()["sha256"] == row["sha256"]
    for start, end in [(0, 1), (3, 2), (1, 51), (1, 5)]:
        assert call(client, h, row, "excerpt", start_line=start, end_line=end).status_code == 422
    data = call(client, h, row, "original").json()
    assert base64.b64decode(data["original_base64"]) == ORIGINAL
    assert not data["managed_copy"] and data["download_filename"].endswith("-v2.txt")
    replaced = call(
        client,
        h,
        row,
        "replace",
        filename="new.txt",
        original_base64=base64.b64encode(b"Synthetic replacement").decode(),
    ).json()
    assert replaced["revision"] == 3 and not replaced["reviewed"]
    assert call(client, h, row, "original").status_code == 409
    assert call(client, h, row, "correct").status_code == 409
    old = call(client, h, replaced, "original", version=1).json()
    assert base64.b64decode(old["original_base64"]) == ORIGINAL
    history = call(client, h, replaced, "history").json()
    assert [r["operation"] for r in history["items"]] == ["uploaded", "corrected", "replaced"]
    assert history["items"][0]["snapshot"]["sha256"] == row["sha256"]
    exported = client.post(
        "/api/v1/documents/export",
        headers=h,
        json={"scope": row["scope"], "reviewed_only": False, "acknowledge_copy_limits": True},
    )
    assert exported.status_code == 200 and exported.json()["actor_id"] == row["owner_id"]
    assert "content_text" not in exported.json()["items"][0]
    tomb = call(client, h, replaced, "forget").json()
    assert tomb["state"] == "forgotten" and "sha256" not in tomb
    assert call(client, h, tomb, "original").status_code == 410
    assert call(client, h, tomb, "correct").status_code == 410
    assert call(client, h, tomb, "forget").status_code == 410
    assert all(x["snapshot"] is None for x in call(client, h, tomb, "history").json()["items"])
    return tomb


def test_complete_lifecycle(auth_client, auth_store):
    tomb = lifecycle(auth_client, signin(auth_client))
    with auth_store() as db:
        versions = list(
            db.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == UUID(tomb["id"]))
            )
        )
        assert len(versions) == 4 and all(
            x.snapshot is None and x.original_bytes is None for x in versions
        )
        audit = list(db.scalars(select(AuditEvent).where(AuditEvent.entity_id == tomb["id"])))
        assert audit and all(
            "Synthetic" not in str(x.metadata_json) + str(x.after_json) + str(x.before_json)
            for x in audit
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"filename": "../x.txt"},
        {"filename": "x\\z.md"},
        {"filename": "x.pdf"},
        {"filename": "x\n.txt"},
        {"original_base64": "!!!!"},
        {"original_base64": "/w=="},
        {"original_base64": "AA=="},
        {"original_base64": ""},
        {"original_base64": "YQ==="},
        {"original_base64": base64.b64encode(b"a" * 32001).decode()},
        {"original_base64": base64.b64encode(b"a" * 131073).decode()},
        {"title": " "},
        {"source_reference": "bad\nref"},
        {"scope": "technical_admin"},
        {"scope": "finance_private"},
        {"reviewed": True},
        {"filename": "x\x7f.txt"},
        {"filename": "x\ud800.txt"},
        {"title": "bad\ud800"},
    ],
)
def test_invalid_upload_is_rejected(auth_client, changes):
    assert upload(auth_client, signin(auth_client), **changes).status_code == 422


def test_shared_read_and_private_owner_and_revocation(auth_client, auth_store):
    h = signin(auth_client)
    shared = upload(auth_client, h).json()
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        alice = db.scalar(select(User).where(User.slug == "alice"))
        set_scope(db, bob, "household_shared", True)
        set_scope(db, alice, "member_b_private", True)
    h = signin(auth_client, "bob")
    private = upload(auth_client, h, scope="member_b_private").json()
    assert not call(auth_client, h, shared, "read").json()["can_edit"]
    assert call(auth_client, h, shared, "original").status_code == 200
    for op in ["correct", "forget", "history"]:
        assert call(auth_client, h, shared, op).status_code == 403
    h = signin(auth_client)
    assert call(auth_client, h, private, "read").status_code == 404
    shared2 = call(auth_client, h, shared, "correct").json()
    h = signin(auth_client, "bob")
    assert call(auth_client, h, shared2, "original", version=1).status_code == 403
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, bob, "household_shared", False)
    assert call(auth_client, h, shared2, "original").status_code == 403


def test_transport_csrf_and_export_ack(auth_client):
    h = signin(auth_client)
    assert upload(auth_client, {}).status_code == 403
    assert upload(auth_client, {**h, "Origin": "https://evil.invalid"}).status_code == 403
    assert upload(auth_client, h).headers["cache-control"] == "no-store"
    for ack in [False, 1, "true", None]:
        assert (
            auth_client.post(
                "/api/v1/documents/export",
                headers=h,
                json={"scope": "household_shared", "acknowledge_copy_limits": ack},
            ).status_code
            == 422
        )
    auth_client.cookies.clear()
    assert query(auth_client, h).status_code == 401


def test_quotas_and_forget_at_limit(auth_client, monkeypatch):
    h = signin(auth_client)
    monkeypatch.setattr(documents, "MAX_ACTIVE", 1)
    monkeypatch.setattr(documents, "MAX_RECORDS", 2)
    row = upload(auth_client, h).json()
    assert upload(auth_client, h).status_code == 409
    monkeypatch.setattr(documents, "MAX_RETAINED_BYTES", len(ORIGINAL) * 2)
    assert call(auth_client, h, row, "correct").status_code == 409
    monkeypatch.setattr(documents, "MAX_VERSIONS", 1)
    assert call(auth_client, h, row, "correct").status_code == 409
    assert call(auth_client, h, row, "forget").status_code == 200
    assert upload(auth_client, h).status_code == 201
    monkeypatch.setattr(documents, "MAX_ACTIVE", 10)
    assert upload(auth_client, h).status_code == 409


def test_pagination_and_history_pages(auth_client, monkeypatch):
    h = signin(auth_client)
    ids = {upload(auth_client, h).json()["id"] for _ in range(26)}
    first = query(auth_client, h, reviewed_only=False).json()
    second = query(auth_client, h, reviewed_only=False, after=first["next_cursor"]).json()
    assert len(first["items"]) == 25 and len(second["items"]) == 1
    assert {x["id"] for x in first["items"] + second["items"]} == ids
    row = call(auth_client, h, first["items"][0], "read").json()
    for i in range(25):
        row = call(auth_client, h, row, "correct", title=f"Synthetic correction {i}").json()
    a = call(auth_client, h, row, "history").json()
    b = call(auth_client, h, row, "history", after=a["next_cursor"]).json()
    assert a["next_cursor"] == 25 and b["items"][0]["revision"] == 26


def test_audit_failure_rolls_back_bytes_and_record(auth_client, auth_store):
    h = signin(auth_client)

    def stop(mapper, connection, target):
        raise SQLAlchemyError("Synthetic audit outage")

    event.listen(AuditEvent, "before_insert", stop)
    try:
        response = upload(auth_client, h)
        assert response.status_code == 503
    finally:
        event.remove(AuditEvent, "before_insert", stop)
    with auth_store() as db:
        assert db.scalar(select(DocumentRecord.id)) is None
        assert db.scalar(select(DocumentVersion.id)) is None
