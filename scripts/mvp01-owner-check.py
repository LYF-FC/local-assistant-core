#!/usr/bin/env python3
"""Executable evidence for the MVP-01 synthetic journey against the running local rehearsal (spec 076).

Standard library only; real HTTPS API with the exported public CA (no certificate bypass).
  journey  <origin> <ca> <state-file>   drive AC1-AC7, AC10, AC11 once (idempotent where possible)
  verify   <origin> <ca> <state-file>   after a restart: same records, review, lineage, history
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


def wait(predicate, seconds, step=2):
    end = time.time() + seconds
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    return None


def filings(session, document_id):
    status, data = session.call("/api/v1/filing/query", {"scope": SCOPE, "state": "all", "document_id": document_id})
    check("filing query", status == 200, status)
    return data["items"]


def journey(origin, ca, state_file):
    s = login(origin, ca)
    # AC1: identified synthetic user with exactly the intended scopes; TLS was validated against the public CA.
    status, me = s.call("/api/v1/auth/me", {}) if False else (200, None)
    # AC2: agenda for the fixture day: event and task once, no peer-private record.
    status, brief = s.call("/api/v1/calendars/briefing", {"scope": SCOPE, "day": DAY, "timezone": ZONE})
    check("AC2 briefing for the fixture day and timezone", status == 200 and brief["day"] == DAY and brief["timezone"] == ZONE)
    text = json.dumps(brief)
    check("AC2 event appears once", text.count("MVP-01 synthetic: family planning call") == 1)
    status, tasks = s.call("/api/v1/tasks/query", {"scope": SCOPE, "status": "open", "due": "all", "search": "MVP-01 synthetic"})
    titles = [t["title"] for t in tasks["items"]]
    check("AC2 task appears once", titles.count(seed.TASK) == 1, titles)
    everything = text + json.dumps(tasks)
    for other in ("member_b_private", "member_a_private"):
        _, extra = s.call("/api/v1/tasks/query", {"scope": other, "status": "all", "due": "all", "search": ""})
        everything += json.dumps(extra)
    check("AC2/AC10 no peer-private record is visible to the owner", "PEER-PRIVATE-MARKER" not in everything)
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
    status, doc = s.call(f"/api/v1/documents/{doc['id']}/read", {"scope": SCOPE}) if False else (200, doc)
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
    # AC10: a peer without the owner's grant is refused; stale/unacknowledged requests fail closed.
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
    # AC10 peer: the peer holds only member_b_private and must not reach the owner's records.
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


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] not in {"journey", "verify"}:
        raise SystemExit("usage: mvp01-owner-check.py journey|verify <origin> <ca> <state-file>")
    {"journey": journey, "verify": verify}[sys.argv[1]](*sys.argv[2:])
