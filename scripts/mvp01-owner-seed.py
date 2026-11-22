#!/usr/bin/env python3
"""Seed the synthetic MVP-01 agenda through the real HTTPS API (spec 076); idempotent.

Standard library only. Trusts exactly the exported public development CA (never disables TLS
verification). Passwords come from the environment only and are never printed. Creates, once:
a synthetic manual task and a synthetic calendar snapshot for the fixture day for the owner, and
a peer-private task so that cross-user privacy can be observed. The invoice is never seeded:
the owner imports the supplied .eml personally.
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

DAY, ZONE = "2026-11-24", "Europe/Zurich"
TASK = "MVP-01 synthetic: pay-check invoice MVP01-2026-001"
EVENT_UID, CALENDAR = "mvp01-rehearsal-event-1", "MVP-01 synthetic calendar (manual snapshot)"
PEER_TASK = "MVP-01 synthetic: PEER-PRIVATE-MARKER peer-only task"


class Session:
    def __init__(self, origin, ca):
        self.origin = origin
        context = ssl.create_default_context(cafile=ca)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(CookieJar()),
        )
        self.csrf = None

    def call(self, path, body):
        request = urllib.request.Request(
            self.origin + path,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Origin": self.origin, **({"X-CSRF-Token": self.csrf} if self.csrf else {})},
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            return error.code, {}

    def get(self, path):
        request = urllib.request.Request(self.origin + path, headers={"Origin": self.origin})
        try:
            with self.opener.open(request, timeout=20) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            return error.code, {}

    def login(self, slug, password):
        status, data = self.call("/api/v1/auth/login", {"slug": slug, "password": password})
        if status != 200:
            raise SystemExit(f"Sign-in for {slug} was refused ({status})")
        self.csrf = data["csrf_token"]


def ensure_task(session, scope, title, due, details):
    status, data = session.call("/api/v1/tasks/query", {"scope": scope, "status": "all", "due": "all", "search": "MVP-01 synthetic"})
    if status != 200:
        raise SystemExit(f"Task query refused ({status})")
    if any(item["title"] == title for item in data["items"]):
        return "kept"
    status, _ = session.call("/api/v1/tasks", {"scope": scope, "title": title, "details": details, "due_at": due, "assignment": "me"})
    if status != 201:
        raise SystemExit(f"Task creation refused ({status})")
    return "created"


def ensure_calendar(session):
    status, data = session.call("/api/v1/calendars/query", {"scope": "household_shared"})
    if status != 200:
        raise SystemExit(f"Calendar query refused ({status})")
    if any(item.get("label") == CALENDAR for item in data["items"]):
        return "kept"
    status, source = session.call("/api/v1/calendars", {"scope": "household_shared", "label": CALENDAR})
    if status != 201:
        raise SystemExit(f"Calendar creation refused ({status})")
    window = {
        "complete": True,
        "cursor": "mvp01-rehearsal-snapshot-1",
        "fetched_at": "2026-11-22T08:00:00+00:00",
        "timezone": ZONE,
        "start_date": "2026-11-23",
        "end_date": "2026-11-26",
        "events": [{
            "kind": "timed", "uid": EVENT_UID, "recurrence_id": "", "sequence": 0,
            "title": "MVP-01 synthetic: family planning call", "description": "Synthetic rehearsal event.",
            "status": "confirmed", "timezone": ZONE,
            "start": "2026-11-24T10:00:00+01:00", "end": "2026-11-24T11:00:00+01:00",
        }],
    }
    status, _ = session.call(f"/api/v1/calendars/{source['id']}/import", {"scope": "household_shared", "expected_revision": source["revision"], "window": window})
    if status != 200:
        raise SystemExit(f"Calendar snapshot import refused ({status})")
    return "created"


def main():
    origin, ca = sys.argv[1], sys.argv[2]
    owner = Session(origin, ca)
    owner.login("mvp01-owner", os.environ["BUTLER_MVP01_OWNER_PASSWORD"])
    print("task", ensure_task(owner, "household_shared", TASK, f"{DAY}T17:00:00+01:00", "Synthetic rehearsal task due on the fixture day."))
    print("calendar", ensure_calendar(owner))
    peer_password = os.environ.get("BUTLER_MVP01_PEER_PASSWORD")
    if peer_password:
        peer = Session(origin, ca)
        peer.login("mvp01-peer", peer_password)
        print("peer-task", ensure_task(peer, "member_b_private", PEER_TASK, f"{DAY}T12:00:00+01:00", "Peer-private synthetic record."))


if __name__ == "__main__":
    main()
