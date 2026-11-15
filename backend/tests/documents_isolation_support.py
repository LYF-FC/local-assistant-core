"""Shared behavior for the document and document-answer isolation tests.

Contracts the tests are derived from (they add no permission rule):

* docs/DOCUMENT_LIBRARY.md: household members read current shared documents and originals; only
  the creator can correct, replace, inspect history or previous originals, and forget; private
  documents stay creator-only even for another person holding the same private scope; technical
  administration provides no content grant; membership, active account, live session, CSRF and
  Origin are checked on each operation.
* docs/DOCUMENT_ANSWERS.md: only current active reviewed documents from one selected scope are
  eligible; private records stay creator-only even for a member with the same scope; technical
  administration adds no content access.
* docs/MVP_ACCEPTANCE.md, Gate 1: another adult, a revoked user and an administrator must not
  retrieve private content through IDs, search, answers, citations, exports or history.

Endpoint behavior the expectations rely on (documents.authority / documents.operate):
401 for a missing, unknown or revoked session; 403 when the requested scope is not granted; 404
when the record is not visible in a granted scope; 403 when a non-owner asks for an owner-only
operation (history, previous original, write) on a visible shared record. Foreign-ID responses
are deliberately not compared with random-UUID responses: neither contract requires equivalent
denial for documents, only that no content is released.

The same behavior runs twice, from the SQLite module and from the restricted PostgreSQL module.
Only the environment differs. Privileged sessions provision users and change grants; every
request under test goes through a client built by ``open_client``. For PostgreSQL that client's
database session is bound to the restricted runtime role engine. These tests do not prove timing
or side-channel properties and exercise only the pages and actors listed below.
"""

import base64
import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from conftest import SYNTHETIC_PASSWORD, client_for
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from test_document_answers import ask, enabled
from test_documents import call, query, upload

from app import answer_adapter, identity
from app.main import app
from app.manage import provision, set_scope
from app.models import User

ORIGIN = "https://localhost:8443"
SHARED = "household_shared"
PRIVATE = "member_a_private"
OTHER_PRIVATE = "member_b_private"
ADMIN = "technical_admin"

PRIVATE_OPERATIONS = ("read", "original", "original_v1", "excerpt", "history", "query", "export")


@dataclass
class Actor:
    name: str
    slug: str
    user_id: UUID
    client: object
    headers: dict
    token: str


class Environment:
    """Privileged provisioning plus the client factory for requests under test."""

    def __init__(self, label, provisioner, open_client):
        self.label = label
        self.provisioner = provisioner
        self.open_client = open_client
        self.shared = []

    def track(self, owner, doc):
        """Remember a shared document so cleanup can forget it (see ``cleanup``)."""
        self.shared.append((owner, doc))

    def cleanup(self):
        """Forget every shared document a test created.

        The disposable PostgreSQL database keeps committed rows for the rest of the run, and other
        modules assume the shared scope holds no active reviewed documents. Forgetting through the
        owner's own session leaves only a tombstone, which queries and answers never return.
        """
        for owner, doc in self.shared:
            current = call(owner.client, owner.headers, doc.row, "read")
            assert current.status_code == 200, current.text[:200]
            forgotten = call(owner.client, owner.headers, current.json(), "forget")
            assert forgotten.status_code == 200, forgotten.text[:200]

    def actor(self, name, scopes):
        slug = f"iso-{name}-{uuid4().hex[:10]}".replace("_", "-")
        with self.provisioner.begin() as db:
            user = provision(db, slug, "Synthetic isolation actor", SYNTHETIC_PASSWORD, set(scopes))
            user_id = user.id
        client = self.open_client()
        login = client.post(
            "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
        )
        assert login.status_code == 200, login.text
        token = client.cookies.get(identity.COOKIE)
        assert token
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        return Actor(name, slug, user_id, client, headers, token)

    def grant(self, actor, scope, granted):
        with self.provisioner.begin() as db:
            set_scope(db, db.get(User, actor.user_id), scope, granted)


def sqlite_environment(store, stack):
    def open_client():
        return stack.enter_context(
            TestClient(
                app,
                base_url=ORIGIN,
                headers={"Origin": ORIGIN},
                client=("synthetic-" + uuid4().hex, 50000),
            )
        )

    return Environment("sqlite", store, open_client)


def postgres_environment(admin, runtime_engine, stack):
    runtime = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    return Environment("postgres-runtime", admin, lambda: stack.enter_context(client_for(runtime)))


def b64(text):
    return base64.b64encode(text.encode()).decode()


def new_mark(label):
    return label + uuid4().hex[:12]


@dataclass
class Doc:
    row: dict
    mark: str
    text: str

    @property
    def id(self):
        return self.row["id"]

    @property
    def needles(self):
        """Values that must never appear in a response meant to withhold this document."""
        return (self.mark, self.id, self.row["sha256"], b64(self.text))


def create(actor, scope, mark, extra="", reviewed=True):
    """A synthetic document carrying a unique marker in its title, filename, reference and text."""
    text = f"Synthetic isolation record {mark}\nREF {mark} value 100\n{extra}"
    response = upload(
        actor.client,
        actor.headers,
        scope=scope,
        title=f"Doc {mark}",
        filename=f"{mark}.md",
        source_reference=f"Ref {mark}",
        original_base64=b64(text),
    )
    assert response.status_code == 201, response.text
    row = response.json()
    if reviewed:
        done = call(
            actor.client,
            actor.headers,
            row,
            "correct",
            title=f"Doc {mark}",
            source_reference=f"Ref {mark}",
        )
        assert done.status_code == 200, done.text
        row = done.json()
        assert row["reviewed"] and row["revision"] == 2
    return Doc(row, mark, text)


def perform(actor, operation, doc, headers=None):
    h = actor.headers if headers is None else headers
    c, row = actor.client, doc.row
    if operation == "read":
        return call(c, h, row, "read")
    if operation == "original":
        return call(c, h, row, "original")
    if operation == "original_v1":
        return call(c, h, row, "original", version=1)
    if operation == "excerpt":
        return call(c, h, row, "excerpt", start_line=1, end_line=2)
    if operation == "history":
        return call(c, h, row, "history")
    if operation == "query":
        return query(c, h, scope=row["scope"], search=doc.mark)
    if operation == "export":
        return c.post(
            "/api/v1/documents/export",
            headers=h,
            json={"scope": row["scope"], "search": doc.mark, "acknowledge_copy_limits": True},
        )
    if operation == "correct":
        return call(c, h, row, "correct", title="Synthetic hijacked title")
    if operation == "replace":
        return call(c, h, row, "replace", filename="swap.md", original_base64=b64("swap"))
    if operation == "forget":
        return call(c, h, row, "forget")
    raise AssertionError(operation)


def listed(response):
    return [item["id"] for item in response.json()["items"]]


def body_text(response):
    """Response text without the ``filters`` echo: a listing repeats the caller's own search term."""
    try:
        value = response.json()
    except ValueError:
        return response.text
    if isinstance(value, dict):
        value = {key: item for key, item in value.items() if key != "filters"}
    return json.dumps(value)


def assert_withheld(response, docs, status=None):
    assert status is None or response.status_code == status, (
        response.status_code,
        response.text[:200],
    )
    text = body_text(response)
    for doc in docs:
        for needle in doc.needles:
            assert needle not in text, (doc.mark, "released")


def assert_released(operation, response, doc):
    assert response.status_code == 200, (operation, response.status_code, response.text[:200])
    if operation == "read":
        assert response.json()["id"] == doc.id and doc.mark in response.text
    elif operation in {"original", "original_v1"}:
        assert base64.b64decode(response.json()["original_base64"]) == doc.text.encode()
    elif operation == "excerpt":
        assert doc.mark in response.json()["excerpt"]
    elif operation == "history":
        assert [x["operation"] for x in response.json()["items"]] == ["uploaded", "corrected"]
    elif operation in {"query", "export"}:
        assert listed(response) == [doc.id]


def assert_outcome(operation, response, doc, expected):
    """``expected`` is "released", an HTTP status, or "empty" (200 listing without the document)."""
    if expected == "released":
        assert_released(operation, response, doc)
    elif expected == "empty":
        assert response.status_code == 200 and listed(response) == []
        assert_withheld(response, [doc])
    else:
        assert_withheld(response, [doc], status=expected)


def private_expectations(actor_name):
    """Expected outcome per operation for the owner's private document (scope member_a_private)."""
    if actor_name == "owner":
        return {op: "released" for op in PRIVATE_OPERATIONS}
    if actor_name in {"peer", "admin_same"}:  # same private grant, not the creator
        return {
            **{op: 404 for op in PRIVATE_OPERATIONS},
            "query": "empty",
            "export": "empty",
        }
    return {op: 403 for op in PRIVATE_OPERATIONS}  # scope not granted


def shared_expectations(actor_name):
    """Expected outcome per operation for the owner's shared document (scope household_shared)."""
    if actor_name == "owner":
        return {op: "released" for op in PRIVATE_OPERATIONS}
    if actor_name in {"peer", "reader"}:  # granted shared readers
        return {
            "read": "released",
            "original": "released",
            "original_v1": 403,
            "excerpt": "released",
            "history": 403,
            "query": "released",
            "export": "released",
        }
    return {op: 403 for op in PRIVATE_OPERATIONS}  # shared scope not granted


def standard_actors(env):
    return {
        "owner": env.actor("owner", {SHARED, PRIVATE}),
        "peer": env.actor("peer", {SHARED, PRIVATE}),
        "admin_same": env.actor("admin-same", {ADMIN, PRIVATE}),
        "admin_only": env.actor("admin-only", {ADMIN}),
        "reader": env.actor("reader", {SHARED}),
        "stranger": env.actor("stranger", {OTHER_PRIVATE}),
    }


def behave_private_document_operations(env):
    actors = standard_actors(env)
    owner, peer = actors["owner"], actors["peer"]
    mine = create(owner, PRIVATE, new_mark("own"))
    theirs = create(peer, PRIVATE, new_mark("peer"))
    for name, actor in actors.items():
        expected = private_expectations(name)
        for operation in PRIVATE_OPERATIONS:
            response = perform(actor, operation, mine)
            assert_outcome(operation, response, mine, expected[operation])
    # Bidirectional control: the other adult's own document is released to them and withheld
    # from the owner, so the denials above are not an artefact of the owner's data.
    for operation in PRIVATE_OPERATIONS:
        assert_released(operation, perform(peer, operation, theirs), theirs)
        assert_outcome(
            operation,
            perform(owner, operation, theirs),
            theirs,
            private_expectations("peer")[operation],
        )


def behave_shared_document_operations(env):
    actors = standard_actors(env)
    owner = actors["owner"]
    shared = create(owner, SHARED, new_mark("shr"))
    env.track(owner, shared)
    for name, actor in actors.items():
        expected = shared_expectations(name)
        for operation in PRIVATE_OPERATIONS:
            response = perform(actor, operation, shared)
            assert_outcome(operation, response, shared, expected[operation])
    # Owner-only writes are refused for granted shared readers and change nothing.
    for name in ("peer", "reader"):
        for operation in ("correct", "replace", "forget"):
            assert perform(actors[name], operation, shared).status_code == 403
    current = perform(owner, "read", shared)
    assert current.status_code == 200
    assert current.json()["revision"] == 2 and current.json()["state"] == "active"
    assert current.json()["title"] == f"Doc {shared.mark}"


def walk(actor, route, scope, tag):
    ids, sizes, after = [], [], None
    for _ in range(4):
        body = {"scope": scope, "search": tag, "reviewed_only": False}
        if route == "export":
            body["acknowledge_copy_limits"] = True
        if after:
            body["after"] = after
        response = actor.client.post(f"/api/v1/documents/{route}", headers=actor.headers, json=body)
        assert response.status_code == 200, response.text[:200]
        data = response.json()
        ids += [item["id"] for item in data["items"]]
        sizes.append(len(data["items"]))
        after = data["next_cursor"]
        if not after:
            return ids, sizes
    raise AssertionError("unexpected number of pages")


def behave_pagination_and_export(env):
    actors = standard_actors(env)
    owner, peer, admin = actors["owner"], actors["peer"], actors["admin_same"]
    tag = new_mark("pg")
    owned = [create(owner, PRIVATE, f"{tag}o{i:02d}", reviewed=False) for i in range(26)]
    peers = [create(peer, PRIVATE, f"{tag}p{i}", reviewed=False) for i in range(3)]
    for route in ("query", "export"):
        owner_ids, owner_sizes = walk(owner, route, PRIVATE, tag)
        assert owner_sizes == [25, 1] and sorted(owner_ids) == sorted(d.id for d in owned)
        peer_ids, peer_sizes = walk(peer, route, PRIVATE, tag)
        assert peer_sizes == [3] and sorted(peer_ids) == sorted(d.id for d in peers)
        assert not set(owner_ids) & set(peer_ids)
        assert walk(admin, route, PRIVATE, tag) == ([], [0])
        for stranger in ("reader", "admin_only", "stranger"):
            response = actors[stranger].client.post(
                f"/api/v1/documents/{route}",
                headers=actors[stranger].headers,
                json={
                    "scope": PRIVATE,
                    "search": tag,
                    "reviewed_only": False,
                    **({"acknowledge_copy_limits": True} if route == "export" else {}),
                },
            )
            assert_withheld(response, owned + peers, status=403)


class Selector:
    """Synthetic answer adapter: records what it was handed and cites the first source."""

    def __init__(self):
        self.calls = []

    def __call__(self, question, language, sources):
        self.calls.append([source["document"]["id"] for source in sources])
        first = sources[0]["start_line"]
        return {
            "status": "selected",
            "invoked": True,
            "selection": {
                "status": "answer",
                "passages": [{"source": 1, "start_line": first, "end_line": first}],
            },
        }


def question(*marks):
    return "What is " + " ".join(marks) + "?"


def install_selector(monkeypatch):
    enabled(monkeypatch)
    selector = Selector()
    monkeypatch.setattr(answer_adapter, "select_passages", selector)
    return selector


def source_ids(response):
    return [item["document"]["id"] for item in response.json()["sources"]]


def passage_ids(response):
    return [item["document"]["id"] for item in response.json()["passages"]]


def behave_answers(env, monkeypatch):
    selector = install_selector(monkeypatch)
    actors = standard_actors(env)
    owner, peer = actors["owner"], actors["peer"]
    shared_mark = new_mark("sh")
    owner_only = create(owner, PRIVATE, new_mark("fo"))
    # A foreign-only matching source: the question matches nothing but the owner's document.
    own_answer = ask(owner.client, owner.headers, scope=PRIVATE, question=question(owner_only.mark))
    assert own_answer.status_code == 200 and own_answer.json()["status"] == "answered"
    assert source_ids(own_answer) == [owner_only.id] == passage_ids(own_answer)
    assert owner_only.mark in own_answer.json()["passages"][0]["text"]
    assert selector.calls == [[owner_only.id]]
    selector.calls.clear()
    for name in ("peer", "admin_same"):  # same private grant, not the creator
        actor = actors[name]
        response = ask(
            actor.client, actor.headers, scope=PRIVATE, question=question(owner_only.mark)
        )
        assert response.status_code == 200 and response.json()["status"] == "no_sources"
        assert response.json()["sources"] == [] and response.json()["passages"] == []
        assert not response.json()["model_invoked"]
        assert_withheld(response, [owner_only])
    assert selector.calls == []  # nothing foreign reached the adapter
    for name in ("reader", "admin_only", "stranger"):  # private scope not granted
        actor = actors[name]
        response = ask(
            actor.client, actor.headers, scope=PRIVATE, question=question(owner_only.mark)
        )
        assert_withheld(response, [owner_only], status=403)
    # A mixed matching case: the owner's document outranks the peer's (two question terms versus
    # one), yet the peer's answer cites only the peer's own document.
    extra = new_mark("xt")
    foreign = create(owner, PRIVATE, new_mark("fm"), extra=f"shared {extra}\n")
    mine = create(peer, PRIVATE, new_mark("pm"), extra=f"shared {extra}\n")
    both = question(foreign.mark, extra)
    owner_view = ask(owner.client, owner.headers, scope=PRIVATE, question=both)
    assert owner_view.json()["status"] == "answered"
    assert source_ids(owner_view)[0] == foreign.id  # ranking really favours the foreign source
    assert mine.id not in source_ids(owner_view)
    selector.calls.clear()
    peer_view = ask(peer.client, peer.headers, scope=PRIVATE, question=both)
    assert peer_view.status_code == 200 and peer_view.json()["status"] == "answered"
    assert source_ids(peer_view) == [mine.id] == passage_ids(peer_view)
    assert mine.mark in peer_view.json()["passages"][0]["document"]["title"]
    assert selector.calls == [[mine.id]]
    assert_withheld(peer_view, [foreign, owner_only])
    # Shared scope: a granted shared reader gets the shared source; a member holding both grants
    # gets nothing from the owner's private scope when asking in the shared scope.
    shared = create(owner, SHARED, shared_mark)
    env.track(owner, shared)
    reader = actors["reader"]
    cited = ask(reader.client, reader.headers, scope=SHARED, question=question(shared_mark))
    assert cited.json()["status"] == "answered"
    assert source_ids(cited) == [shared.id] == passage_ids(cited)
    assert cited.json()["sources"][0]["document"]["can_edit"] is False
    selector.calls.clear()
    bleed = ask(peer.client, peer.headers, scope=SHARED, question=question(owner_only.mark))
    assert bleed.json()["status"] == "no_sources" and selector.calls == []
    assert_withheld(bleed, [owner_only, foreign])
    for name in ("admin_same", "admin_only", "stranger"):  # shared scope not granted
        actor = actors[name]
        response = ask(actor.client, actor.headers, scope=SHARED, question=question(shared_mark))
        assert_withheld(response, [shared], status=403)


ALL_OPERATIONS = PRIVATE_OPERATIONS + ("ask",)


def attempt(actor, operation, doc, headers=None):
    if operation == "ask":
        h = actor.headers if headers is None else headers
        return ask(actor.client, h, scope=doc.row["scope"], question=question(doc.mark))
    return perform(actor, operation, doc, headers)


def behave_grant_revocation(env, monkeypatch):
    install_selector(monkeypatch)
    actors = standard_actors(env)
    owner, peer, reader = actors["owner"], actors["peer"], actors["reader"]
    owned = create(owner, PRIVATE, new_mark("go"))
    theirs = create(peer, PRIVATE, new_mark("gp"))
    shared = create(owner, SHARED, new_mark("gs"))
    env.track(owner, shared)
    for operation in ALL_OPERATIONS:  # authorized before any revocation
        response = attempt(peer, operation, theirs)
        assert response.status_code == 200, (operation, response.text[:200])
    assert attempt(reader, "read", shared).status_code == 200
    # Revoke the private grant; the session stays valid and the shared grant is untouched.
    env.grant(peer, PRIVATE, False)
    for operation in ALL_OPERATIONS:
        assert_withheld(attempt(peer, operation, theirs), [theirs, owned], status=403)
        assert_withheld(attempt(peer, operation, owned), [theirs, owned], status=403)
    assert attempt(peer, "read", shared).status_code == 200  # same session, shared grant intact
    # Revoke the shared grant of the shared reader.
    env.grant(reader, SHARED, False)
    for operation in ALL_OPERATIONS:
        assert_withheld(attempt(reader, operation, shared), [shared], status=403)
    # Restoring the grant restores access, so the denial was caused by the grant, not the session.
    env.grant(peer, PRIVATE, True)
    assert attempt(peer, "read", theirs).status_code == 200
    assert_withheld(attempt(peer, "read", owned), [owned], status=404)


def behave_session_revocation(env, monkeypatch):
    install_selector(monkeypatch)
    actors = standard_actors(env)
    owner, peer, reader = actors["owner"], actors["peer"], actors["reader"]
    theirs = create(peer, PRIVATE, new_mark("sp"))
    shared = create(owner, SHARED, new_mark("ss"))
    env.track(owner, shared)
    for operation in ALL_OPERATIONS:  # the retained session is genuinely valid first
        assert attempt(peer, operation, theirs).status_code == 200, operation
        if operation not in {"history", "original_v1"}:
            assert attempt(peer, operation, shared).status_code == 200, operation
    retained = {**peer.headers, "Cookie": f"{identity.COOKIE}={peer.token}"}
    # Revoke that session through the supported logout; nothing else about the account changes.
    logout = peer.client.post("/api/v1/auth/logout", headers=peer.headers, json={})
    assert logout.status_code == 200
    for operation in ALL_OPERATIONS:
        for doc in (theirs, shared):
            response = attempt(peer, operation, doc, headers=retained)
            assert_withheld(response, [theirs, shared], status=401)
    # Controls: the account and grants are intact (a fresh login works), and other sessions are
    # unaffected. Session revocation is not user disablement and not grant revocation.
    login = peer.client.post(
        "/api/v1/auth/login", json={"slug": peer.slug, "password": SYNTHETIC_PASSWORD}
    )
    assert login.status_code == 200
    fresh = {"X-CSRF-Token": login.json()["csrf_token"]}
    assert perform(peer, "read", theirs, headers=fresh).status_code == 200
    assert perform(owner, "read", shared).status_code == 200
    assert perform(reader, "read", shared).status_code == 200
