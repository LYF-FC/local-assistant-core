from sqlalchemy import select
from test_approvals import signin

from app.manage import set_scope
from app.models import User


def values(**changes):
    return {
        "schema_version": 1,
        "topic": "general",
        "basis": "unknown",
        "title": "Synthetic goal",
        "statement": "Synthetic intent, no forecast",
        "as_of": "2026-11-10",
        "target_date": None,
        "source_reference": "Synthetic manual source",
        "source_date": None,
        "amount": None,
        "currency": None,
        **changes,
    }


def headers(client, store):
    with store.begin() as db:
        set_scope(db, db.scalar(select(User).where(User.slug == "alice")), "finance_private", True)
    return signin(client)


def create(client, h, kind="goal", **changes):
    return client.post(
        "/api/v1/finance",
        headers=h,
        json={"scope": "finance_private", "kind": kind, "values": values(**changes)},
    )


def call(client, h, row, op, **changes):
    body = {"scope": "finance_private", **changes}
    if op in {"correct", "accept", "forget"}:
        body["expected_revision"] = row["revision"]
    return client.post(f"/api/v1/finance/{row['id']}/{op}", headers=h, json=body)


def test_lifecycle_acceptance_reset_and_forgetting(auth_client, auth_store):
    h = headers(auth_client, auth_store)
    r = create(auth_client, h, "plan")
    assert r.status_code == 201, r.json()
    row = r.json()
    accepted = call(auth_client, h, row, "accept", acknowledge_record_only=True)
    assert accepted.status_code == 200, accepted.json()
    accepted = accepted.json()
    assert accepted["plan_status"] == "accepted" and accepted["accepted_by"] == row["owner_id"]
    corrected = call(
        auth_client, h, accepted, "correct", values=values(title="Synthetic changed plan")
    ).json()
    assert corrected["plan_status"] == "proposed" and corrected["accepted_by"] is None
    assert call(auth_client, h, row, "correct", values=values()).status_code == 409
    forgotten = call(auth_client, h, corrected, "forget").json()
    assert forgotten["state"] == "forgotten" and "values" not in forgotten
    assert call(auth_client, h, forgotten, "forget").status_code == 200
    history = call(auth_client, h, forgotten, "history").json()
    assert len(history["items"]) == 4 and all(r["snapshot"] is None for r in history["items"])


def test_amount_unknown_zero_and_validation(auth_client, auth_store):
    h = headers(auth_client, auth_store)
    for change in [
        {"amount": 1.2, "currency": "EUR"},
        {"amount": "01.00", "currency": "EUR"},
        {"amount": "1.234", "currency": "EUR"},
        {"amount": "-1", "currency": "EUR"},
        {"amount": "1", "currency": None},
        {"as_of": "2026-02-30"},
        {"as_of": "1899-01-01"},
        {"schema_version": True},
        {"basis": "guaranteed"},
        {"title": " "},
    ]:
        assert create(auth_client, h, **change).status_code == 422, change
    row = create(auth_client, h, amount="0", currency="EUR", basis="forecast").json()
    assert row["values"]["amount"] == "0.00" and row["values"]["basis"] == "forecast"
    assert create(auth_client, h).json()["values"]["amount"] is None
    assert call(auth_client, h, row, "accept", acknowledge_record_only=True).status_code == 409


def test_owner_and_scope_export_denials(auth_client, auth_store):
    h = headers(auth_client, auth_store)
    row = create(auth_client, h).json()
    auth_client.post("/api/v1/auth/logout", headers=h, json={})
    other = signin(auth_client, "bob")
    for op in ["read", "history", "correct", "forget", "accept"]:
        extra = (
            {"values": values()}
            if op == "correct"
            else {"acknowledge_record_only": True}
            if op == "accept"
            else {}
        )
        assert call(auth_client, other, row, op, **extra).status_code == 404
    listed = auth_client.post(
        "/api/v1/finance/query", headers=other, json={"scope": "finance_private"}
    )
    assert listed.status_code == 200 and listed.json()["items"] == []
    assert (
        auth_client.post(
            "/api/v1/finance/export",
            headers=other,
            json={"scope": "finance_private", "acknowledge_copy_limits": 1},
        ).status_code
        == 422
    )


def test_quota_noop_confirmation_and_metadata_audit(auth_client, auth_store):
    from app.models import AuditEvent

    h = headers(auth_client, auth_store)
    row = create(auth_client, h, "plan").json()
    assert call(auth_client, h, row, "accept", acknowledge_record_only=1).status_code == 422
    assert call(auth_client, h, row, "correct", values=values()).status_code == 409
    assert (
        auth_client.post(
            "/api/v1/finance", json={"scope": "finance_private", "kind": "goal", "values": values()}
        ).status_code
        == 403
    )
    for _ in range(99):
        assert create(auth_client, h).status_code == 201
    assert create(auth_client, h).status_code == 429
    accepted = call(auth_client, h, row, "accept", acknowledge_record_only=True).json()
    assert call(auth_client, h, accepted, "accept", acknowledge_record_only=True).json() == accepted
    with auth_store() as db:
        assert all(
            "Synthetic goal" not in str(a.metadata_json)
            for a in db.scalars(select(AuditEvent).where(AuditEvent.event_type.like("finance.%")))
        )


def test_financial_history_limit_and_explicit_exports(auth_client, auth_store):
    h = headers(auth_client, auth_store)
    row = create(auth_client, h).json()
    for i in range(99):
        row = call(
            auth_client, h, row, "correct", values=values(title=f"Synthetic revision {i}")
        ).json()
    assert row["revision"] == 100
    assert (
        call(auth_client, h, row, "correct", values=values(title="Beyond limit")).status_code == 429
    )
    exported = call(
        auth_client,
        h,
        row,
        "export",
        expected_revision=row["revision"],
        acknowledge_copy_limits=True,
    )
    assert exported.status_code == 200 and exported.json()["record"] == row
    md = auth_client.post(
        "/api/v1/finance/export",
        headers=h,
        json={"scope": "finance_private", "acknowledge_copy_limits": True, "format": "markdown"},
    )
    assert (
        md.status_code == 200
        and md.headers["content-type"].startswith("text/markdown")
        and "```json" in md.text
    )
    forgotten = call(auth_client, h, row, "forget").json()
    assert forgotten["revision"] == 101
    assert all(
        r["snapshot"] is None for r in call(auth_client, h, forgotten, "history").json()["items"]
    )
