from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from test_approvals import signin
from test_documents import call as document_call
from test_invoice_review import call, confirm, decisions, prepare, source

from app import invoice_filing
from app.manage import set_scope
from app.models import AuditEvent, InvoiceReview, User


def plan_call(client, h, doc, op, receipt, **extra):
    return call(
        client,
        h,
        doc,
        op,
        expected_document_revision=doc["revision"],
        expected_review_revision=receipt["review_revision"],
        **extra,
    )


def approved(client, h, doc, receipt):
    p = plan_call(client, h, doc, "plan", receipt)
    assert p.status_code == 200, p.json()
    r = plan_call(
        client,
        h,
        doc,
        "approve_plan",
        p.json(),
        acknowledge_plan_only=True,
        acknowledge_duplicate_limits=True,
    )
    assert r.status_code == 200, r.json()
    return r.json()


@pytest.mark.parametrize(
    "folder,name",
    [
        ("/invoices/2026", "a.txt"),
        ("invoices/../x", "a.txt"),
        ("invoices/x", "../a.txt"),
        ("invoices/x", "a\\b.txt"),
        ("invoices/x", "a/b.txt"),
        ("invoices/x", "a%2ftxt.txt"),
        ("invoices/x", "con.txt"),
        ("invoices/nul", "a.txt"),
        ("invoices/x", "com9.extra.txt"),
        ("invoices/x", "a..txt"),
        ("invoices/x", "a.txt."),
        ("invoices/x", "A.txt"),
        ("invoices/x", "é.txt"),
        ("invoices/x", "a.pdf"),
        ("invoices/x", ".a.txt"),
        ("invoices/x", "a\n.txt"),
        ("invoices/x", "a" * 157 + ".txt"),
        ("invoices/" + "a" * 65, "a.txt"),
        ("invoices/a/b/c", "a.txt"),
        ("invoices//x", "a.txt"),
        ("invoices/x ", "a.txt"),
        ("invoices", "a.txt"),
        ("https://invoices/x", "a.txt"),
        ("C:/invoices/x", "a.txt"),
    ],
)
def test_logical_path_rejection(folder, name):
    with pytest.raises(ValueError):
        invoice_filing.validate(folder, name, "txt")


def test_multilingual_slug_and_unique_original_template():
    src = SimpleNamespace(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        revision=2,
        sha256="a" * 64,
        filename="INVOICE.PDF",
    )
    r = SimpleNamespace(
        revision=2,
        data={
            "decisions": {
                k: {"state": "confirmed", "value": v}
                for k, v in {
                    "issuer": "Société Española",
                    "invoice_number": "N° / 42",
                    "issued_on": "2026-11-01",
                }.items()
            }
        },
    )
    plan = invoice_filing.propose(src, r)
    assert (
        plan["relative_path"]
        == f"invoices/2026/societe-espanola/2026-11-01_societe-espanola_n-42_{src.id}.pdf"
    )
    assert plan["execution_authorized"] is False and plan["approved_revision"] is None
    assert invoice_filing.slug("a" * 100, 48) == "a" * 48
    with pytest.raises(ValueError):
        invoice_filing.slug("東京", 48)


def test_plan_approval_withdraw_correction_history_and_aggregate_forget(auth_client):
    h = signin(auth_client)
    doc = source(auth_client, h)
    r = confirm(auth_client, h, doc)
    r = approved(auth_client, h, doc, r)
    p = r["review"]["data"]["filing_plan"]
    assert p["state"] == "approved" and p["execution_authorized"] is False
    assert p["based_on_review_revision"] == 2 and p["approved_revision"] == 4
    assert (
        plan_call(
            auth_client,
            h,
            doc,
            "approve_plan",
            r,
            acknowledge_plan_only=True,
            acknowledge_duplicate_limits=True,
        ).status_code
        == 409
    )
    r = plan_call(auth_client, h, doc, "withdraw_plan", r).json()
    assert r["review"]["data"]["filing_plan"]["state"] == "withdrawn"
    r = plan_call(
        auth_client, h, doc, "plan", r, folder="invoices/manual", filename="synthetic.txt"
    ).json()
    assert r["review"]["data"]["filing_plan"]["manual"]
    assert (
        plan_call(auth_client, h, doc, "withdraw_plan", {**r, "review_revision": 2}).status_code
        == 409
    )
    history = call(auth_client, h, doc, "export", acknowledge_copy_limits=True).json()
    assert history["items"][3]["snapshot"]["data"]["filing_plan"]["state"] == "approved"
    assert document_call(auth_client, h, doc, "forget").status_code == 200
    assert call(auth_client, h, doc, "read").json()["review"] is None


@pytest.mark.parametrize("op", ["review", "prepare"])
def test_field_decision_or_candidate_reset_invalidates_plan(auth_client, op):
    h = signin(auth_client)
    doc = source(auth_client, h)
    r = approved(auth_client, h, doc, confirm(auth_client, h, doc))
    r = call(auth_client, h, doc, op, r).json()
    assert not r["review"]["data"].get("filing_plan")


def test_unknown_fields_manual_alternative_and_explicit_acknowledgement(auth_client):
    h = signin(auth_client)
    doc = source(auth_client, h)
    p = prepare(auth_client, h, doc)
    r = call(
        auth_client, h, doc, "review", p, decisions=decisions(issued_on={"state": "unknown"})
    ).json()
    assert plan_call(auth_client, h, doc, "plan", r).status_code == 422
    assert plan_call(auth_client, h, doc, "plan", r, folder="invoices/manual").status_code == 422
    r = plan_call(
        auth_client, h, doc, "plan", r, folder="invoices/manual", filename="undated.txt"
    ).json()
    for extra in (
        {},
        {"acknowledge_plan_only": 1, "acknowledge_duplicate_limits": True},
        {"acknowledge_plan_only": True, "acknowledge_duplicate_limits": False},
    ):
        assert plan_call(auth_client, h, doc, "approve_plan", r, **extra).status_code == 422
    assert (
        plan_call(
            auth_client,
            h,
            doc,
            "approve_plan",
            r,
            acknowledge_plan_only=True,
            acknowledge_duplicate_limits=True,
        ).status_code
        == 200
    )


def test_shared_reads_but_owner_only_changes_and_source_drift(auth_client, auth_store):
    h = signin(auth_client)
    doc = source(auth_client, h)
    r = approved(auth_client, h, doc, confirm(auth_client, h, doc))
    with auth_store.begin() as db:
        bob = db.scalar(select(User).where(User.slug == "bob"))
        set_scope(db, bob, "household_shared", True)
    other = signin(auth_client, "bob")
    assert (
        call(auth_client, other, doc, "read").json()["review"]["data"]["filing_plan"]["state"]
        == "approved"
    )
    for op, extra in (
        ("plan", {}),
        ("approve_plan", {"acknowledge_plan_only": True, "acknowledge_duplicate_limits": True}),
        ("withdraw_plan", {}),
    ):
        assert plan_call(auth_client, other, doc, op, r, **extra).status_code == 403
    h = signin(auth_client)
    changed = document_call(auth_client, h, doc, "correct", title="Synthetic revised source").json()
    assert call(auth_client, h, changed, "read").json()["review"] is None
    assert plan_call(auth_client, h, changed, "withdraw_plan", r).status_code == 409


def test_metadata_only_audit_and_rollback(auth_client, auth_store):
    h = signin(auth_client)
    doc = source(auth_client, h)
    r = confirm(auth_client, h, doc)

    def fail(*args):
        raise SQLAlchemyError("Synthetic failure")

    event.listen(AuditEvent, "before_insert", fail)
    try:
        assert plan_call(auth_client, h, doc, "plan", r).status_code == 503
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    with auth_store() as db:
        assert db.get(InvoiceReview, UUID(doc["id"])).revision == 2
    r = approved(auth_client, h, doc, r)
    with auth_store() as db:
        events = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.event_type.in_(["invoices.plan", "invoices.approve_plan"])
                )
            )
        )
        assert len(events) == 2 and all("invoices/" not in str(e.metadata_json) for e in events)
    r = call(auth_client, h, doc, "forget", r).json()
    assert r["status"] == "forgotten"
    assert all(x["snapshot"] is None for x in call(auth_client, h, doc, "history").json()["items"])


def test_plan_private_admin_revocation_and_request_boundaries(auth_client, auth_store):
    h = signin(auth_client)
    with auth_store.begin() as db:
        for slug in ("alice", "bob"):
            user = db.scalar(select(User).where(User.slug == slug))
            set_scope(db, user, "member_b_private", True)
            if slug == "bob":
                set_scope(db, user, "technical_admin", True)
    doc = source(auth_client, h, scope="member_b_private")
    r = approved(auth_client, h, doc, confirm(auth_client, h, doc))
    assert plan_call(auth_client, {"X-CSRF-Token": "invalid"}, doc, "plan", r).status_code == 403
    assert (
        auth_client.post(
            f"/api/v1/invoices/{doc['id']}/plan",
            headers={**h, "Origin": "https://invalid.example"},
            json={
                "scope": doc["scope"],
                "expected_document_revision": doc["revision"],
                "expected_review_revision": r["review_revision"],
            },
        ).status_code
        == 403
    )
    bh = signin(auth_client, "bob")
    for op in ("plan", "approve_plan", "withdraw_plan"):
        extra = (
            {"acknowledge_plan_only": True, "acknowledge_duplicate_limits": True}
            if op == "approve_plan"
            else {}
        )
        assert plan_call(auth_client, bh, doc, op, r, **extra).status_code == 404
    h = signin(auth_client)
    with auth_store.begin() as db:
        user = db.scalar(select(User).where(User.slug == "alice"))
        set_scope(db, user, "member_b_private", False)
    assert plan_call(auth_client, h, doc, "withdraw_plan", r).status_code == 403
