"""Whole-MVP cross-user leakage harness (Gate 1). Test infrastructure only; synthetic data only.

Contract (it adds no permission rule): docs/MVP_ACCEPTANCE.md Gate 1 requires that another adult,
a revoked user and an administrator cannot retrieve private content through IDs, counts, search,
answers, citations, exports or history. The behavior each surface shows is the one its own
authority code and existing tests already define (401 for a missing, unknown or revoked session;
403 when the requested scope is not granted; 404 when the record is not visible in a granted
scope; owner-only operations refuse a non-owner). Expected visibility is computed here, from the
records this harness created and the documented owner/shared rules, never from the endpoint under
test.

Every surface is described once by an adapter. ``sweep`` then runs the same negative-actor
operations on every adapter, on SQLite and on the restricted PostgreSQL role (the two environments
are those of ``documents_isolation_support``). The sensitivity controls in
``test_mvp_leakage_controls.py`` prove that the assertions here catch a leaked body, count, cursor
and log line. These tests prove nothing about timing or side channels, and they observe only the
operations listed in the adapters.
"""

import base64
import contextlib
import json
import random
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from email import policy as email_policy
from email.message import EmailMessage
from uuid import UUID, uuid4

import documents_isolation_support as support
from conftest import SYNTHETIC_PASSWORD
from sqlalchemy import event, select
from test_document_answers import reviewed
from test_documents import upload
from test_invoice_review import call as invoice_call
from test_invoice_review import decisions as _invoice_decisions

from app import identity
from app.models import AuditEvent

SHARED, PRIVATE, OTHER_PRIVATE = support.SHARED, support.PRIVATE, support.OTHER_PRIVATE
FINANCE, ADMIN = "finance_private", support.ADMIN

# Actor kinds. "owner" created the records; the others are negative actors except where a shared
# reader is entitled to a shared record.
OWNER, PEER, READER = "owner", "peer", "reader"
ADMIN_SAME, ADMIN_ONLY, STRANGER, NO_GRANT = "admin_same", "admin_only", "stranger", "no_grant"
GRANT_REVOKED, SESSION_REVOKED, ANON = "grant_revoked", "session_revoked", "anonymous"
NEGATIVE = (
    PEER, READER, ADMIN_SAME, ADMIN_ONLY, STRANGER, NO_GRANT, GRANT_REVOKED, SESSION_REVOKED, ANON,
)  # fmt: skip
SAME_PRIVATE_GRANT = {PEER, ADMIN_SAME}  # hold the private scope, are not the creator
SCOPE_DENIED = {READER, ADMIN_ONLY, STRANGER, NO_GRANT, GRANT_REVOKED}
SESSION_DENIED = {SESSION_REVOKED, ANON}
SHARED_GRANTED = {OWNER, PEER, READER}  # actors whose shared-scope grant is live in a sweep


def invoice_decisions(number):
    return _invoice_decisions(
        invoice_number={"state": "confirmed", "value": number, "line": 2, "note": ""}
    )


def mark(label):
    return label + uuid4().hex[:12]


@dataclass
class Caller:
    """What a request is made with: a client and its headers (retained cookie for a revoked session)."""

    client: object
    headers: dict
    kind: str

    def get(self, path, **kwargs):
        return self.client.get(path, headers=self.headers, **kwargs)

    def post(self, path, body=None, **kwargs):
        return self.client.post(path, headers=self.headers, json=body, **kwargs)

    def put(self, path, body=None):
        return self.client.put(path, headers=self.headers, json=body)

    def patch(self, path, body=None):
        return self.client.patch(path, headers=self.headers, json=body)


@dataclass
class World:
    env: object
    callers: dict
    actors: dict
    owner: object
    log: list = field(default_factory=list)  # every record this harness created, for cleanup
    shared_records: list = field(default_factory=list)
    hits: set = field(default_factory=set)  # (actor kind, METHOD, normalised path) of every request


UUID_SEGMENT = re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def normalise(path):
    return UUID_SEGMENT.sub("/{identifier}", path.split("?")[0])


def record_requests(client, hits, kind):
    """Record every request an actor client makes, so a classification of a route as swept can be
    checked against the routes this suite really called."""
    original = client.request

    def recording(method, url, *args, **kwargs):
        hits.add((kind, method.upper(), normalise(str(url))))
        return original(method, url, *args, **kwargs)

    client.request = recording


def build_world(env):
    """Provision every actor kind through privileged provisioning; requests use the env clients."""
    full = {SHARED, PRIVATE, FINANCE}
    actors = {
        OWNER: env.actor("owner", full),
        PEER: env.actor("peer", full),
        READER: env.actor("reader", {SHARED}),
        ADMIN_SAME: env.actor("admin-same", {ADMIN, PRIVATE, FINANCE}),
        ADMIN_ONLY: env.actor("admin-only", {ADMIN}),
        STRANGER: env.actor("stranger", {OTHER_PRIVATE}),
        NO_GRANT: env.actor("no-grant", set()),
        GRANT_REVOKED: env.actor("revoked-grant", full),
    }
    session = env.actor("revoked-session", full)
    actors[SESSION_REVOKED] = session
    anonymous = support.Actor("anonymous", "none", None, env.open_client(), {}, "")
    actors[ANON] = anonymous
    hits = set()
    for kind, actor in actors.items():
        record_requests(actor.client, hits, kind)
    callers = {kind: Caller(a.client, a.headers, kind) for kind, a in actors.items()}
    world = World(env, callers, actors, actors[OWNER])
    world.hits = hits
    return world


def revoke(world):
    """Revoke one grant on a live session and one session through logout; both stay otherwise valid."""
    env, actors = world.env, world.actors
    for scope in (SHARED, PRIVATE, FINANCE):
        env.grant(actors[GRANT_REVOKED], scope, False)
    session = actors[SESSION_REVOKED]
    retained = {**session.headers, "Cookie": f"{identity.COOKIE}={session.token}"}
    logout = session.client.post("/api/v1/auth/logout", headers=session.headers, json={})
    assert logout.status_code == 200, logout.text
    world.callers[SESSION_REVOKED] = Caller(session.client, retained, SESSION_REVOKED)


def relogin(world):
    """The revoked-session account is intact: a fresh login works (revocation is not disablement)."""
    session = world.actors[SESSION_REVOKED]
    login = session.client.post(
        "/api/v1/auth/login", json={"slug": session.slug, "password": SYNTHETIC_PASSWORD}
    )
    assert login.status_code == 200, login.text


@dataclass
class Rec:
    adapter: object
    scope: str
    mark: str
    row: dict
    shared: bool
    extra: tuple = ()  # further identifiers that must not leak (for example a task id)
    content: tuple = ()  # further content canaries (for example an invoice number)

    @property
    def id(self):
        return self.row["id"]

    @property
    def owner_id(self):
        return self.row.get("owner_id") or self.row.get("requested_by")

    def needles_for(self, kind=None):
        """Values that must not appear in a response meant to withhold this record. The creator's
        user id is a needle only for actors that cannot legitimately see the creator's shared
        records (shared records show their owner)."""
        values = [self.mark, self.id, *self.extra, *self.content]
        if not self.shared and self.owner_id and kind not in SHARED_GRANTED:
            values.append(self.owner_id)
        return tuple(values)


# ----------------------------------------------------------------------------------- inspection


def text_of(response):
    try:
        return json.dumps(response.json(), sort_keys=True)
    except ValueError:
        return response.text


def header_text(response):
    return "\n".join(f"{k}: {v}" for k, v in response.headers.items())


def strip_filters(response):
    """Drop the echo of the caller's own request (filters, starting cursor) from a body."""
    try:
        value = response.json()
    except ValueError:
        return response.text
    if isinstance(value, dict):
        value = {key: item for key, item in value.items() if key not in {"filters", "after"}}
    return json.dumps(value, sort_keys=True)


def assert_no_leak(response, recs, where, kind=None):
    """No needle of any withheld record in the body, the headers or the error text."""
    body, headers = strip_filters(response), header_text(response)
    for rec in recs:
        for needle in rec.needles_for(kind):
            assert needle not in body, (where, rec.adapter.name, "needle in body")
            assert needle not in headers, (where, rec.adapter.name, "needle in headers")


COUNT_KEYS = re.compile(r"(^|_)(total|count|counts|has_more|remaining|more)($|_)")


def count_fields(value, path=""):
    """Every count, total or has-more field of the response itself (nested objects included, items
    excluded: a per-record attribute such as a document's ``line_count`` is not a listing total)."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, list):
                continue
            if COUNT_KEYS.search(key) and not isinstance(item, dict):
                found.append((path + key, item))
            found.extend(count_fields(item, path + key + "."))
    return found


def assert_counts_match(response, visible, where):
    """Every count, total or has-more field equals what the actor's visible set implies."""
    for name, value in count_fields(response.json()):
        if isinstance(value, bool):
            assert value is False or visible > 0, (
                where,
                "has-more flag with nothing visible",
                name,
            )
        elif isinstance(value, int):
            assert value == visible, (where, "count differs from the visible set", name, value)


def assert_cursors_clean(cursors, forbidden, where):
    """No continuation token is empty or carries the id of a record the actor must not see."""
    for cursor in cursors:
        assert cursor, (where, "empty continuation token")
        assert all(f not in str(cursor) for f in forbidden), (
            where,
            "continuation token carries a foreign id",
        )


def forget_document(caller, scope, identifier):
    """Forget an uploaded document through its owner's session (leaves only a tombstone)."""
    current = caller.post(f"/api/v1/documents/{identifier}/read", {"scope": scope})
    assert current.status_code == 200, current.text[:200]
    done = caller.post(
        f"/api/v1/documents/{identifier}/forget",
        {"scope": scope, "expected_revision": current.json()["revision"]},
    )
    assert done.status_code == 200, done.text[:200]


# -------------------------------------------------------------------------------------- adapters


class Adapter:
    """One surface. Subclasses fill in the request shapes; the sweep is generic."""

    name = ""
    private_scope = PRIVATE
    shared_scope = SHARED
    not_visible = 404  # status for a foreign private record in a scope the caller holds
    page_size = None  # records needed on one actor to force a second page (None: single page)
    mutations = ()  # names of mutation operations this surface supports on a record
    boundary_model = None  # ORM model whose primary key orders the listing (None: no boundary case)
    boundary_page = 25  # records per page of that listing
    boundary_layout = "same_scope"  # see ``seed_scenario``
    boundary_fresh_world = False  # a world per scenario (surfaces with a per-creator cap)
    scope_denied = 403  # by-ID status when the caller holds no grant for the record's scope
    scope_denied_list = 403  # listing status for the same case ("empty": a 200 with nothing in it)

    def shared_status(self, is_creator, op):
        """Status for ``op`` on a shared record: members read it, owner-only operations are refused."""
        return 200 if (is_creator or op == "read") else 403

    def create(self, actor, scope, label):
        raise NotImplementedError

    def read(self, caller, rec):
        raise NotImplementedError

    def history(self, caller, rec):
        return None

    def export_one(self, caller, rec):
        return None

    extra_by_id = ()  # names of further read-only by-ID methods, called as ``method(caller, rec)``
    has_listing = True
    shared_is_owner_only = False  # True: even in the shared scope only the creator sees a record

    def mutations_for(self, kind):
        return self.mutations

    def listing(self, caller, scope, cursor=None):
        raise NotImplementedError

    def export(self, caller, scope, cursor=None):
        return None

    def ids(self, response):
        return [item["id"] for item in response.json()["items"]]

    def cursor(self, response):
        return response.json().get("next_cursor")

    def mutate(self, caller, rec, name):
        raise NotImplementedError

    def snapshot(self, caller, rec):
        """The owner's view of the record, normalised for before/after comparison."""
        parts = [text_of(self.read(caller, rec))]
        history = self.history(caller, rec)
        if history is not None:
            parts.append(text_of(history))
        return "\n".join(parts)

    def forget(self, caller, rec):
        return None

    # Hooks a surface overrides only where its own documented contract differs from the default.
    scope_visibility = False  # True: every holder of the scope sees every record in it (approvals)
    owner_only_listing = False  # True: the listing ignores ``scope`` and returns the caller's own

    def create_row(self, actor, scope, label):
        response = self.create(actor, scope, label)
        assert response.status_code == 201, (self.name, response.status_code, response.text[:300])
        return response.json()

    def rec_from(self, row, scope, label):
        return Rec(self, scope, label, row, scope == SHARED)

    def expectation(self, world, kind, rec, op):
        """Return a status to replace the generic by-ID expectation, or None."""
        return

    def mutation_expectation(self, world, kind, rec, name):
        return None

    def views(self):
        """Extra read views: {name: (fn(caller, scope) -> response, ids(response) -> list)}."""
        return {}


class Tasks(Adapter):
    name = "tasks"
    mutations = ("correct", "transition", "forget")
    page_size = 26  # the page limit is 25

    def create(self, actor, scope, label):
        return actor.client.post(
            "/api/v1/tasks",
            headers=actor.headers,
            json={"scope": scope, "title": f"Task {label}", "details": f"Details {label}"},
        )

    def _body(self, rec, **extra):
        return {"scope": rec.scope, **extra}

    def read(self, caller, rec):
        return caller.post(f"/api/v1/tasks/{rec.id}/read", self._body(rec))

    def history(self, caller, rec):
        return caller.post(f"/api/v1/tasks/{rec.id}/history", self._body(rec))

    def listing(self, caller, scope, cursor=None):
        return caller.post(
            "/api/v1/tasks/query", {"scope": scope, "status": "all", "after": cursor}
        )

    def export(self, caller, scope, cursor=None):
        return caller.post(
            "/api/v1/tasks/export",
            {"scope": scope, "status": "all", "after": cursor, "acknowledge_copy_limits": True},
        )

    def mutate(self, caller, rec, name):
        revision = rec.row["revision"]
        if name == "correct":
            body = self._body(rec, expected_revision=revision, title="Synthetic hijacked title")
            return caller.post(f"/api/v1/tasks/{rec.id}/correct", body)
        if name == "transition":
            body = self._body(rec, expected_revision=revision, status="done")
            return caller.post(f"/api/v1/tasks/{rec.id}/transition", body)
        body = self._body(rec, expected_revision=revision)
        return caller.post(f"/api/v1/tasks/{rec.id}/forget", body)

    def forget(self, caller, rec):
        current = self.read(caller, rec).json()
        rec.row = current
        return self.mutate(caller, rec, "forget")


class Memory(Adapter):
    name = "memory"
    mutations = ("correct", "forget")
    page_size = 5
    # Listing a scope the caller does not hold is a 200 with nothing in it (``memory.visible``
    # intersects the request with the caller's grants).
    scope_denied_list = "empty"
    # By-ID memory routes take no scope: ``memory.visible`` filters on the caller's own grants and
    # ownership, so a record that is not visible to the caller is a 404 whatever the reason.
    scope_denied = 404

    def create(self, actor, scope, label):
        return actor.client.post(
            "/api/v1/memory",
            headers=actor.headers,
            json={
                "scope": scope,
                "kind": "preference",
                "title": f"Memory {label}",
                "content": {"value": f"Content {label}"},
                "source_type": "manual",
                "source_reference": f"Ref {label}",
                "assessment": "confirmed",
            },
        )

    def read(self, caller, rec):
        return caller.get(f"/api/v1/memory/{rec.id}")

    def history(self, caller, rec):
        return caller.get(f"/api/v1/memory/{rec.id}/history")

    def listing(self, caller, scope, cursor=None):
        params = {"scope": scope, "limit": 2}
        if cursor:
            params["after"] = cursor
        return caller.get("/api/v1/memory", params=params)

    def export(self, caller, scope, cursor=None):
        params = {"scope": scope, "limit": 2}
        if cursor:
            params["after"] = cursor
        return caller.get("/api/v1/memory/export", params=params)

    def mutate(self, caller, rec, name):
        revision = rec.row["revision"]
        if name == "correct":
            return caller.patch(
                f"/api/v1/memory/{rec.id}",
                {
                    "expected_revision": revision,
                    "title": "Synthetic hijacked title",
                    "content": {"value": "hijacked"},
                    "source_type": "manual",
                    "source_reference": "hijack",
                    "assessment": "confirmed",
                    "expires_at": None,
                },
            )
        return caller.post(f"/api/v1/memory/{rec.id}/forget", {"expected_revision": revision})

    def forget(self, caller, rec):
        return self.mutate(caller, rec, "forget")


class Finance(Adapter):
    name = "finance"
    private_scope = FINANCE
    shared_scope = None
    mutations = ("correct", "accept", "forget")

    def values(self, label, title=None):
        return {
            "schema_version": 1,
            "topic": "general",
            "basis": "unknown",
            "title": title or f"Goal {label}",
            "statement": f"Statement {label}",
            "as_of": "2026-11-10",
            "target_date": None,
            "source_reference": f"Ref {label}",
            "source_date": None,
            "amount": None,
            "currency": None,
        }

    def create(self, actor, scope, label):
        return actor.client.post(
            "/api/v1/finance",
            headers=actor.headers,
            json={"scope": scope, "kind": "plan", "values": self.values(label)},
        )

    def read(self, caller, rec):
        return caller.post(f"/api/v1/finance/{rec.id}/read", {"scope": rec.scope})

    def history(self, caller, rec):
        return caller.post(f"/api/v1/finance/{rec.id}/history", {"scope": rec.scope})

    def listing(self, caller, scope, cursor=None):
        return caller.post("/api/v1/finance/query", {"scope": scope, "after": cursor})

    def export(self, caller, scope, cursor=None):
        return caller.post(
            "/api/v1/finance/export",
            {"scope": scope, "after": cursor, "acknowledge_copy_limits": True},
        )

    def export_one(self, caller, rec):
        return caller.post(
            f"/api/v1/finance/{rec.id}/export",
            {
                "scope": rec.scope,
                "expected_revision": rec.row["revision"],
                "acknowledge_copy_limits": True,
                "format": "json",
            },
        )

    def mutate(self, caller, rec, name):
        body = {"scope": rec.scope, "expected_revision": rec.row["revision"]}
        if name == "correct":
            body["values"] = self.values("hijack", title="Synthetic hijacked title")
        if name == "accept":
            body["acknowledge_record_only"] = True
        return caller.post(f"/api/v1/finance/{rec.id}/{name}", body)

    def forget(self, caller, rec):
        current = self.read(caller, rec).json()
        rec.row = current
        return self.mutate(caller, rec, "forget")


class Routines(Adapter):
    name = "routines"
    mutations = ("correct", "pause", "forget")
    extra_by_id = ("occurrences",)

    def occurrences(self, caller, rec):
        return self._post(caller, rec, "occurrences")

    def values(self, scope, label, title=None):
        today = date.today()
        return {
            "scope": scope,
            "title": title or f"Routine {label}",
            "details": f"Details {label}",
            "source_reference": f"Ref {label}",
            "timezone": "Europe/Paris",
            "local_time": "10:00",
            "frequency": "daily",
            "interval": 1,
            "weekdays": [],
            "starts_on": (today + timedelta(days=1)).isoformat(),
            "ends_on": (today + timedelta(days=4)).isoformat(),
            "remind": True,
            "authorize_future_tasks": True,
        }

    def create(self, actor, scope, label):
        return actor.client.post(
            "/api/v1/routines", headers=actor.headers, json=self.values(scope, label)
        )

    def _post(self, caller, rec, op, **extra):
        return caller.post(f"/api/v1/routines/{rec.id}/{op}", {"scope": rec.scope, **extra})

    def read(self, caller, rec):
        return self._post(caller, rec, "read")

    def history(self, caller, rec):
        return self._post(caller, rec, "history")

    def export_one(self, caller, rec):
        return self._post(caller, rec, "export", acknowledge_copy_limits=True)

    def listing(self, caller, scope, cursor=None):
        return caller.post("/api/v1/routines/query", {"scope": scope, "after": cursor})

    def mutate(self, caller, rec, name):
        revision = rec.row["revision"]
        if name == "correct":
            body = self.values(rec.scope, "hijack", title="Synthetic hijacked title")
            return self._post(caller, rec, "correct", **body, expected_revision=revision)
        action = "pause" if name == "pause" else "forget"
        return self._post(caller, rec, "action", expected_revision=revision, action=action)

    def forget(self, caller, rec):
        return self.mutate(caller, rec, "forget")


def calendar_window(label):
    return {
        "complete": True,
        "cursor": f"cursor-{label}",
        "fetched_at": (identity.now_utc() - timedelta(seconds=5)).isoformat(),
        "timezone": "Europe/Paris",
        "start_date": "2026-10-24",
        "end_date": "2026-10-27",
        "events": [
            {
                "kind": "timed",
                "uid": label,
                "recurrence_id": "",
                "sequence": 0,
                "title": f"Event {label}",
                "description": f"Description {label}",
                "status": "confirmed",
                "timezone": "Europe/Paris",
                "start": "2026-10-25T09:00:00+01:00",
                "end": "2026-10-25T10:00:00+01:00",
            }
        ],
    }


class Calendars(Adapter):
    name = "calendars"
    mutations = ("import", "unavailable", "forget")

    def create(self, actor, scope, label):
        return actor.client.post(
            "/api/v1/calendars",
            headers=actor.headers,
            json={"scope": scope, "label": f"Calendar {label}"},
        )

    def create_row(self, actor, scope, label):
        row = super().create_row(actor, scope, label)
        imported = actor.client.post(
            f"/api/v1/calendars/{row['id']}/import",
            headers=actor.headers,
            json={
                "scope": scope,
                "expected_revision": row["revision"],
                "window": calendar_window(label),
            },
        )
        assert imported.status_code == 200, imported.text[:300]
        return imported.json()

    def _post(self, caller, rec, op, **extra):
        return caller.post(f"/api/v1/calendars/{rec.id}/{op}", {"scope": rec.scope, **extra})

    def read(self, caller, rec):
        return self._post(caller, rec, "read")

    def history(self, caller, rec):
        return self._post(caller, rec, "history")

    def export_one(self, caller, rec):
        return self._post(caller, rec, "export", acknowledge_copy_limits=True)

    def listing(self, caller, scope, cursor=None):
        return caller.post("/api/v1/calendars/query", {"scope": scope, "after": cursor})

    def mutate(self, caller, rec, name):
        revision = rec.row["revision"]
        if name == "import":
            window = calendar_window("hijack")
            return self._post(caller, rec, "import", expected_revision=revision, window=window)
        extra = {"reason": "offline"} if name == "unavailable" else {}
        return self._post(caller, rec, name, expected_revision=revision, **extra)

    def forget(self, caller, rec):
        return self._post(caller, rec, "forget", expected_revision=rec.row["revision"])

    def briefing(self, caller, scope):
        return caller.post(
            "/api/v1/calendars/briefing",
            {"scope": scope, "day": "2026-10-25", "timezone": "Europe/Paris"},
        )

    def views(self):
        return {"briefing": (self.briefing, lambda r: [c["id"] for c in r.json()["calendars"]])}


class Reminders(Adapter):
    name = "reminders"
    mutations = ("cancel", "schedule")
    shared_is_owner_only = True  # reminders are owner-only even in the shared scope

    def shared_status(self, is_creator, op):
        return 200 if is_creator else self.not_visible

    def create_row(self, actor, scope, label):
        task = actor.client.post(
            "/api/v1/tasks",
            headers=actor.headers,
            json={"scope": scope, "title": f"Reminded task {label}", "details": f"Details {label}"},
        )
        assert task.status_code == 201, task.text[:300]
        task = task.json()
        when = identity.now_utc() + timedelta(days=2)
        scheduled = actor.client.post(
            "/api/v1/reminders/schedule",
            headers=actor.headers,
            json={
                "scope": scope,
                "task_id": task["id"],
                "expected_task_revision": task["revision"],
                "expected_revision": None,
                "scheduled_at": when.isoformat(),
            },
        )
        assert scheduled.status_code == 200, scheduled.text[:300]
        return {**scheduled.json(), "task_scope": scope}

    def rec_from(self, row, scope, label):
        return Rec(self, scope, label, row, scope == SHARED, extra=(row["task_id"],))

    def _body(self, rec, **extra):
        return {"scope": rec.scope, "task_id": rec.row["task_id"], **extra}

    def read(self, caller, rec):
        return caller.post("/api/v1/reminders/read", self._body(rec))

    def history(self, caller, rec):
        return caller.post("/api/v1/reminders/history", self._body(rec))

    def listing(self, caller, scope, cursor=None):
        return caller.post(
            "/api/v1/reminders/query", {"scope": scope, "state": "all", "after": cursor}
        )

    def export(self, caller, scope, cursor=None):
        return caller.post(
            "/api/v1/reminders/export",
            {"scope": scope, "state": "all", "after": cursor, "acknowledge_copy_limits": True},
        )

    def ids(self, response):
        return [item["reminder"]["id"] for item in response.json()["items"]]

    def mutate(self, caller, rec, name):
        if name == "schedule":
            return caller.post(
                "/api/v1/reminders/schedule",
                {
                    "scope": rec.scope,
                    "task_id": rec.row["task_id"],
                    "expected_task_revision": rec.row["task_revision"],
                    "expected_revision": rec.row["revision"],
                    "scheduled_at": (identity.now_utc() + timedelta(days=3)).isoformat(),
                },
            )
        return caller.post(
            "/api/v1/reminders/action",
            self._body(rec, expected_revision=rec.row["revision"], action="cancel"),
        )

    def forget(self, caller, rec):
        self.mutate(caller, rec, "cancel")  # may already be cancelled; the task is what matters
        task = caller.post(f"/api/v1/tasks/{rec.row['task_id']}/read", {"scope": rec.scope}).json()
        return caller.post(
            f"/api/v1/tasks/{task['id']}/forget",
            {"scope": rec.scope, "expected_revision": task["revision"]},
        )


class Approvals(Adapter):
    """Approvals are scope-based by their documented contract (docs/APPROVALS.md): every current
    member of the record's scope may fetch and review it, only the requester may cancel or consume,
    and a scope the caller does not hold answers 404 exactly like a missing id."""

    name = "approvals"
    scope_visibility = True
    scope_denied = 404
    mutations = ("cancel", "consume", "decide")

    def create(self, actor, scope, label):
        return actor.client.post(
            "/api/v1/approvals",
            headers=actor.headers,
            json={"scope": scope, "payload": {"note": f"Approval {label}"}},
        )

    def read(self, caller, rec):
        return caller.get(f"/api/v1/approvals/{rec.id}")

    def listing(self, caller, scope, cursor=None):
        return caller.post("/api/v1/approvals/query", {"scope": scope, "after": cursor})

    def holds(self, kind, rec):
        if rec.shared:
            return kind in SHARED_GRANTED
        return kind in {OWNER, PEER, ADMIN_SAME}

    def expectation(self, world, kind, rec, op):
        if kind in SESSION_DENIED:
            return 401
        return 200 if self.holds(kind, rec) else 404

    def mutations_for(self, kind):
        # A scope member may legitimately decide (documented), so decide is exercised only by
        # callers that hold no grant for the scope.
        return self.mutations if kind not in {PEER, ADMIN_SAME} else ("cancel", "consume")

    def mutation_expectation(self, world, kind, rec, name):
        if kind in SESSION_DENIED:
            return 401
        return 403 if self.holds(kind, rec) else 404

    def mutate(self, caller, rec, name):
        binding = {
            "payload_hash": rec.row["payload_hash"],
            "policy_version": rec.row["policy_version"],
        }
        if name == "decide":
            binding["decision"] = "approve"
        return caller.post(f"/api/v1/approvals/{rec.id}/{name}", binding)

    def forget(self, caller, rec):
        return self.mutate(caller, rec, "cancel")


class Discovery(Adapter):
    """Discovery records are owner-only even for another holder of the same private scope, and the
    by-ID route takes no scope (not visible is 404 whatever the reason)."""

    name = "discovery"
    shared_scope = None
    scope_denied = 404
    scope_denied_list = "empty"
    owner_only_listing = True
    mutations = ("details", "feedback")
    page_size = 5

    def proposal(self, scope, label, title=None):
        return {
            "topic": "synthetic-tagging",
            "summary": f"Summary {label}",
            "evidence": [
                {
                    "title": "Synthetic primary source",
                    "url": "https://example.org/research",
                    "observed_at": "2026-01-01T00:00:00Z",
                }
            ],
            "benefit": "Synthetic benefit",
            "privacy": "Synthetic privacy",
            "maturity_license": "Synthetic",
            "hardware_cost": "Synthetic",
            "alternatives_dependencies": "Synthetic",
            "experiment": "Synthetic",
            "title": title or f"Idea {label}",
            "scope": scope,
        }

    def create(self, actor, scope, label):
        return actor.client.post(
            "/api/v1/discovery", headers=actor.headers, json=self.proposal(scope, label)
        )

    def read(self, caller, rec):
        return caller.get(f"/api/v1/discovery/{rec.id}")

    def listing(self, caller, scope, cursor=None):
        params = {"limit": 2}
        if cursor:
            params["after"] = cursor["id"]
            params["after_priority"] = cursor["priority"]
        return caller.get("/api/v1/discovery", params=params)

    def cursor(self, response):
        return response.json().get("next_cursor")

    def inbox(self, caller, scope):
        return caller.post("/api/v1/discovery/inbox", {})

    def views(self):
        return {"inbox": (self.inbox, lambda r: [i["id"] for i in r.json()["items"]])}

    def mutate(self, caller, rec, name):
        revision = rec.row["revision"]
        if name == "details":
            body = self.proposal(rec.scope, "hijack", title="Synthetic hijacked title")
            body.pop("scope")
            return caller.put(
                f"/api/v1/discovery/{rec.id}/details", {**body, "expected_revision": revision}
            )
        return caller.put(
            f"/api/v1/discovery/{rec.id}/feedback",
            {"expected_revision": revision, "choice": "later", "note": "hijack"},
        )


class ContextCandidates(Adapter):
    """The local-context catalogue and preview over memory records (one explicit scope)."""

    name = "context"
    mutations = ()

    def create(self, actor, scope, label):
        return Memory().create(actor, scope, label)

    def read(self, caller, rec):  # a one-record preview releases the record's content
        return caller.post(
            "/api/v1/context/preview",
            {
                "scope": rec.scope,
                "selections": [{"id": rec.id, "expected_revision": rec.row["revision"]}],
            },
        )

    def listing(self, caller, scope, cursor=None):
        params = {"scope": scope}
        if cursor:
            params["after"] = cursor
        return caller.get("/api/v1/context/candidates", params=params)

    def forget(self, caller, rec):
        return Memory().forget(caller, rec)


class EmailIntake(Adapter):
    """An ingested email original is owner-only provenance: a non-owner shared reader gets 403."""

    name = "email-intake"
    has_listing = False
    shared_is_owner_only = True
    mutations = ()

    def message(self, label):
        mail = EmailMessage(policy=email_policy.SMTP)
        mail["From"] = "sender@example.invalid"
        mail["To"] = "recipient@example.invalid"
        mail["Subject"] = f"Subject {label}"
        mail["Message-ID"] = f"<{label}@example.invalid>"
        mail.set_content(f"Body {label}. Untrusted instructions are inert.")
        mail.add_attachment(
            f"Issuer: Synthetic {label}\nTotal: 10,00\n".encode(),
            maintype="text",
            subtype="plain",
            filename=f"{label}.txt",
        )
        mail.set_boundary(f"boundary-{label}")
        return mail.as_bytes()

    def create(self, actor, scope, label):
        return actor.client.post(
            "/api/v1/email-intake",
            headers=actor.headers,
            json={
                "scope": scope,
                "title": f"Email {label}",
                "message_base64": base64.b64encode(self.message(label)).decode(),
            },
        )

    def create_row(self, actor, scope, label):
        return super().create_row(actor, scope, label)["document"]

    def shared_status(self, is_creator, op):
        return 200 if is_creator else 403

    def _post(self, caller, rec, op, **extra):
        return caller.post(
            f"/api/v1/email-intake/{rec.id}/{op}",
            {"scope": rec.scope, "expected_document_revision": rec.row["revision"], **extra},
        )

    def read(self, caller, rec):
        return self._post(caller, rec, "read")

    def export_one(self, caller, rec):
        return self._post(caller, rec, "export", acknowledge_copy_limits=True)

    def forget(self, caller, rec):
        return forget_document(caller, rec.scope, rec.id)


class Invoices(Adapter):
    """Reviewed invoice records over an uploaded, reviewed document (docs/INVOICE_REVIEW.md).
    Shared invoices are readable by shared members; history, export, and every change are owner-only."""

    name = "invoices"
    has_listing = False
    mutations = ("prepare", "review", "forget")
    extra_by_id = ("duplicates",)

    def shared_status(self, is_creator, op):
        # docs/INVOICE_REVIEW.md: shared members read the review and its duplicate hints.
        return 200 if is_creator or op in {"read", "duplicates"} else 403

    def create_row(self, actor, scope, label):
        number = "INV-" + label[-8:].upper()
        text = (
            "Issuer: Synthetic Vendor\n"
            f"Invoice number: {number}\n"
            "Invoice date: 2026-11-01\nDue date: 2026-11-30\nTotal: 123,45\nCurrency: EUR\n"
        )
        doc = reviewed(
            actor.client,
            actor.headers,
            text=text,
            scope=scope,
            title=f"Invoice {label}",
            filename=f"{label}.txt",
            source_reference=f"Ref {label}",
        )
        assert doc.get("id"), doc
        receipt = invoice_call(actor.client, actor.headers, doc, "prepare")
        assert receipt.status_code == 200, receipt.text[:300]
        decided = invoice_call(
            actor.client,
            actor.headers,
            doc,
            "review",
            receipt.json(),
            decisions=invoice_decisions(number),
        )
        assert decided.status_code == 200, decided.text[:300]
        return {**doc, "review_revision": decided.json()["review_revision"], "number": number}

    def rec_from(self, row, scope, label):
        return Rec(self, scope, label, row, scope == SHARED, content=(row["number"],))

    def _post(self, caller, rec, op, **extra):
        return caller.post(f"/api/v1/invoices/{rec.id}/{op}", {"scope": rec.scope, **extra})

    def read(self, caller, rec):
        return self._post(caller, rec, "read")

    def history(self, caller, rec):
        return self._post(caller, rec, "history")

    def duplicates(self, caller, rec):
        return self._post(caller, rec, "duplicates")

    def export_one(self, caller, rec):
        return self._post(caller, rec, "export", acknowledge_copy_limits=True)

    def mutate(self, caller, rec, name):
        extra = {
            "expected_document_revision": rec.row["revision"],
            "expected_review_revision": rec.row["review_revision"],
        }
        if name == "review":
            extra.update(attest_original=True, decisions=invoice_decisions(rec.row["number"]))
        return self._post(caller, rec, name, **extra)

    def forget(self, caller, rec):
        return forget_document(caller, rec.scope, rec.id)


class Documents(Adapter):
    """Reviewed documents (docs/DOCUMENT_LIBRARY.md). The existing isolation suites already read
    every document operation as every actor; this adapter adds the part they leave open: foreign
    correct, replace and forget attempts on a private record, with state-unchanged snapshots."""

    name = "documents"
    mutations = ("correct", "replace", "forget")
    extra_by_id = ("original", "excerpt")

    def shared_status(self, is_creator, op):
        return 200 if is_creator or op in {"read", "original", "excerpt"} else 403

    def create(self, actor, scope, label):
        return upload(
            actor.client,
            actor.headers,
            scope=scope,
            title=f"Doc {label}",
            filename=f"{label}.md",
            source_reference=f"Ref {label}",
            original_base64=base64.b64encode(f"Record {label}".encode()).decode(),
        )

    def create_row(self, actor, scope, label):
        text = f"Synthetic isolation record {label}\nREF {label} value 100\n"
        doc = reviewed(
            actor.client,
            actor.headers,
            text=text,
            scope=scope,
            title=f"Doc {label}",
            filename=f"{label}.md",
            source_reference=f"Ref {label}",
        )
        assert doc.get("id"), doc
        return {**doc, "_encoded": base64.b64encode(text.encode()).decode()}

    def rec_from(self, row, scope, label):
        return Rec(
            self,
            scope,
            label,
            row,
            scope == SHARED,
            extra=(row["sha256"],),
            content=(row["_encoded"],),
        )

    def _post(self, caller, rec, op, **extra):
        return caller.post(f"/api/v1/documents/{rec.id}/{op}", {"scope": rec.scope, **extra})

    def read(self, caller, rec):
        return self._post(caller, rec, "read")

    def history(self, caller, rec):
        return self._post(caller, rec, "history")

    def original(self, caller, rec):
        return self._post(
            caller,
            rec,
            "original",
            expected_revision=rec.row["revision"],
            acknowledge_copy_limits=True,
        )

    def excerpt(self, caller, rec):
        return self._post(
            caller, rec, "excerpt", expected_revision=rec.row["revision"], start_line=1, end_line=2
        )

    def listing(self, caller, scope, cursor=None):
        return caller.post("/api/v1/documents/query", {"scope": scope, "after": cursor})

    def export(self, caller, scope, cursor=None):
        return caller.post(
            "/api/v1/documents/export",
            {"scope": scope, "after": cursor, "acknowledge_copy_limits": True},
        )

    def mutate(self, caller, rec, name):
        revision = rec.row["revision"]
        if name == "correct":
            return self._post(
                caller,
                rec,
                "correct",
                expected_revision=revision,
                title="Synthetic hijacked title",
                source_reference="hijack",
                reviewed=True,
            )
        if name == "replace":
            return self._post(
                caller,
                rec,
                "replace",
                expected_revision=revision,
                filename="swap.md",
                original_base64=base64.b64encode(b"swap").decode(),
            )
        return self._post(caller, rec, "forget", expected_revision=revision)

    def forget(self, caller, rec):
        return forget_document(caller, rec.scope, rec.id)


ADAPTERS = {
    adapter.name: adapter
    for adapter in (
        Tasks(), Memory(), Finance(), Routines(), Calendars(), Reminders(), Approvals(),
        Discovery(), ContextCandidates(), EmailIntake(), Invoices(), Documents(),
    )
}  # fmt: skip


# ------------------------------------------------------------------------------------- the sweep


@dataclass
class Seed:
    owner_private: list
    owner_shared: list
    peer_private: list
    peer_shared: list

    @property
    def everything(self):
        return self.owner_private + self.owner_shared + self.peer_private + self.peer_shared


def make(world, adapter, actor_kind, scope, label):
    actor = world.actors[actor_kind]
    rec = adapter.rec_from(adapter.create_row(actor, scope, label), scope, label)
    world.log.append((actor_kind, rec))
    if rec.shared:
        world.shared_records.append((actor_kind, rec))
    return rec


def seed(world, adapter):
    """Owner A and peer B each hold private records (interleaved) and, where the surface has a
    shared scope, one shared record. Enough owner records are made to force a second page."""
    owner_n = adapter.page_size or 3
    seed_ = Seed([], [], [], [])
    for index in range(owner_n):
        seed_.owner_private.append(
            make(
                world, adapter, OWNER, adapter.private_scope, mark(f"{adapter.name[:3]}-ap{index}-")
            )
        )
        if index in {owner_n // 2, owner_n - 1}:  # peer records land between and after owner pages
            seed_.peer_private.append(
                make(world, adapter, PEER, adapter.private_scope, mark(f"{adapter.name[:3]}-bp-"))
            )
    if adapter.shared_scope:
        seed_.owner_shared.append(
            make(world, adapter, OWNER, adapter.shared_scope, mark(f"{adapter.name[:3]}-as-"))
        )
        seed_.peer_shared.append(
            make(world, adapter, PEER, adapter.shared_scope, mark(f"{adapter.name[:3]}-bs-"))
        )
    return seed_


def creator_kind(world, rec):
    for kind, candidate in world.log:
        if candidate is rec:
            return kind
    raise AssertionError("record not created by this harness")


def by_id_expectation(world, adapter, kind, rec, op="read"):
    """Status an actor must get for ``op`` on ``rec``, from the documented owner/shared rules."""
    if kind in SESSION_DENIED:
        return 401
    override = adapter.expectation(world, kind, rec, op)
    if override is not None:
        return override
    creator = creator_kind(world, rec)
    if rec.shared:
        if kind in SHARED_GRANTED:
            return adapter.shared_status(kind == creator, op)
        return adapter.scope_denied
    if kind == creator:
        return 200
    if kind in SCOPE_DENIED:
        return adapter.scope_denied
    return adapter.not_visible  # holds the private grant but is not the creator


def visible_ids(world, adapter, kind, scope, seed_):
    """The record ids ``kind`` may see in ``scope``, computed from creation, not from the API."""
    if kind in SESSION_DENIED:
        return None
    pool = seed_.everything
    if adapter.owner_only_listing:  # the listing ignores scope: the caller's own records only
        if kind in SCOPE_DENIED and kind != READER:
            return []
        return [r.id for r in pool if creator_kind(world, r) == kind]
    if adapter.scope_visibility:  # every holder of the scope sees every record in it
        held = {OWNER, PEER, ADMIN_SAME} if scope != SHARED else SHARED_GRANTED
        if kind not in held:
            return None
        return [r.id for r in pool if r.scope == scope]
    if scope == SHARED:
        if kind not in SHARED_GRANTED:
            return None
        if adapter.shared_is_owner_only:
            return [r.id for r in pool if r.shared and creator_kind(world, r) == kind]
        return [r.id for r in pool if r.shared]
    if kind not in {OWNER, PEER, ADMIN_SAME}:  # the private scope grant
        return None
    return [r.id for r in pool if not r.shared and creator_kind(world, r) == kind]


def walk(adapter, caller, scope, listing):
    """Every page of a listing; returns (ids, pages, cursors)."""
    ids, cursors, cursor = [], [], None
    for _ in range(50):
        response = listing(caller, scope, cursor)
        assert response.status_code == 200, (
            adapter.name,
            response.status_code,
            response.text[:200],
        )
        ids.extend(adapter.ids(response))
        cursor = adapter.cursor(response)
        if not cursor:
            return ids, len(cursors) + 1, cursors, response
        cursors.append(cursor)
    raise AssertionError("pagination did not end")


def sweep_by_id(world, adapter, seed_):
    """Read and history by ID for every actor and record: exact status, nothing withheld released."""
    everything = seed_.everything
    for kind, caller in world.callers.items():
        for rec in everything:
            for op in ("read", "history", "export_one", *adapter.extra_by_id):
                if op != "read" and getattr(adapter, op)(world.callers[OWNER], rec) is None:
                    continue
                response = getattr(adapter, op)(caller, rec)
                expected = by_id_expectation(world, adapter, kind, rec, op)
                where = (adapter.name, kind, op, rec.mark)
                assert response.status_code == expected, (where, response.status_code, expected)
                if expected != 200:
                    assert_no_leak(response, [rec], where, kind)
                    assert_no_leak(response, withheld_from(world, kind, everything), where, kind)


def withheld_from(world, kind, everything):
    """Records ``kind`` must never learn of through a denial: every private record it did not create,
    and every record of a scope it has no grant for."""
    out = []
    for rec in everything:
        creator = creator_kind(world, rec)
        if rec.shared and kind in SHARED_GRANTED:
            continue
        if not rec.shared and kind == creator:
            continue
        out.append(rec)
    return out


def shared_view(adapter, scope):
    """True where other records, made by other modules, may legitimately be visible as well: the
    shared scope (every member sees every shared record) and scope-based surfaces. The disposable
    PostgreSQL database keeps committed rows from other tests, so the expected set is a floor there
    and exact only where visibility is per user."""
    return (scope == SHARED and not adapter.shared_is_owner_only) or adapter.scope_visibility


def check_visible_set(world, adapter, kind, scope, ids, expected, everything, where):
    if not shared_view(adapter, scope):
        assert sorted(ids) == sorted(expected), (where, "listing differs from expected")
        return
    assert set(expected) <= set(ids), (where, "an entitled record is missing")
    visible = set(expected)
    withheld = {r.id for r in everything if r.id not in visible}
    assert not (set(ids) & withheld), (where, "a withheld record is listed")


def assert_same_for_every_holder(seen, adapter):
    """Where visibility is shared, every actor holding the scope sees the identical set."""
    for key, by_kind in seen.items():
        sets = {frozenset(v) for v in by_kind.values()}
        if shared_view(adapter, key[1]):
            assert len(sets) == 1, (adapter.name, key, "holders of the scope see different sets")


def sweep_lists(world, adapter, seed_):
    """Listings, exports, counts, cursors and pages for every actor in every scope."""
    scopes = [adapter.private_scope] + ([adapter.shared_scope] if adapter.shared_scope else [])
    everything = seed_.everything
    if not adapter.has_listing:
        return
    seen = {}
    for kind, caller in world.callers.items():
        for scope in scopes:
            for name in ("listing", "export"):
                fn = getattr(adapter, name)
                if name == "export" and adapter.export(world.callers[OWNER], scope) is None:
                    continue
                expected = visible_ids(world, adapter, kind, scope, seed_)
                where = (adapter.name, kind, name, scope)
                if expected is None:
                    first = fn(caller, scope, None)
                    if kind in SESSION_DENIED:
                        assert first.status_code == 401, (where, first.status_code)
                    elif adapter.scope_denied_list == "empty":
                        assert first.status_code == 200 and adapter.ids(first) == [], (where,)
                        assert not adapter.cursor(first), (where, "cursor with nothing visible")
                        assert_counts_match(first, 0, where)
                    else:
                        assert first.status_code == adapter.scope_denied_list, (
                            where,
                            first.status_code,
                        )
                    assert_no_leak(first, everything, where, kind)
                    continue
                ids, pages, cursors, _last = walk(adapter, caller, scope, fn)
                check_visible_set(world, adapter, kind, scope, ids, expected, everything, where)
                seen.setdefault((name, scope), {})[kind] = frozenset(ids)
                assert len(ids) == len(set(ids)), (where, "duplicate across pages")
                foreign = [r for r in everything if r.id not in expected]
                forbidden = [r.id for r in foreign if not (r.shared and kind in SHARED_GRANTED)]
                assert_cursors_clean(cursors, forbidden, where)
                if kind == OWNER and scope == adapter.private_scope and adapter.page_size:
                    assert pages >= 2, (where, "the owner's own listing was not paged")
                first = fn(caller, scope, None)
                body = strip_filters(first)
                for rec in foreign:
                    if rec.shared and kind in SHARED_GRANTED:
                        continue
                    for needle in rec.needles_for(kind):
                        assert needle not in body, (where, "foreign needle in listing")
                assert_counts_match(first, len(ids), where)
    assert_same_for_every_holder(seen, adapter)


def replay_foreign_cursor(world, adapter, seed_):
    """A cursor issued to the owner must not make the peer's listing reveal the owner's records."""
    if not adapter.page_size:
        return
    owner = world.callers[OWNER]
    first = adapter.listing(owner, adapter.private_scope, None)
    cursor = adapter.cursor(first)
    assert cursor, "the owner's first page has a continuation"
    for kind in (PEER, ADMIN_SAME):
        response = adapter.listing(world.callers[kind], adapter.private_scope, cursor)
        where = (adapter.name, kind, "foreign cursor")
        own = visible_ids(world, adapter, kind, adapter.private_scope, seed_)
        if response.status_code == 200:
            assert set(adapter.ids(response)) <= set(own), (where, "released a foreign id")
        else:
            assert response.status_code in (400, 404, 422), (where, response.status_code)
        assert_no_leak(response, seed_.owner_private, where, kind)


def snapshots(world, adapter, recs):
    owner = world.callers[OWNER]
    return {r.id: adapter.snapshot(owner, r) for r in recs}


def sweep_mutations(world, adapter, seed_):
    """Foreign correct/forget/transition/... attempts are refused with the exact status and the
    owner's record, history included, is byte-for-byte unchanged afterwards."""
    if not adapter.mutations:
        return
    targets = seed_.owner_private
    target = targets[0]
    before = snapshots(world, adapter, targets)
    for kind, caller in world.callers.items():
        if kind == OWNER:
            continue
        for name in adapter.mutations_for(kind):
            response = adapter.mutate(caller, target, name)
            expected = adapter.mutation_expectation(world, kind, target, name)
            if expected is None:
                expected = by_id_expectation(world, adapter, kind, target)
            where = (adapter.name, kind, name)
            assert response.status_code == expected, (where, response.status_code, expected)
            assert_no_leak(response, [target], where, kind)
    after = snapshots(world, adapter, targets)
    assert before == after, (adapter.name, "a refused foreign mutation changed the record")


def sweep_shared_legitimacy(world, adapter, seed_):
    """Entitled shared readers keep access: the shared record is readable and listed for them."""
    if not adapter.shared_scope or adapter.shared_is_owner_only:
        return
    shared = seed_.owner_shared[0]
    for kind in (OWNER, PEER, READER):
        response = adapter.read(world.callers[kind], shared)
        assert response.status_code == 200, (adapter.name, kind, response.status_code)
        assert any(value in response.text for value in shared.needles_for(None))
    if adapter.has_listing:
        ids = walk(adapter, world.callers[READER], adapter.shared_scope, adapter.listing)[0]
        entitled = {r.id for r in seed_.owner_shared + seed_.peer_shared}
        assert entitled <= set(ids), (adapter.name, "an entitled shared record is not listed")


def cleanup(world):
    """Forget what a sweep committed to the shared scope (the PostgreSQL database keeps rows). Every
    record is attempted; failures are reported together afterwards."""
    failures = []
    for kind, rec in world.shared_records:
        caller = world.callers[OWNER] if kind == OWNER else world.callers[PEER]
        if kind == READER:
            caller = world.callers[READER]
        try:
            rec.adapter.forget(caller, rec)
        except (AssertionError, KeyError, ValueError, TypeError) as error:  # reported below
            failures.append((rec.adapter.name, rec.mark, repr(error)[:120]))
    assert not failures, ("cleanup failed", failures)


def sweep_views(world, adapter, seed_):
    """Read views that are not a plain listing (briefings, inboxes): the same visible set, no leak."""
    scopes = [adapter.private_scope] + ([adapter.shared_scope] if adapter.shared_scope else [])
    everything = seed_.everything
    for view, (fn, ids_of) in adapter.views().items():
        for kind, caller in world.callers.items():
            for scope in scopes:
                expected = visible_ids(world, adapter, kind, scope, seed_)
                response = fn(caller, scope)
                where = (adapter.name, view, kind, scope)
                if expected is None:
                    status = 401 if kind in SESSION_DENIED else 403
                    assert response.status_code == status, (where, response.status_code, status)
                    assert_no_leak(response, everything, where, kind)
                    continue
                assert response.status_code == 200, (where, response.status_code)
                check_visible_set(
                    world, adapter, kind, scope, ids_of(response), expected, everything, where
                )
                body = strip_filters(response)
                for rec in everything:
                    if rec.id in expected:
                        continue
                    for needle in rec.needles_for(kind):
                        assert needle not in body, (where, "foreign needle in view")


def sweep_foreign_create(world, adapter, seed_):
    """A caller without the scope grant, or without a session, cannot create into the private scope."""
    if type(adapter).create is Adapter.create:
        return
    owner = world.callers[OWNER]
    before = None
    if adapter.has_listing:
        before = sorted(walk(adapter, owner, adapter.private_scope, adapter.listing)[0])
    for kind in (READER, ADMIN_ONLY, STRANGER, NO_GRANT, GRANT_REVOKED, SESSION_REVOKED, ANON):
        caller = world.callers[kind]
        actor = support.Actor(kind, kind, None, caller.client, caller.headers, "")
        response = adapter.create(actor, adapter.private_scope, mark(f"{adapter.name[:3]}-xc-"))
        expected = 401 if kind in SESSION_DENIED else 403
        assert response.status_code == expected, (adapter.name, kind, response.status_code)
        assert_no_leak(response, seed_.everything, (adapter.name, kind, "create"), kind)
    if before is not None:
        after = sorted(walk(adapter, owner, adapter.private_scope, adapter.listing)[0])
        assert before == after, (adapter.name, "a refused create changed the owner's listing")


ADMIN_ROUTES = (
    ("/api/v1/operations/read", {"scope": "technical_admin"}),
    ("/api/v1/operations/audit-summary", {"scope": "technical_admin", "window": "24h"}),
    ("/api/v1/operations/work-status", {"scope": "technical_admin"}),
)


def sweep_operations(world, seeds):
    """The technical administrator reads operational observations: none carries any record content
    or identifier; every other actor is denied. ``audit-summary`` needs the PostgreSQL audit
    function and answers 503 on SQLite (documented in docs/OPERATIONS_OVERVIEW.md)."""
    everything = [r for seed_ in seeds for r in seed_.everything]
    admins = {ADMIN_SAME, ADMIN_ONLY}
    for kind, caller in world.callers.items():
        for path, body in ADMIN_ROUTES:
            response = caller.post(path, body)
            where = ("operations", kind, path)
            if kind in SESSION_DENIED:
                expected = 401
            elif kind in admins:
                expected = (
                    503 if path.endswith("audit-summary") and world.env.label == "sqlite" else 200
                )
            else:
                expected = 403
            assert response.status_code == expected, (where, response.status_code, expected)
            assert_no_leak(response, everything, where, kind)


def content_marks(seeds):
    """Content canaries of every seeded record (marks, plus invoice numbers): never in logs or audit."""
    out = set()
    for seed_ in seeds:
        for rec in seed_.everything:
            out.add(rec.mark)
            out.update(rec.content)
    return sorted(out)


def log_text(record):
    values = [record.getMessage(), str(record.args), str(record.msg)]
    values.extend(
        str(value) for key, value in record.__dict__.items() if key not in {"args", "msg"}
    )
    return "\n".join(values)


def assert_logs_clean(records, marks):
    """No captured log message or structured field carries a content canary."""
    assert records is not None
    for record in records:
        text = log_text(record)
        for value in marks:
            assert value not in text, ("canary in a log record", record.name, record.levelname)


def audit_rows_text(env):
    """Every audit column of every row, read through the privileged provisioning session (the
    restricted runtime role has no SELECT on audit_events by design)."""
    with env.provisioner.begin() as db:
        rows = db.execute(select(AuditEvent)).scalars().all()
        columns = [column.name for column in AuditEvent.__table__.columns]
        return ["\n".join(str(getattr(row, name)) for name in columns) for row in rows]


def assert_audit_clean(env, marks):
    rows = audit_rows_text(env)
    assert rows, "no audit rows were written: the check would prove nothing"
    for text in rows:
        for value in marks:
            assert value not in text, "content canary in an audit row"


def configure_boundaries():
    """Which ORM model orders each paginated listing and how many records a page holds. Each
    listing orders a keyset by the record's UUID primary key after filtering visibility in SQL;
    discovery orders by a computed score and is not given a boundary case."""
    from app import models

    table = {
        "tasks": (models.ManualTask, 25),
        "finance": (models.FinancialRecord, 25),
        "routines": (models.Routine, 25),
        "calendars": (models.CalendarSource, 25),
        "reminders": (models.TaskReminder, 25),
        "approvals": (models.Approval, 25),
        "documents": (models.DocumentRecord, 25),
        "memory": (models.MemoryRecord, 2),  # the memory adapter lists with limit=2
        "context": (models.MemoryRecord, 25),
    }
    for name, (model, page) in table.items():
        ADAPTERS[name].boundary_model = model
        ADAPTERS[name].boundary_page = page
    ADAPTERS["approvals"].boundary_layout = "foreign_scope"
    for name in ("calendars", "routines"):  # a creator may hold at most ten
        ADAPTERS[name].boundary_layout = "shared_spread"
        ADAPTERS[name].boundary_fresh_world = True


def sweep_reminder_preferences(world):
    """Reminder preferences have no identifier: the row is the caller's own for a scope. Another
    holder of the same private scope reads their own defaults, never the owner's; a caller without
    the grant is refused; a refused save changes nothing."""
    path = "/api/v1/reminders/preferences/"
    owner = world.callers[OWNER]
    saved = owner.post(
        path + "save",
        {
            "scope": PRIVATE,
            "expected_revision": 0,
            "enabled": True,
            "timezone": "UTC",
            "quiet_start": 0,
            "quiet_end": 0,
            "daily_limit": 3,
        },
    )
    assert saved.status_code == 200, saved.text[:200]
    first = owner.post(path + "read", {"scope": PRIVATE})
    assert first.status_code == 200 and '"daily_limit": 3' in text_of(first)
    before = first.json()
    owner_id = world.actors[OWNER].user_id
    for kind, caller in world.callers.items():
        if kind == OWNER:
            continue
        read = caller.post(path + "read", {"scope": PRIVATE})
        save = caller.post(
            path + "save",
            {
                "scope": PRIVATE,
                "expected_revision": 0,
                "enabled": False,
                "timezone": "UTC",
                "quiet_start": 1,
                "quiet_end": 2,
                "daily_limit": 1,
            },
        )
        where = ("reminder preferences", kind)
        if kind in SESSION_DENIED:
            assert (read.status_code, save.status_code) == (401, 401), where
        elif kind in SAME_PRIVATE_GRANT:
            # Holding the scope entitles the caller to their own preferences, not the owner's.
            assert read.status_code == 200, (where, read.status_code)
            assert '"daily_limit": 3' not in text_of(read), (where, "the owner's preferences")
            assert str(owner_id) not in text_of(read), (where, "the owner's id")
        else:
            assert (read.status_code, save.status_code) == (403, 403), where
            assert str(owner_id) not in text_of(read), where
    after = owner.post(path + "read", {"scope": PRIVATE}).json()
    assert {k: v for k, v in before.items() if k != "checked_at"} == {
        k: v for k, v in after.items() if k != "checked_at"
    }, "a foreign preferences save changed the owner's preferences"


def registered_operations(application=None):
    """Every (METHOD, path template) registered on the application, walked from ``app.routes``.
    Included routers are followed through ``original_router``; hidden (not in the OpenAPI schema)
    routes are included."""
    from app.main import app as default_app

    found = set()

    def walk_routes(routes):
        for route in routes:
            nested = getattr(route, "original_router", None)
            if nested is not None:
                walk_routes(nested.routes)
            elif hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods or ():
                    if method not in {"HEAD", "OPTIONS"}:
                        found.add((method, route.path))

    walk_routes((application or default_app).routes)
    return found


def run_sweep(world, name, caplog):
    """The complete sweep of one adapter on one world; returns the routes the sweep requested."""
    import logging

    caplog.set_level(logging.DEBUG)
    adapter = ADAPTERS[name]
    seeded = seed(world, adapter)
    revoke(world)
    sweep_by_id(world, adapter, seeded)
    sweep_lists(world, adapter, seeded)
    sweep_views(world, adapter, seeded)
    replay_foreign_cursor(world, adapter, seeded)
    sweep_shared_legitimacy(world, adapter, seeded)
    sweep_mutations(world, adapter, seeded)
    sweep_foreign_create(world, adapter, seeded)
    if name == "reminders":
        sweep_reminder_preferences(world)
    relogin(world)
    marks = content_marks([seeded])
    assert_logs_clean(caplog.records, marks)
    assert_audit_clean(world.env, marks)
    return set(world.hits)


def run_operations_sweep(world, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    seeds = [seed(world, ADAPTERS[name]) for name in ("tasks", "memory", "finance")]
    revoke(world)
    sweep_operations(world, seeds)
    sweep_installation(world, seeds)
    marks = content_marks(seeds)
    assert_logs_clean(caplog.records, marks)
    assert_audit_clean(world.env, marks)
    return set(world.hits)


# ------------------------------------------------------------------- pagination boundary cases

TOP = 1 << 128
STEP = 1 << 64
WINDOW = 64 * STEP
SLOTS = 256
RUN_SALT = random.SystemRandom().randrange(
    1 << 20
)  # a random band per process: keys are never reused
_slot = [0]


@contextlib.contextmanager
def planned_ids(model, ids):
    """The next ORM inserts of ``model`` in this process take these primary keys, in order. The
    application code runs in-process under the test client, so a ``before_insert`` listener fixes
    each record's position in the listing's sort order without touching application code."""
    queue = list(ids)

    def assign(mapper, connection, target):
        if queue:
            target.id = queue.pop(0)

    event.listen(model, "before_insert", assign)
    try:
        yield queue
    finally:
        event.remove(model, "before_insert", assign)
    assert not queue, "a planned primary key was not used"


@dataclass
class Scenario:
    name: str
    visible: list  # ints, ascending
    foreign: list  # ints, ascending
    page: int

    def uid(self, number):
        return str(UUID(int=number))

    @property
    def start(self):
        return str(UUID(int=min(self.visible + self.foreign) - 1))


def scenario(adapter, index, name, visible_count):
    """Visible and foreign keys, with foreign keys immediately before and after the keys at both
    sides of the page boundary, before the first record and after the last. Every scenario has its
    own window in a random band at the very top of the key space (a random uuid4 is very unlikely to
    land there, and a retained PostgreSQL database never sees a key twice), and windows rise with
    each scenario of a process, so a listing from a scenario's own first key holds that scenario's
    records only."""
    page = adapter.boundary_page
    _slot[0] += 1
    assert _slot[0] < SLOTS, "more scenarios than window slots in one process"
    base = TOP - (RUN_SALT * SLOTS + (SLOTS - _slot[0])) * WINDOW
    visible = [base + (position + 1) * STEP for position in range(visible_count)]
    last = visible[-1]
    foreign = {visible[0] - 1, last + 1, last + STEP // 2}
    for position in {page - 2, page - 1, page}:
        if 0 <= position < visible_count:
            foreign.update({visible[position] - 1, visible[position] + 1})
    foreign.difference_update(visible)
    return Scenario(name, visible, sorted(foreign), page)


def naive_first_page(sc):
    """What a listing that took the first ``page`` rows of the unfiltered table and filtered
    afterwards would return. The scenario must make that differ from the correct page."""
    union = sorted(sc.visible + sc.foreign)
    return [number for number in union[: sc.page] if number in sc.visible]


def fetch_pages(fetch, start):
    """Follow a listing from ``start``; ``fetch(cursor)`` returns (ids, next_cursor, response)."""
    pages, cursor = [], start
    for _ in range(12):
        ids, following, response = fetch(cursor)
        pages.append((ids, following, response))
        if not following:
            return pages
        cursor = following
    raise AssertionError("pagination did not end")


def verify_pages(sc, pages, expected, where, tail=()):
    """Exact sequence, exact page sizes, a continuation only where more records follow, and no key
    outside ``expected`` (every other visible or foreign key of the scenario) in any page or
    continuation token. ``tail`` holds ids of records above the scenario's window that the actor may
    legitimately see (scope-based surfaces in a database that retains earlier rows)."""
    flat = [identifier for ids, _, _ in pages for identifier in ids]
    assert flat == [sc.uid(n) for n in expected] + list(tail), (
        where,
        "sequence differs from the expected set",
    )
    assert len(flat) == len(set(flat)), (where, "a record is duplicated")
    forbidden = {sc.uid(n) for n in sc.visible + sc.foreign if n not in expected}
    for index, (ids, following, _) in enumerate(pages):
        last = index == len(pages) - 1
        assert bool(following) is (not last), (where, "continuation does not match the visible set")
        if not last:
            assert len(ids) == sc.page, (where, "a non-final page is not full")
            assert not any(f in str(following) for f in forbidden), (
                where,
                "token names a key the actor may not see",
            )
        else:
            assert len(ids) <= sc.page, (where, "final page too long")
            assert ids or len(pages) == 1, (where, "a continuation leads to an empty page")
        assert not (set(ids) & forbidden), (where, "a record the actor may not see is listed")


def expected_for(adapter, kind, sc):
    """The keys ``kind`` may list in the scenario, in order; None where the scope is not granted."""
    layout = adapter.boundary_layout
    if kind in SESSION_DENIED:
        return None
    if layout == "same_scope":  # the peer's records; the owner holds the foreign ones
        return {PEER: sc.visible, OWNER: sc.foreign, ADMIN_SAME: []}.get(kind)
    if layout == "foreign_scope":  # scope-based: every holder of the scope sees the whole scope
        return sc.visible if kind in {PEER, OWNER, ADMIN_SAME} else None
    return sc.visible if kind in SHARED_GRANTED else None  # shared_spread: the shared scope


def listing_scope(adapter):
    return SHARED if adapter.boundary_layout == "shared_spread" else adapter.private_scope


def seed_scenario(world, adapter, sc):
    """Create the visible records and the foreign records, each with its planned key. Returns a
    list of (key, record, is_visible). Layouts: ``same_scope`` (the peer's records are visible, the
    owner's records in the same private scope are foreign), ``foreign_scope`` (foreign records are in
    a scope the peer does not hold) and ``shared_spread`` (visible records are in the shared scope,
    spread over three creators because a creator may hold only ten calendars or routines; foreign
    records are in a scope no shared reader holds)."""
    layout = adapter.boundary_layout
    created = []
    plan = [(n, True) for n in sc.visible] + [(n, False) for n in sc.foreign]
    plan.sort(
        key=lambda item: (item[0] * 2654435761) % (1 << 61)
    )  # a fixed shuffle of creation order
    spread = [OWNER, PEER, READER]
    for number, is_visible in plan:
        if layout == "same_scope":
            kind, scope = (PEER if is_visible else OWNER), adapter.private_scope
        elif layout == "foreign_scope":
            kind = PEER if is_visible else STRANGER
            scope = adapter.private_scope if is_visible else OTHER_PRIVATE
        else:
            kind = spread[sc.visible.index(number) % 3] if is_visible else STRANGER
            scope = SHARED if is_visible else OTHER_PRIVATE
        label = mark(f"{adapter.name[:3]}-bd-")
        with planned_ids(adapter.boundary_model, [UUID(int=number)]):
            row = adapter.create_row(world.actors[kind], scope, label)
        assert row["id"] == sc.uid(number), (adapter.name, "the planned key was not used")
        rec = adapter.rec_from(row, scope, label)
        created.append((number, rec, is_visible))
        if scope == SHARED:
            world.log.append((kind, rec))
            world.shared_records.append((kind, rec))
    return created


def tails(adapter, sc, kind, fetch, cache):
    """Records above the scenario's window that ``kind`` legitimately sees. Per-user surfaces have
    none (the users are new). On a scope-based or shared listing in a database that retains rows of
    earlier runs, a listing from the window's end shows them; it must hold none of this scenario's
    keys, and every actor holding the scope must see the same ones."""
    if adapter.boundary_layout == "same_scope":
        return []
    if not cache:
        end = str(UUID(int=max(sc.visible + sc.foreign)))
        ids, _, _ = fetch_flat(fetch, end)
        cache.append(ids)
    return cache[0]


def fetch_flat(fetch, start):
    pages = fetch_pages(fetch, start)
    return [i for ids, _, _ in pages for i in ids], len(pages), pages


def sweep_boundaries(new_world, adapter, only=None):
    """Page-boundary cases for one listing. ``new_world()`` returns a fresh world; surfaces with a
    per-creator cap get one per scenario. For every actor, the pages are exactly that actor's
    records, in order, while foreign records occupy the keys right around every boundary; foreign,
    replayed and unauthorized cursors release nothing. ``only`` limits the scenarios by name (the
    restricted-PostgreSQL job has a time budget; each scenario creates about thirty records)."""
    if adapter.boundary_model is None:
        return
    page = adapter.boundary_page
    scenarios = [
        scenario(adapter, 0, "exactly one page", page),
        scenario(adapter, 1, "one record over a page", page + 1),
        scenario(adapter, 2, "a short page", min(3, page)),
    ]
    if adapter.boundary_layout == "shared_spread":
        scenarios = scenarios[:2]  # three creators cannot hold more than 30 records
    if only is not None:
        scenarios = [sc for sc in scenarios if sc.name in only]
        assert scenarios, (adapter.name, "no scenario selected")
    scope = listing_scope(adapter)
    world = None
    for sc in scenarios:
        if world is None or adapter.boundary_fresh_world:
            world = new_world()
        where = (adapter.name, sc.name)
        if len(sc.visible) >= page:
            assert naive_first_page(sc) != sc.visible[:page], (
                where, "the scenario would not expose filtering after the limit",
            )  # fmt: skip
        created = seed_scenario(world, adapter, sc)
        shared_tail = []
        numbers = {rec.id: n for n, rec, _ in created}
        every = [rec for _, rec, _ in created]
        issued = {}
        for kind in (PEER, OWNER, ADMIN_SAME, READER):
            expected = expected_for(adapter, kind, sc)
            if expected is None:
                continue
            withheld = [r for r in every if numbers[r.id] not in expected]

            def fetch(
                cursor, caller=world.callers[kind], withheld=withheld, kind=kind, where=where
            ):
                response = adapter.listing(caller, scope, cursor)
                assert response.status_code == 200, (where, kind, response.status_code)
                assert_no_leak(response, withheld, where + (kind,), kind)
                return adapter.ids(response), adapter.cursor(response), response

            tail = tails(adapter, sc, kind, fetch, shared_tail)
            pages = fetch_pages(fetch, sc.start)
            verify_pages(sc, pages, expected, where + (kind,), tail)
            assert len(pages) == max(1, -(-(len(expected) + len(tail)) // page)), (
                where,
                kind,
                "page count",
            )
            issued[kind] = (pages[0][1], fetch, tail)
            if kind == PEER and type(adapter).export is not Adapter.export:
                # The export route pages the same query: the same exact sequence.
                def fetch_export(
                    cursor, caller=world.callers[kind], withheld=withheld, where=where
                ):
                    response = adapter.export(caller, scope, cursor)
                    assert response.status_code == 200, (where, "export", response.status_code)
                    assert_no_leak(response, withheld, where + ("export",), PEER)
                    return adapter.ids(response), adapter.cursor(response), response

                exported = fetch_pages(fetch_export, sc.start)
                verify_pages(sc, exported, expected, where + ("export",), tail)
        # A cursor issued to the peer, replayed by every other holder: only that holder's own
        # records after it, exactly.
        cursor = issued[PEER][0] if PEER in issued else None
        if cursor:
            for kind, (_, fetch, tail) in issued.items():
                after = int(UUID(cursor))
                expected = [n for n in expected_for(adapter, kind, sc) if n > after]
                # The cursor may itself lie in the legitimate tail (a retained database holds enough
                # earlier rows to fill the first page): only the tail records after it are listed.
                later = [i for i in tail if int(UUID(i)) > after]
                verify_pages(
                    sc,
                    fetch_pages(fetch, cursor),
                    expected,
                    where + (kind, "replayed cursor"),
                    later,
                )
        # A cursor that is only the key of a foreign private record: it reveals nothing about it.
        foreign_key = str(UUID(int=sc.foreign[len(sc.foreign) // 2]))
        for kind, (_, fetch, tail) in issued.items():
            expected = [n for n in expected_for(adapter, kind, sc) if n > int(UUID(foreign_key))]
            verify_pages(
                sc, fetch_pages(fetch, foreign_key), expected, where + (kind, "foreign key"), tail
            )
    revoke(world)
    sc = scenarios[0]
    for kind, caller in world.callers.items():
        if expected_for(adapter, kind, sc) is not None and kind != GRANT_REVOKED:
            continue
        response = adapter.listing(caller, scope, sc.start)
        where = (adapter.name, kind, "denied cursor")
        if kind in SESSION_DENIED:
            assert response.status_code == 401, (where, response.status_code)
        elif adapter.scope_denied_list == "empty":
            assert response.status_code == 200 and adapter.ids(response) == [], where
        else:
            assert response.status_code == adapter.scope_denied_list, (where, response.status_code)
        body = text_of(response)
        for number in sc.visible + sc.foreign:
            assert sc.uid(number) not in body, (where, "a record id in a denied response")


configure_boundaries()


INSTALLATION = "/api/v1/installation/"
INSTALLATION_TEMPLATE = {
    "schema_version": 1,
    "defaults": {"languages": ["en", "fr"], "timezone": "UTC"},
}


def sweep_installation(world, seeds):
    """Installation configuration is household-level and technical-administrator only. Nobody else
    reads, previews, exports, applies or reads the history of it, and a refused apply changes
    nothing; the administrator's own read carries no record content."""
    everything = [r for seed_ in seeds for r in seed_.everything]
    admin = world.callers[ADMIN_ONLY]
    current = admin.post(INSTALLATION + "read", {"scope": ADMIN})
    assert current.status_code == 200, current.text[:200]
    record = current.json()["record"]
    binding = {
        "expected_revision": record["revision"],
        "expected_installation_id": record["installation_id"],
    }
    bodies = {
        "read": {},
        "history": {"after": 0},
        "export": {**binding, "acknowledge_copy_limits": True},
        "preview": {**binding, "template": INSTALLATION_TEMPLATE},
        "apply": {
            **binding,
            "template": INSTALLATION_TEMPLATE,
            "preview_token": "0" * 64,
            "expires_at": (identity.now_utc() + timedelta(minutes=5)).isoformat(),
            "confirm": True,
        },
    }
    for kind, caller in world.callers.items():
        for operation, body in bodies.items():
            if kind in {ADMIN_SAME, ADMIN_ONLY} and operation not in {"read", "history"}:
                continue  # an administrator may export, preview and apply; only refusals are exercised
            response = caller.post(INSTALLATION + operation, {"scope": ADMIN, **body})
            where = ("installation", kind, operation)
            if kind in SESSION_DENIED:
                assert response.status_code == 401, (where, response.status_code)
            elif kind in {ADMIN_SAME, ADMIN_ONLY}:
                if operation in {"read", "history"}:
                    assert response.status_code == 200, (where, response.status_code)
                else:
                    continue  # an administrator may export, preview and apply; only refusals are exercised
            else:
                assert response.status_code == 403, (where, response.status_code)
            assert_no_leak(response, everything, where, kind)
    after = admin.post(INSTALLATION + "read", {"scope": ADMIN}).json()["record"]
    assert after == record, "a refused installation request changed the configuration"
