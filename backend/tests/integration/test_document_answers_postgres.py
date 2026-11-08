"""Real committed audit, current authority and source locking across local selection."""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_approvals import signin
from test_document_answers import answer_lifecycle, ask, enabled, reviewed, selection
from test_documents import call

from app import answer_adapter, answer_routes, documents, identity
from app.manage import set_scope
from app.models import AuditEvent, AuthSession, DocumentRecord, DocumentVersion, User

pytestmark = pytest.mark.integration


def test_restricted_answer_lifecycle(scenario, monkeypatch):
    client, h, _, _, _ = scenario
    answer_lifecycle(client, h, monkeypatch)


def test_preparation_audit_is_committed_and_source_locked_before_model(scenario, monkeypatch):
    client, h, _, admin, owner = scenario
    row = reviewed(client, h)
    enabled(monkeypatch)

    def model(*args):
        with admin() as db:
            assert (
                db.scalar(
                    select(AuditEvent.id).where(
                        AuditEvent.initiator_id == str(owner),
                        AuditEvent.event_type == "answers.prepared",
                    )
                )
                is not None
            )
        with admin() as db:
            prepared = db.scalar(
                select(AuditEvent).where(
                    AuditEvent.initiator_id == str(owner),
                    AuditEvent.event_type == "answers.prepared",
                )
            )
            assert prepared.metadata_json["sources"][0]["start_line"] == 2
            assert prepared.metadata_json["sources"][0]["end_line"] == 3
            assert prepared.metadata_json["model"] == "synthetic-citation:fixture"
            assert prepared.metadata_json["digest"] == "1" * 64
        with admin.begin() as db, pytest.raises(DBAPIError):
            db.execute(text("SET LOCAL lock_timeout='150ms'"))
            db.execute(
                text("UPDATE document_records SET revision=revision+1 WHERE id=:id"),
                {"id": UUID(row["id"])},
            )
        return selection(*args)

    monkeypatch.setattr(answer_adapter, "select_passages", model)
    assert ask(client, h).json()["status"] == "answered"
    assert call(client, h, row, "forget").status_code == 200


@pytest.mark.parametrize("fault", ["revision", "grant", "session"])
def test_reauthorization_after_committed_preparation_prevents_stale_dispatch(
    scenario, monkeypatch, fault
):
    client, h, _, admin, owner = scenario
    row = reviewed(client, h)
    enabled(monkeypatch)
    original = answer_routes.run
    mutated = False

    def boundary(db, request, operation, unsafe=False):
        nonlocal mutated
        result = original(db, request, operation, unsafe)
        if result.payload.get("status") == "prepared" and not mutated:
            mutated = True
            with admin.begin() as writer:
                user = writer.get(User, owner)
                if fault == "grant":
                    set_scope(writer, user, "household_shared", False)
                elif fault == "session":
                    for session in writer.scalars(
                        select(AuthSession).where(AuthSession.user_id == owner)
                    ):
                        session.expires_at = identity.now_utc() - timedelta(seconds=1)
                else:
                    record = writer.get(DocumentRecord, UUID(row["id"]))
                    raw = writer.scalar(
                        select(DocumentVersion.original_bytes).where(
                            DocumentVersion.document_id == record.id,
                            DocumentVersion.revision == record.revision,
                        )
                    )
                    record.title = "Synthetic corrected source"
                    record.revision += 1
                    record.updated_at = identity.now_utc()
                    writer.flush()
                    documents.snapshot(writer, user, record, "corrected", raw)
                    documents.audit(writer, user, record, "corrected")
        return result

    monkeypatch.setattr(answer_routes, "run", boundary)
    monkeypatch.setattr(
        answer_adapter,
        "select_passages",
        lambda *args: pytest.fail("Stale/revoked input dispatched"),
    )
    assert ask(client, h).status_code == {"revision": 409, "grant": 403, "session": 401}[fault]
    monkeypatch.setattr(answer_routes, "run", original)
    with admin.begin() as db:
        user = db.get(User, owner)
        slug = user.slug
        if fault == "grant":
            set_scope(db, user, "household_shared", True)
    if fault == "session":
        h = signin(client, slug)
    current = call(client, h, row, "read").json()
    assert call(client, h, current, "forget").status_code == 200


def test_real_local_http_slow_headers_have_a_hard_deadline(scenario, monkeypatch):
    import json
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Event, Thread

    from app.config import settings

    client, h, _, _, _ = scenario
    row = reviewed(client, h)
    enabled(monkeypatch)
    stop = Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):
            body = json.dumps(
                {
                    "models": [
                        {
                            "name": settings.document_answer_model,
                            "digest": "1" * 64,
                            "size": 1024,
                            "details": {"format": "gguf"},
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            assert "cookie" not in self.headers and "X-CSRF-Token" not in self.headers
            self.rfile.read(int(self.headers["Content-Length"]))
            # Trickle incomplete headers below socket timeouts; only the parent
            # process deadline can enforce the whole-request bound.
            self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Synthetic: ")
            self.wfile.flush()
            for _ in range(40):
                if stop.wait(0.5):
                    break
                try:
                    self.wfile.write(b"x")
                    self.wfile.flush()
                except OSError:
                    break

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "ollama_url", f"http://127.0.0.1:{server.server_port}")
    started = time.monotonic()
    try:
        value = ask(client, h).json()
        assert value["status"] == "unavailable" and not value["passages"]
        assert value["model_invoked"] is True
        assert 11 <= time.monotonic() - started < 16
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert call(client, h, row, "forget").status_code == 200
