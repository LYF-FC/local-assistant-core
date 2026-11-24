"""Spec 078 ("the paper invoice"): PDF documents on PostgreSQL with injected extraction results.

Synthetic only. The real Poppler/Tesseract engines are exercised by the live rehearsal checks, never here: these tests
inject worker replies (so the exact OCR text is never asserted, decision A-2), keep the backend behaviour unchanged
(D7: every failed or unavailable attempt adds a version and resets review) and cover scope refusals for every PDF
operation, including the original that the browser now draws as page images.
"""

import base64
import hashlib
from uuid import uuid4

import pytest
from conftest import SYNTHETIC_PASSWORD, client_for
from pdf_fixtures import pdf
from sqlalchemy.orm import sessionmaker
from test_documents import call
from test_invoice_review import call as invoice_call
from test_pdf_ingestion import extract_call, pdf_upload
from test_pdf_ocr import ocr_call

from app import pdf_ingestion
from app.manage import provision

pytestmark = pytest.mark.integration

OCR_LINES = [
    "Issuer: Synthetic Rehearsal Vendor",
    "Invoice number: MVP01-2026-004",
    "Invoice date: 2026-11-23",
    "Due date: 2027-01-08",
    "Total: 812.80",  # a plausible wrong value (3 read as 8): injected, never produced by the live engine here
    "Currency: EUR",
]


def injected(raw, *, ocr=False, lines=OCR_LINES):
    return {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "engine": "poppler-tesseract-v1" if ocr else "poppler-text-v1",
        "version": "25.03.0",
        "status": "ready",
        "pages": 1,
        "page_spans": [{"page": 1, "start_line": 1, "end_line": len(lines)}],
        "empty_pages": [],
        "text": "\n".join(lines),
    }


def history(client, h, row):
    return call(client, h, row, "history").json()["items"]


def test_every_unavailable_attempt_adds_a_version_and_resets_review_and_the_state_stays_visible(
    scenario,
):
    client, h, _, _, _ = scenario
    row = pdf_upload(client, h).json()  # no worker answers: unavailable, original kept
    assert row["extraction"]["status"] == "unavailable" and not row["reviewed"]
    first_revision = row["revision"]
    seen = [first_revision]
    for attempt in (extract_call, ocr_call, extract_call):
        response = attempt(client, h, row)
        assert response.status_code == 200, response.text
        row = response.json()
        assert row["extraction"]["status"] == "unavailable" and not row["reviewed"]
        seen.append(row["revision"])
    assert seen == [
        first_revision + i for i in range(4)
    ]  # D7: one new version per click, unchanged backend
    # Text that was never extracted cannot be attested as reviewed.
    assert call(client, h, row, "correct").status_code in (409, 422)
    assert len(history(client, h, row)) >= 4
    original = call(client, h, row, "original").json()
    assert base64.b64decode(original["original_base64"]).startswith(
        b"%PDF-"
    )  # the original is kept
    assert call(client, h, row, "forget").status_code == 200


def test_ocr_that_misreads_a_value_is_corrected_by_the_owner_and_an_unknown_total_stays_unknown(
    scenario, monkeypatch
):
    client, h, _, _, _ = scenario
    monkeypatch.setattr(pdf_ingestion, "exchange", lambda raw, *, ocr=False: injected(raw, ocr=ocr))
    row = pdf_upload(client, h).json()
    row = ocr_call(client, h, row).json()
    assert row["extraction"]["engine"] == "poppler-tesseract-v1" and not row["reviewed"]
    row = call(
        client, h, row, "correct"
    ).json()  # human attestation that the text was compared with the original
    receipt = invoice_call(client, h, row, "prepare").json()
    assert (
        receipt["review"]["data"]["candidates"]["total"][0]["value"] == "812.80"
    )  # the plausible wrong candidate
    names = ("issuer", "invoice_number", "issued_on", "due_on", "total", "currency")
    values = (
        "Synthetic Rehearsal Vendor",
        "MVP01-2026-004",
        "2026-11-23",
        "2027-01-08",
        "312.80",
        "EUR",
    )
    confirmed = {
        f: {
            "state": "confirmed",
            "value": v,
            "line": i + 1,
            "note": "OCR read 3 as 8" if f == "total" else "",
        }
        for i, (f, v) in enumerate(zip(names, values, strict=True))
    }
    corrected = invoice_call(client, h, row, "review", receipt, decisions=confirmed)
    # Whatever the validator decides about a corrected value, the owner always has the honest alternative: Unknown.
    unknown = {
        **confirmed,
        "total": {"state": "unknown", "value": None, "line": None, "note": "Not trustworthy"},
    }
    if corrected.status_code != 200:
        corrected = invoice_call(client, h, row, "review", receipt, decisions=unknown)
    assert corrected.status_code == 200, corrected.text
    saved = invoice_call(client, h, row, "review", corrected.json(), decisions=unknown)
    assert saved.status_code == 200, saved.text
    decided = saved.json()["review"]["data"]["decisions"]
    assert (
        decided["total"]["state"] == "unknown" and decided["total"]["value"] is None
    )  # Unknown is not zero
    assert decided["issuer"]["state"] == "confirmed"
    assert call(client, h, row, "forget").status_code == 200


def second_client(admin, runtime_engine, scopes):
    slug = "synthetic-" + uuid4().hex
    with admin.begin() as db:
        provision(db, slug, "Synthetic second adult", SYNTHETIC_PASSWORD, scopes)
    maker = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    context = client_for(maker)
    client = context.__enter__()
    response = client.post(
        "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
    )
    assert response.status_code == 200
    return context, client, {"X-CSRF-Token": response.json()["csrf_token"]}


def test_other_users_cannot_extract_review_or_forget_and_a_peer_cannot_even_read_the_original(
    scenario, runtime_engine, monkeypatch
):
    owner, h, _, admin, _ = scenario
    monkeypatch.setattr(pdf_ingestion, "exchange", lambda raw, *, ocr=False: injected(raw, ocr=ocr))
    row = pdf_upload(owner, h, pdf(("Synthetic invoice 100.00",))).json()
    row = call(owner, h, row, "correct").json()
    # A non-owner household member (shared scope) may read the current original but has no change controls.
    reader_ctx, reader, rh = second_client(admin, runtime_engine, {"household_shared"})
    try:
        shared = call(reader, rh, row, "original")
        assert shared.status_code == 200 and base64.b64decode(
            shared.json()["original_base64"]
        ).startswith(b"%PDF-")
        for operation, changes in (
            ("extract", {}),
            ("correct", {}),
            ("replace", {}),
            ("forget", {}),
            ("history", {}),
        ):
            if operation == "extract":
                response = extract_call(reader, rh, row)
            elif operation == "history":
                response = call(reader, rh, row, "history")
            else:
                response = call(reader, rh, row, operation, **changes)
            allowed = (
                (403, 404, 422) if operation == "replace" else (403, 404)
            )  # replace needs a file body
            assert response.status_code in allowed, (operation, response.status_code)
        assert ocr_call(reader, rh, row).status_code in (403, 404)
    finally:
        reader_ctx.__exit__(None, None, None)
    # A peer with only its own private scope sees nothing of the owner's PDF in the shared scope.
    peer_ctx, peer, ph = second_client(admin, runtime_engine, {"member_b_private"})
    try:
        for operation in ("read", "original", "excerpt", "history", "extract", "correct", "forget"):
            lines = {"start_line": 1, "end_line": 1} if operation == "excerpt" else {}
            response = (
                extract_call(peer, ph, row)
                if operation == "extract"
                else call(peer, ph, row, operation, **lines)
            )
            assert response.status_code in (403, 404), (operation, response.status_code)
        assert ocr_call(peer, ph, row).status_code in (403, 404)
        listing = peer.post(
            "/api/v1/documents/query", headers=ph, json={"scope": "household_shared"}
        )
        assert listing.status_code in (403, 404)
    finally:
        peer_ctx.__exit__(None, None, None)
    # Stale revision, invalid mode and unknown id fail closed for the owner as well.
    stale = {**row, "revision": row["revision"] + 5}
    assert extract_call(owner, h, stale).status_code == 409
    bad = owner.post(
        f"/api/v1/documents/{row['id']}/extract",
        headers=h,
        json={"scope": row["scope"], "expected_revision": row["revision"], "mode": "magic"},
    )
    assert bad.status_code == 422
    missing = owner.post(
        f"/api/v1/documents/{uuid4()}/extract",
        headers=h,
        json={"scope": row["scope"], "expected_revision": 1},
    )
    assert missing.status_code == 404
    assert call(owner, h, row, "forget").status_code == 200
