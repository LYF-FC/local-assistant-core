#!/usr/bin/env python3
"""Executable evidence for the MVP-01 synthetic journey against the running local rehearsal (spec 076).

Standard library only; real HTTPS API with the exported public CA (no certificate bypass).
  journey  <origin> <ca> <state-file>   drive AC1-AC7, AC10 (owner-side refusals), AC11 once (idempotent where possible)
  verify   <origin> <ca> <state-file>   after a restart: same records, review, lineage, history
  outage-journey / outage-end / peer    spec 077: bad-connection day (outage already ON / after OFF / live peer negatives)
The synthetic owner password comes from BUTLER_MVP01_OWNER_PASSWORD only; nothing secret is printed.
"""

import base64
import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("seed", HERE / "mvp01-owner-seed.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)
SCOPE, DAY, ZONE = "household_shared", seed.DAY, seed.ZONE
EML = HERE / "mvp01-owner-fixtures" / "invoice.eml"
results = []
QUESTION = "What is the total amount?"


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(("PASS " if condition else "FAIL ") + name + (f"  [{detail}]" if detail and not condition else ""))
    if not condition:
        raise SystemExit(f"Check failed: {name}")


def login(origin, ca):
    session = seed.Session(origin, ca)
    session.login("mvp01-owner", os.environ["BUTLER_MVP01_OWNER_PASSWORD"])
    return session


def wait(predicate, seconds, step=2, note=None):
    end = time.time() + seconds
    last = time.time()
    while time.time() < end:
        value = predicate()
        if value:
            return value
        if note and time.time() - last >= 60:
            print(note, file=sys.stderr, flush=True)
            last = time.time()
        time.sleep(step)
    return None


def filings(session, document_id):
    status, data = session.call("/api/v1/filing/query", {"scope": SCOPE, "state": "all", "document_id": document_id})
    check("filing query", status == 200, status)
    return data["items"]


def journey(origin, ca, state_file):
    s = login(origin, ca)
    # AC1: identified synthetic user with exactly the intended scopes; TLS was validated against the public CA.
    status, me = s.get("/api/v1/auth/me")
    check("AC1 signed in as the synthetic owner with exactly the intended scopes", status == 200 and me.get("display_name", "").startswith("Synthetic MVP-01") and sorted(me.get("scopes", [])) == ["household_shared", "member_a_private"], me)
    # AC2: agenda for the fixture day: event and task once, no peer-private record.
    status, brief = s.call("/api/v1/calendars/briefing", {"scope": SCOPE, "day": DAY, "timezone": ZONE})
    check("AC2 briefing for the fixture day and timezone", status == 200 and brief["day"] == DAY and brief["timezone"] == ZONE)
    text = json.dumps(brief)
    check("AC2 event appears once", text.count("MVP-01 synthetic: family planning call") == 1)
    status, tasks = s.call("/api/v1/tasks/query", {"scope": SCOPE, "status": "open", "due": "all", "search": "MVP-01 synthetic"})
    titles = [t["title"] for t in tasks["items"]]
    check("AC2 task appears once", titles.count(seed.TASK) == 1, titles)
    everything = text + json.dumps(tasks)
    status_a, own_private = s.call("/api/v1/tasks/query", {"scope": "member_a_private", "status": "all", "due": "all", "search": ""})
    check("AC2 the owner's own private scope is readable", status_a == 200 and own_private.get("items") is not None, status_a)
    status_b, _ = s.call("/api/v1/tasks/query", {"scope": "member_b_private", "status": "all", "due": "all", "search": ""})
    check("AC2/AC10 the peer's private scope is explicitly denied (403), not merely empty", status_b == 403, status_b)
    everything += json.dumps(own_private)
    check("AC2 no peer-private record is visible to the owner", "PEER-PRIVATE-MARKER" not in everything)
    print("NOTE AC10 peer isolation by a signed-in peer, revoked grants/sessions and concurrent requests are evidenced by backend/tests/integration/test_mvp01_journey_postgres.py (and the leakage suite), not by this driver: the peer password is random and never retained.")
    # AC3: the exact same email twice: one document, visible replay, original title preserved.
    raw = EML.read_bytes()
    body = {"scope": SCOPE, "title": "MVP-01 rehearsal invoice", "message_base64": base64.b64encode(raw).decode()}
    first = s.call("/api/v1/email-intake", body)
    second = s.call("/api/v1/email-intake", {**body, "title": "A replay must not rename"})
    doc = second[1]["document"]
    check("AC3 import then replay", first[0] in (200, 201) and second[0] == 200 and second[1]["status"] == "replayed")
    check("AC3 one document and original title preserved", first[1]["document"]["id"] == doc["id"] and doc["title"] == "MVP-01 rehearsal invoice")
    status, lineage = s.call(f"/api/v1/email-intake/{doc['id']}/read", {"scope": SCOPE, "expected_document_revision": doc["revision"]})
    check("AC3 email original lineage inspectable", status == 200 and lineage["message_sha256"] == hashlib.sha256(raw).hexdigest())
    # AC4: source review then an authorized cited question; simulated model labelled by the stack.
    if not doc.get("reviewed"):
        status, doc = s.call(f"/api/v1/documents/{doc['id']}/correct", {"scope": SCOPE, "expected_revision": doc["revision"], "title": doc["title"], "source_reference": doc["source_reference"], "reviewed": True})
        check("AC4 source reviewed", status == 200, status)
    status, answer = s.call("/api/v1/document-answers", {"scope": SCOPE, "question": QUESTION})
    cited = answer.get("passages") or [{}]
    check(
        "AC4 cited exact quotation with document/revision/hash/line",
        status == 200 and answer.get("status") == "answered" and len(cited) == 1 and cited[0].get("text") == "Total: 123.45"
        and cited[0]["document"]["id"] == doc["id"] and cited[0]["document"]["sha256"] == doc["sha256"]
        and cited[0]["document"]["revision"] == doc["revision"] and cited[0]["start_line"] == cited[0]["end_line"] == 5,
        json.dumps(answer)[:300],
    )
    # AC11: explicit unavailable answer; agenda and manual records stay useful.
    status, down = s.call("/api/v1/document-answers", {"scope": SCOPE, "question": "synthetic-unavailable what is the total?"})
    check("AC11 model unavailable is explicit and no answer is invented", status == 200 and down.get("status") == "unavailable" and "123.45" not in json.dumps(down.get("passages", [])), json.dumps(down)[:300])
    # AC5: in-app reminder scheduled by the owner and delivered by the restricted worker.
    task = next(t for t in tasks["items"] if t["title"] == seed.TASK)
    status, prefs = s.call("/api/v1/reminders/preferences/read", {"scope": SCOPE})
    check("AC5 reminder preferences readable", status == 200, status)
    if not prefs.get("enabled"):
        status, saved = s.call("/api/v1/reminders/preferences/save", {"scope": SCOPE, "expected_revision": prefs.get("revision", 0), "enabled": True, "timezone": ZONE, "quiet_start": 0, "quiet_end": 0, "daily_limit": 5})
        check("AC5 owner enables in-app reminders (opt-in)", status == 200, json.dumps(saved)[:300])
    status, queried = s.call("/api/v1/reminders/query", {"scope": SCOPE, "state": "all"})
    existing = [r for r in queried.get("items", []) if r["reminder"]["task_id"] == task["id"]]
    if not existing:
        when = (datetime.fromisoformat(brief["checked_at"]) + timedelta(seconds=75)).isoformat()  # server clock
        status, scheduled = s.call("/api/v1/reminders/schedule", {"scope": SCOPE, "task_id": task["id"], "expected_task_revision": task["revision"], "scheduled_at": when})
        check("AC5 reminder scheduled (pending)", status in (200, 201), json.dumps(scheduled)[:300])
    def delivered():
        _, q = s.call("/api/v1/reminders/query", {"scope": SCOPE, "state": "all"})
        return [r["reminder"] for r in q["items"] if r["reminder"]["task_id"] == task["id"] and r["reminder"]["state"] in ("delivered", "acknowledged")]
    got = wait(delivered, 200, 5)
    check("AC5 worker delivered the reminder once", got and len(got) == 1, got)
    reminder = got[0]
    if reminder["state"] == "delivered":
        status, _ = s.call("/api/v1/reminders/action", {"scope": SCOPE, "task_id": task["id"], "expected_revision": reminder["revision"], "action": "acknowledge"})
        check("AC5 acknowledged", status == 200, status)
    _, after = s.call("/api/v1/tasks/query", {"scope": SCOPE, "status": "open", "due": "all", "search": "MVP-01 synthetic"})
    check("AC5 acknowledgement does not complete the task", seed.TASK in [t["title"] for t in after["items"]])
    # AC6: candidates, intentional unknown, contained plan; plan approval alone causes no effect.
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/prepare", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": None})
    check("AC6 candidates prepared", status == 200, status)
    values = {"issuer": "Synthetic Rehearsal Vendor", "invoice_number": "MVP01-2026-001", "issued_on": "2026-11-20", "total": "123.45", "currency": "EUR"}
    lines = {"issuer": 1, "invoice_number": 2, "issued_on": 3, "total": 5, "currency": 6}
    decisions = {f: {"state": "confirmed", "value": v, "line": lines[f], "note": ""} for f, v in values.items()}
    decisions["due_on"] = {"state": "unknown", "value": None, "line": None, "note": "Left unknown on purpose"}
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/review", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"], "attest_original": True, "decisions": decisions})
    check("AC6 review saved with an intentional unknown", status == 200 and receipt["status"] == "reviewed", status)
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/plan", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"]})
    check("AC6 logical plan proposed", status == 200, status)
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/approve_plan", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"], "acknowledge_plan_only": True, "acknowledge_duplicate_limits": True})
    plan = receipt["review"]["data"]["filing_plan"]
    check("AC6 plan approved but execution not authorized", status == 200 and plan["state"] == "approved" and plan["execution_authorized"] is False and plan["relative_path"].startswith("invoices/"))
    check("AC6 plan approval alone caused no filing", filings(s, doc["id"]) == [])
    # AC10 (owner-side only): unacknowledged and stale requests fail closed and start nothing.
    bad = {"scope": SCOPE, "document_id": doc["id"], "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"]}
    check("AC10 missing acknowledgements are refused", s.call("/api/v1/filing/request", {**bad, "acknowledge_synthetic_destination": True})[0] == 422)
    check("AC10 stale source revision is refused", s.call("/api/v1/filing/request", {**bad, "expected_document_revision": doc["revision"] + 1, "acknowledge_synthetic_destination": True, "acknowledge_exact_plan": True})[0] == 409)
    check("AC10 nothing was started by refusals", filings(s, doc["id"]) == [])
    # AC7: separate exact authorization; replay; worker files once; auditable history.
    request = {**bad, "acknowledge_synthetic_destination": True, "acknowledge_exact_plan": True}
    status, created = s.call("/api/v1/filing/request", request)
    check("AC7 one exact request", status == 201 and created["filing"]["state"] == "pending", status)
    status, again = s.call("/api/v1/filing/request", request)
    check("AC7 repeated request is a replay, not a second request", status == 200 and again["replayed"] and again["filing"]["id"] == created["filing"]["id"])
    done = wait(lambda: next((f for f in filings(s, doc["id"]) if f["state"] in ("filed", "failed", "unknown")), None), 90, 3)
    check("AC7 worker filed the exact request", done and done["state"] == "filed" and done["attempts"] == 1, done)
    status, hist = s.call("/api/v1/filing/history", {"scope": SCOPE, "execution_id": done["id"]})
    ops = [e["operation"] for e in hist["items"]]
    check("AC7 history shows request, attempt, filed", ops == ["requested", "attempted", "filed"], ops)
    # Persist identifiers for the post-restart verify phase.
    state = {"document_id": doc["id"], "document_revision": doc["revision"], "title": doc["title"], "review_revision": receipt["review_revision"], "filing_id": done["id"], "filing_revision": done["revision"], "path": plan["relative_path"], "reminder_task": task["id"]}
    Path(state_file).write_text(json.dumps(state, indent=1))
    print(f"journey complete; state written ({len(results)} checks passed)")


def verify(origin, ca, state_file):
    state = json.loads(Path(state_file).read_text())
    s = login(origin, ca)
    status, docs = s.call("/api/v1/documents/query", {"scope": SCOPE})
    ours = [d for d in docs.get("items", []) if d["id"] == state["document_id"]]
    check("AC8 same document with preserved title after restart", status == 200 and len(ours) == 1 and ours[0]["title"] == state["title"] and ours[0]["revision"] == state["document_revision"], status)
    status, receipt = s.call(f"/api/v1/invoices/{state['document_id']}/read", {"scope": SCOPE})
    check("AC8 same invoice review and approved plan", status == 200 and receipt["review_revision"] == state["review_revision"] and receipt["review"]["data"]["filing_plan"]["relative_path"] == state["path"])
    items = filings(s, state["document_id"])
    check("AC8 exactly one filing, still terminal", len(items) == 1 and items[0]["id"] == state["filing_id"] and items[0]["state"] == "filed" and items[0]["revision"] == state["filing_revision"], items)
    status, hist = s.call("/api/v1/filing/history", {"scope": SCOPE, "execution_id": state["filing_id"]})
    check("AC8 history preserved", [e["operation"] for e in hist["items"]] == ["requested", "attempted", "filed"])
    status, q = s.call("/api/v1/reminders/query", {"scope": SCOPE, "state": "all"})
    mine = [r["reminder"] for r in q["items"] if r["reminder"]["task_id"] == state["reminder_task"]]
    check("AC8 reminder not redelivered or duplicated", len(mine) == 1 and mine[0]["state"] == "acknowledged", mine)
    status, brief = s.call("/api/v1/calendars/briefing", {"scope": SCOPE, "day": DAY, "timezone": ZONE})
    check("AC8 agenda unchanged", json.dumps(brief).count("MVP-01 synthetic: family planning call") == 1)
    print("verify complete")


EML2 = HERE / "mvp01-owner-fixtures" / "invoice-002.eml"
TITLE2 = "MVP-01 outage-day invoice"
SECOND_STATE_KEYS = ("document_id", "document_title", "filing_id", "path", "calendar_id")


def outage_journey(origin, ca, state_file):
    """Spec 077: run with `outage on` already applied by the caller. One owner sign-in."""
    s = login(origin, ca)
    status, me = s.get("/api/v1/auth/me")
    check("AC1 signed in as the synthetic owner", status == 200 and sorted(me.get("scopes", [])) == ["household_shared", "member_a_private"], me)
    # C1: the calendar source is marked offline by the owner's existing control; the overview must not claim a free day.
    status, listing = s.call("/api/v1/calendars/query", {"scope": SCOPE})
    source = next(i for i in listing["items"] if i.get("label") == seed.CALENDAR)
    if source.get("status") != "offline":
        status, _ = s.call(f"/api/v1/calendars/{source['id']}/unavailable", {"scope": SCOPE, "expected_revision": source["revision"], "reason": "offline"})
        check("C1 the calendar source is marked offline (existing control)", status == 200, status)
    status, brief = s.call("/api/v1/calendars/briefing", {"scope": SCOPE, "day": DAY, "timezone": ZONE})
    blob = json.dumps(brief).lower()
    check("C1 overview keeps the last-known event and says offline", status == 200 and "family planning call" in blob and "offline" in blob, blob[:300])
    events = brief.get("events", []) if isinstance(brief, dict) else []
    check("C1 overview structurally marks every event of the offline source as offline", bool(events) and all(e.get("availability") == "offline" for e in events), [e.get("availability") for e in events])
    check("C1 overview makes no free-day claim", "free day" not in blob.replace("not establish a free day", "").replace("does not mean a free day", ""))
    # C2 (tasks) first; the question needs a reviewed source, so it follows the review below.
    status, tasks = s.call("/api/v1/tasks/query", {"scope": SCOPE, "status": "open", "due": "all", "search": "MVP-01 synthetic"})
    check("C2 manual tasks still work during the outage", status == 200 and seed.TASK in [t["title"] for t in tasks["items"]])
    # C3: invoice 2 twice, review, plan approval alone starts nothing, then the exact request.
    raw = EML2.read_bytes()
    body = {"scope": SCOPE, "title": TITLE2, "message_base64": base64.b64encode(raw).decode()}
    first = s.call("/api/v1/email-intake", body)
    second = s.call("/api/v1/email-intake", {**body, "title": "A replay must not rename"})
    doc = second[1]["document"]
    check("C3 invoice 2 imported once and replayed", first[0] in (200, 201) and second[0] == 200 and second[1]["status"] == "replayed" and doc["title"] == TITLE2)
    if not doc.get("reviewed"):
        status, doc = s.call(f"/api/v1/documents/{doc['id']}/correct", {"scope": SCOPE, "expected_revision": doc["revision"], "title": doc["title"], "source_reference": doc["source_reference"], "reviewed": True})
        check("C3 source reviewed (works during the outage)", status == 200, status)
    # C2: with the reviewed source present and the model stopped, the answer is an explicit unavailable.
    status, answer = s.call("/api/v1/document-answers", {"scope": SCOPE, "question": QUESTION})
    check("C2 stopped answer service gives an explicit 'unavailable', not an error or a made-up answer", status == 200 and answer.get("status") == "unavailable" and not answer.get("passages"), json.dumps(answer)[:200])
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/prepare", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": None})
    check("C3 candidates prepared", status == 200, status)
    values = {"issuer": "Synthetic Rehearsal Vendor", "invoice_number": "MVP01-2026-002", "issued_on": "2026-11-21", "total": "245.60", "currency": "EUR"}
    lines = {"issuer": 1, "invoice_number": 2, "issued_on": 3, "total": 5, "currency": 6}
    decisions = {f: {"state": "confirmed", "value": v, "line": lines[f], "note": ""} for f, v in values.items()}
    decisions["due_on"] = {"state": "unknown", "value": None, "line": None, "note": "Left unknown on purpose"}
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/review", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"], "attest_original": True, "decisions": decisions})
    check("C3 review saved", status == 200 and receipt["status"] == "reviewed", status)
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/plan", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"]})
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/approve_plan", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"], "acknowledge_plan_only": True, "acknowledge_duplicate_limits": True})
    plan = receipt["review"]["data"]["filing_plan"]
    check("C3 plan approved; approval alone started nothing", status == 200 and plan["execution_authorized"] is False and filings(s, doc["id"]) == [])
    request = {"scope": SCOPE, "document_id": doc["id"], "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"], "acknowledge_synthetic_destination": True, "acknowledge_exact_plan": True}
    status, created = s.call("/api/v1/filing/request", request)
    check("C3 exact request recorded", status in (200, 201), status)
    filing_id = created["filing"]["id"]
    # C4: waiting, never failed, never filed; listed where the Attention inbox reads it.
    waiting = wait(lambda: next((f for f in filings(s, doc["id"]) if f["state"] == "unknown"), None), 120, 3)
    check("C4 the filing waits as 'unknown' (not failed, not filed)", waiting and waiting["id"] == filing_id and waiting["state"] == "unknown" and waiting["reason"] == "ambiguous_outcome", waiting)
    status, inbox = s.call("/api/v1/filing/query", {"scope": SCOPE, "state": "unknown", "document_id": None, "after": None})
    check("C4 the Attention inbox source lists it with its document link target", status == 200 and any(i["id"] == filing_id and i["document_id"] == doc["id"] for i in inbox["items"]))
    status, hist = s.call("/api/v1/filing/history", {"scope": SCOPE, "execution_id": filing_id})
    ops = [e["operation"] for e in hist["items"]]
    check("C4 history shows request and attempt only, then the unknown outcome", ops[:2] == ["requested", "attempted"] and "filed" not in ops and "failed" not in ops, ops)
    Path(state_file).write_text(json.dumps({"document_id": doc["id"], "document_title": TITLE2, "filing_id": filing_id, "path": plan["relative_path"], "calendar_id": source["id"]}, indent=1))
    print("outage-journey complete; run the restart and `outage off`, then outage-end")


OUTAGE_END_WAIT_SECONDS = 17 * 60  # worst case: one 15-minute back-off after the outage ends, plus a worker pass


def outage_end(origin, ca, state_file, effects_before=None, effects_after=None):
    """After `outage off`: one owner sign-in. Ledger counts come from `status` (before the outage ended, after filing)."""
    state = json.loads(Path(state_file).read_text())
    s = login(origin, ca)
    done = wait(lambda: next((f for f in filings(s, state["document_id"]) if f["state"] in ("filed", "failed")), None), OUTAGE_END_WAIT_SECONDS, 3, "still waiting: while the destination was unreachable it was asked only about every 15 minutes (spec 069 back-off)")
    check("C6 the waiting filing resolves to Filed", done and done["id"] == state["filing_id"] and done["state"] == "filed", done)
    items = filings(s, state["document_id"])
    check("C6 still exactly one request for invoice 2", len(items) == 1)
    status, hist = s.call("/api/v1/filing/history", {"scope": SCOPE, "execution_id": state["filing_id"]})
    ops = [e["operation"] for e in hist["items"]]
    check("C6 history is complete and ends Filed", ops[0] == "requested" and ops[-1] == "filed", ops)
    if effects_before is not None and effects_after is not None:
        check("C6 the ledger gained exactly one effect", int(effects_after) == int(effects_before) + 1, (effects_before, effects_after))
    else:
        print("NOTE the ledger +1-effect check was not run: pass the `status` effects counts before and after as arguments")
    raw = EML2.read_bytes()
    third = s.call("/api/v1/email-intake", {"scope": SCOPE, "title": "Replay after filing", "message_base64": base64.b64encode(raw).decode()})
    check("C6 a further import of invoice 2 replays and starts nothing", third[0] == 200 and third[1]["status"] == "replayed" and len(filings(s, state["document_id"])) == 1)
    status, answer = s.call("/api/v1/document-answers", {"scope": SCOPE, "question": QUESTION})
    check("C6 answers work again once the assistant is back", status == 200 and answer.get("status") in ("answered", "insufficient", "conflicting"), answer.get("status"))
    print("outage-end complete")


def peer(origin, ca, state_file):
    """Live peer-side negatives (one peer sign-in). Needs BUTLER_MVP01_PEER_PASSWORD, set for this one command only."""
    state = json.loads(Path(state_file).read_text())
    p = seed.Session(origin, ca)
    p.login("mvp01-peer", os.environ["BUTLER_MVP01_PEER_PASSWORD"])
    status, me = p.get("/api/v1/auth/me")
    check("C7 the peer is a different user with only its own private scope", status == 200 and me.get("scopes") == ["member_b_private"], me)
    owner_ids = (state["document_id"], state["filing_id"], state["document_title"])
    every = ""
    for scope in ("household_shared", "member_a_private"):
        code, _ = p.call("/api/v1/filing/query", {"scope": scope, "state": "all", "document_id": state["document_id"]})
        check(f"C7 filing query in {scope} is refused", code in (403, 404), code)
        code, _ = p.call("/api/v1/filing/history", {"scope": scope, "execution_id": state["filing_id"]})
        check(f"C7 filing history in {scope} is refused", code in (403, 404), code)
        code, _ = p.call("/api/v1/filing/cancel", {"scope": scope, "execution_id": state["filing_id"], "expected_revision": 1})
        check(f"C7 filing cancel in {scope} is refused", code in (403, 404), code)
        code, _ = p.call("/api/v1/filing/request", {"scope": scope, "document_id": state["document_id"], "expected_document_revision": 1, "expected_review_revision": 1, "acknowledge_synthetic_destination": True, "acknowledge_exact_plan": True})
        check(f"C7 filing request in {scope} is refused", code in (403, 404), code)
        code, _ = p.call("/api/v1/documents/query", {"scope": scope})
        check(f"C7 document list in {scope} is refused", code in (403, 404), code)
    own = "member_b_private"
    for name, path, body in (
        ("filing unknown", "/api/v1/filing/query", {"scope": own, "state": "unknown", "document_id": None, "after": None}),
        ("filing failed", "/api/v1/filing/query", {"scope": own, "state": "failed", "document_id": None, "after": None}),
        ("filing all", "/api/v1/filing/query", {"scope": own, "state": "all", "document_id": None, "after": None}),
        ("documents", "/api/v1/documents/query", {"scope": own}),
        ("reminders", "/api/v1/reminders/query", {"scope": own, "state": "all"}),
        ("approvals", "/api/v1/approvals/query", {"scope": own}),
        ("briefing", "/api/v1/calendars/briefing", {"scope": own, "day": DAY, "timezone": ZONE}),
    ):
        code, data = p.call(path, body)
        every += json.dumps(data)
        check(f"C7 peer {name} read is allowed and shows nothing of the owner", code == 200 and not any(x in json.dumps(data) for x in owner_ids), code)
    code, own_tasks = p.call("/api/v1/tasks/query", {"scope": own, "status": "all", "due": "all", "search": ""})
    check("C7 positive control: the peer sees its own marker task", code == 200 and any("PEER-PRIVATE-MARKER" in t["title"] for t in own_tasks["items"]))
    check("C7 no owner title, id or filing id appears anywhere in the peer's responses", not any(x in every + json.dumps(own_tasks) for x in owner_ids))
    print("NOTE a non-owner EDITOR (same scope, different user) needs a third fixture user with household_shared; it is covered by the PostgreSQL tests only.")
    print("peer complete")



# ---------------------------------------------------------------- spec 078: the paper invoice
FIX = HERE / "mvp01-owner-fixtures"
PAPER = {"pdf": FIX / "invoice-pdf.eml", "scan": FIX / "invoice-scan.eml", "offline": FIX / "invoice-pdf-offline.eml"}
TITLES = {"pdf": "MVP-01 paper invoice (text PDF)", "scan": "MVP-01 paper invoice (scan)", "offline": "MVP-01 paper invoice (worker stopped)"}
# States, never OCR text (live OCR output varies by platform): the checker adapts to what the engine returned.


def import_mail(s, key):
    raw = PAPER[key].read_bytes()
    body = {"scope": SCOPE, "title": TITLES[key], "message_base64": base64.b64encode(raw).decode()}
    first = s.call("/api/v1/email-intake", body)
    second = s.call("/api/v1/email-intake", {**body, "title": "A replay must not rename"})
    check(f"P {key}: imported once, then replayed", first[0] in (200, 201) and second[0] == 200 and second[1]["status"] == "replayed", (first[0], second[0]))
    check(f"P {key}: one document and the original title kept", first[1]["document"]["id"] == second[1]["document"]["id"] and second[1]["document"]["title"] == TITLES[key])
    return second[1]["document"]


def read_doc(s, doc):
    status, current = s.call(f"/api/v1/documents/{doc['id']}/read", {"scope": SCOPE})
    check("document read", status == 200, status)
    return current


def extract(s, doc, mode):
    status, out = s.call(f"/api/v1/documents/{doc['id']}/extract", {"scope": SCOPE, "expected_revision": doc["revision"], "mode": mode})
    check(f"extract ({mode}) accepted", status == 200, status)
    return out


def line_of(text, needle):
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return number
    return None


def review_and_file(s, doc, label, expect_total_unknown):
    """Review (confirm only what the document text really shows, leave the rest Unknown), plan, request, wait Filed."""
    status, doc = s.call(f"/api/v1/documents/{doc['id']}/correct", {"scope": SCOPE, "expected_revision": doc["revision"], "title": doc["title"], "source_reference": doc["source_reference"], "reviewed": True})
    check(f"P {label}: text reviewed against the original (human attestation)", status == 200 and doc["reviewed"] is True, status)
    text = doc["content_text"]
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/prepare", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": None})
    check(f"P {label}: candidates prepared", status == 200, status)
    expected = {"issuer": "Synthetic Rehearsal Vendor", "issued_on": "2026-11-23", "currency": "EUR"}
    needles = {"issuer": "Synthetic Rehearsal Vendor", "issued_on": "2026-11-23", "currency": "EUR"}
    if not expect_total_unknown:
        expected.update({"invoice_number": "MVP01-2026-003", "total": "312.80", "due_on": "2027-01-08"})
        needles.update({"invoice_number": "MVP01-2026-003", "total": "312.80", "due_on": "2027-01-08"})
    decisions = {}
    for field in ("issuer", "invoice_number", "issued_on", "due_on", "total", "currency"):
        line = line_of(text, needles[field]) if field in needles else None
        if field in expected and line:
            decisions[field] = {"state": "confirmed", "value": expected[field], "line": line, "note": ""}
        else:
            decisions[field] = {"state": "unknown", "value": None, "line": None, "note": "Left Unknown on purpose (not readable or not confirmed)"}
    if expect_total_unknown:
        check(f"P {label}: the Total stays Unknown (it was not read)", decisions["total"]["state"] == "unknown")
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/review", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"], "attest_original": True, "decisions": decisions})
    check(f"P {label}: review saved with Unknown fields kept Unknown", status == 200 and receipt["status"] == "reviewed", status)
    manual = decisions["invoice_number"]["state"] != "confirmed"
    plan_body = {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"]}
    if manual:
        plan_body.update({"folder": "invoices/manual", "filename": f"paper-{label}.pdf"})
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/plan", plan_body)
    check(f"P {label}: logical plan proposed", status == 200, status)
    status, receipt = s.call(f"/api/v1/invoices/{doc['id']}/approve_plan", {"scope": SCOPE, "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"], "acknowledge_plan_only": True, "acknowledge_duplicate_limits": True})
    plan = receipt["review"]["data"]["filing_plan"]
    check(f"P {label}: plan approved, execution not authorized", status == 200 and plan["state"] == "approved" and plan["execution_authorized"] is False, status)
    check(f"P {label}: plan approval alone started nothing", filings(s, doc["id"]) == [])
    request = {"scope": SCOPE, "document_id": doc["id"], "expected_document_revision": doc["revision"], "expected_review_revision": receipt["review_revision"], "acknowledge_synthetic_destination": True, "acknowledge_exact_plan": True}
    status, created = s.call("/api/v1/filing/request", request)
    check(f"P {label}: one exact request", status == 201 and created["filing"]["state"] == "pending", status)
    done = wait(lambda: next((f for f in filings(s, doc["id"]) if f["state"] in ("filed", "failed", "unknown")), None), 90, 3)
    check(f"P {label}: worker filed it once", done and done["state"] == "filed" and done["attempts"] == 1, done)
    return doc, done, plan


def paper_journey(origin, ca, state_file):
    """Spec 078 (agent run, API): P1 text PDF and P2 scan through extraction, OCR, review, plan and filing. One sign-in."""
    s = login(origin, ca)
    p1 = import_mail(s, "pdf")
    p1 = read_doc(s, p1)
    ex = p1["extraction"]
    check("P1 extraction ready with the text engine (1 page)", ex["status"] == "ready" and ex["engine"] == "poppler-text-v1" and ex["pages"] == 1, ex)
    p2 = import_mail(s, "scan")
    p2 = read_doc(s, p2)
    check("P2 an image-only PDF has no text yet (no_text)", p2["extraction"]["status"] == "no_text" and p2["content_text"] == "", p2["extraction"])
    ocr = extract(s, p2, "ocr")
    p2 = read_doc(s, p2)
    ex2 = p2["extraction"]
    check("P2 explicit OCR ran: ready with the OCR engine, review reset, new version", ex2["status"] == "ready" and ex2["engine"] == "poppler-tesseract-v1" and p2["reviewed"] is False and p2["revision"] > p1["revision"] - 1, (ex2["status"], ex2["engine"], p2["reviewed"]))
    p1, f1, plan1 = review_and_file(s, p1, "text", False)
    p2, f2, plan2 = review_and_file(s, p2, "scan", True)
    state = {"p1": {"document_id": p1["id"], "revision": p1["revision"], "title": p1["title"], "filing_id": f1["id"], "path": plan1["relative_path"]},
             "p2": {"document_id": p2["id"], "revision": p2["revision"], "title": p2["title"], "filing_id": f2["id"], "path": plan2["relative_path"]},
             "document_id": p1["id"], "filing_id": f1["id"], "document_title": p1["title"]}
    Path(state_file).write_text(json.dumps(state, indent=1))
    print(f"paper-journey complete; state written ({len(results)} checks passed)")


def paper_verify(origin, ca, state_file, effects_before=None, effects_after=None):
    """After restart / restart --kill: same documents, extraction states, reviews and exactly one Filed request each."""
    state = json.loads(Path(state_file).read_text())
    s = login(origin, ca)
    for key in ("p1", "p2"):
        item = state[key]
        status, doc = s.call(f"/api/v1/documents/{item['document_id']}/read", {"scope": SCOPE})
        check(f"P {key}: same document after restart, title kept", status == 200 and doc["title"] == item["title"] and doc["revision"] == item["revision"], status)
        check(f"P {key}: extraction still ready", doc["extraction"]["status"] == "ready")
        items = filings(s, item["document_id"])
        check(f"P {key}: exactly one filing, still Filed", len(items) == 1 and items[0]["id"] == item["filing_id"] and items[0]["state"] == "filed", items)
        status, hist = s.call("/api/v1/filing/history", {"scope": SCOPE, "execution_id": item["filing_id"]})
        check(f"P {key}: history preserved", [e["operation"] for e in hist["items"]] == ["requested", "attempted", "filed"])
    if effects_before is not None and effects_after is not None:
        check("P the ledger gained exactly two effects in total and none after the restart", int(effects_after) == int(effects_before), (effects_before, effects_after))
    print("paper-verify complete")


def paper_worker_down(origin, ca, state_file):
    """Run with `pdf-worker stop` applied: P3 keeps its original, reports unavailable, and each attempt adds a version."""
    s = login(origin, ca)
    p3 = import_mail(s, "offline")
    p3 = read_doc(s, p3)
    ex = p3["extraction"]
    check("P3 with the worker stopped: the import succeeds and extraction is unavailable", ex["status"] == "unavailable" and p3["reviewed"] is False, ex)
    raw = PAPER["offline"].read_bytes()
    status, got = s.call(f"/api/v1/documents/{p3['id']}/original", {"scope": SCOPE, "expected_revision": p3["revision"], "version": p3["revision"], "acknowledge_copy_limits": True})
    original = base64.b64decode(got["original_base64"]) if status == 200 else b""
    check("P3 the original is kept byte for byte", status == 200 and original[:5] == b"%PDF-" and got["sha256"] == hashlib.sha256(original).hexdigest(), status)
    status, refused = s.call(f"/api/v1/documents/{p3['id']}/correct", {"scope": SCOPE, "expected_revision": p3["revision"], "title": p3["title"], "source_reference": p3["source_reference"], "reviewed": True})
    check("P3 text that was never extracted cannot be attested as reviewed", status in (409, 422), status)
    revisions = [p3["revision"]]
    for _ in range(2):
        extract(s, {"id": p3["id"], "revision": revisions[-1]}, "text")
        current = read_doc(s, p3)
        revisions.append(current["revision"])
    check("P3 each attempt while the worker is down adds a version (backend behaviour, unchanged)", revisions[0] < revisions[1] < revisions[2], revisions)
    check("P3 the state stays visible as unavailable", current["extraction"]["status"] == "unavailable" and current["reviewed"] is False)
    Path(state_file).write_text(json.dumps({**json.loads(Path(state_file).read_text()), "p3": {"document_id": p3["id"], "revision": current["revision"]}}, indent=1))
    print("paper-worker-down complete")


def paper_repaired(origin, ca, state_file):
    """Run after `pdf-worker start`: Re-extract works, review is required again."""
    state = json.loads(Path(state_file).read_text())
    s = login(origin, ca)
    p3 = read_doc(s, {"id": state["p3"]["document_id"]})
    extract(s, p3, "text")
    p3 = read_doc(s, p3)
    check("P3 after repair Re-extract is ready and unreviewed (review required again)", p3["extraction"]["status"] == "ready" and p3["reviewed"] is False, p3["extraction"])
    print("paper-repaired complete")


def paper_hostile_import(origin, ca, state_file):
    """Agent only (one sign-in): import the hostile, the damaged and the oversized-page test PDFs as ordinary documents."""
    spec = importlib.util.spec_from_file_location("paper_fixtures", FIX / "paper_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    s = login(origin, ca)
    for kind, title in (("hostile", "MVP-01 hostile test PDF"), ("malformed", "MVP-01 malformed test PDF"), ("huge", "MVP-01 huge-page test PDF")):
        body = {"scope": SCOPE, "title": title, "message_base64": base64.b64encode(module.agent_eml(kind)).decode()}
        status, out = s.call("/api/v1/email-intake", body)
        check(f"{kind} test PDF imported as an ordinary document (extraction state is whatever the engine says)", status in (200, 201), status)
    print("paper-hostile-import complete")


def paper_peer(origin, ca, state_file):
    """The second synthetic adult sees nothing of the PDF documents, originals or extraction (one peer sign-in)."""
    state = json.loads(Path(state_file).read_text())
    p = seed.Session(origin, ca)
    p.login("mvp01-peer", os.environ["BUTLER_MVP01_PEER_PASSWORD"])
    ids = [state[k]["document_id"] for k in ("p1", "p2") if k in state] + ([state["p3"]["document_id"]] if "p3" in state else [])
    every = ""
    for scope in ("household_shared", "member_a_private"):
        code, _ = p.call("/api/v1/documents/query", {"scope": scope})
        check(f"PEER document list in {scope} is refused", code in (403, 404), code)
        for identifier in ids:
            for name, path, body in (
                ("read", "read", {"scope": scope}),
                ("original", "original", {"scope": scope, "expected_revision": 1, "version": 1, "acknowledge_copy_limits": True}),
                ("extract", "extract", {"scope": scope, "expected_revision": 1, "mode": "ocr"}),
            ):
                code, _ = p.call(f"/api/v1/documents/{identifier}/{path}", body)
                check(f"PEER {name} of a PDF document in {scope} is refused", code in (403, 404), code)
    for name, path, body in (
        ("documents", "/api/v1/documents/query", {"scope": "member_b_private"}),
        ("filing", "/api/v1/filing/query", {"scope": "member_b_private", "state": "all", "document_id": None, "after": None}),
    ):
        code, data = p.call(path, body)
        every += json.dumps(data)
        check(f"PEER {name} in its own scope shows nothing of the owner", code == 200 and not any(i in json.dumps(data) for i in ids))
    check("PEER no PDF title, filename or id appears anywhere", not any(x in every for x in ids + ["MVP-01 paper invoice", "invoice-MVP01-2026", "scan-MVP01-2026"]))
    print("paper-peer complete")


COMMANDS = {"journey": journey, "verify": verify, "outage-journey": outage_journey, "outage-end": outage_end, "peer": peer, "paper-journey": paper_journey, "paper-verify": paper_verify, "paper-worker-down": paper_worker_down, "paper-repaired": paper_repaired, "paper-peer": paper_peer, "paper-hostile-import": paper_hostile_import}

if __name__ == "__main__":
    if len(sys.argv) < 5 or sys.argv[1] not in COMMANDS:
        raise SystemExit("usage: mvp01-owner-check.py journey|verify|outage-journey|outage-end|peer|paper-journey|paper-verify|paper-worker-down|paper-repaired|paper-peer <origin> <ca> <state-file> [effects-before effects-after for outage-end]")
    COMMANDS[sys.argv[1]](*sys.argv[2:])
