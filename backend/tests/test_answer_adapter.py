"""Bounded synthetic HTTP protocol; never contact an installed model."""

import json

import httpx
import pytest

from app import answer_adapter, local_answer_transport
from app.config import Settings, settings

SOURCE = [{"source": 1, "start_line": 2, "end_line": 2, "text": "TOTAL 123.45"}]
SELECTION = {"status": "answer", "passages": [{"source": 1, "start_line": 2, "end_line": 2}]}


def configured(monkeypatch):
    monkeypatch.setattr(settings, "document_answers_enabled", True)
    monkeypatch.setattr(settings, "document_answer_model", "synthetic-citation:fixture")
    monkeypatch.setattr(settings, "document_answer_digest", "1" * 64)
    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:11435")


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "manifest",
        "drift",
        "duplicate",
        "tools",
        "truncated",
        "large",
        "redirect",
        "timeout",
        "compressed",
        "remote",
        "format",
    ],
)
def test_local_transport_rejects_unsafe_or_incomplete_receipts(monkeypatch, fault):
    configured(monkeypatch)
    calls = []
    real_client = httpx.Client

    def handler(request):
        calls.append(request.url.path)
        if fault == "redirect":
            return httpx.Response(302, headers={"Location": "https://example.invalid"})
        if fault == "timeout":
            raise httpx.ReadTimeout("Synthetic timeout")
        if fault == "large":
            return httpx.Response(200, content=b"x" * 32769)
        if fault == "compressed":
            return httpx.Response(200, headers={"content-encoding": "gzip"}, content=b"synthetic")
        if request.url.path == "/api/tags":
            digest = (
                "0" * 64 if fault == "manifest" or fault == "drift" and len(calls) > 1 else "1" * 64
            )
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": settings.document_answer_model,
                            "digest": digest,
                            "size": 1024,
                            "details": {"format": "remote" if fault == "format" else "gguf"},
                            "remote_host": "https://example.invalid" if fault == "remote" else "",
                        }
                    ]
                },
            )
        payload = json.loads(request.content)
        assert payload["stream"] is False and payload["keep_alive"] == 0
        assert "tools" not in payload and payload["options"]["num_predict"] == 256
        envelope = json.loads(payload["messages"][1]["content"])
        assert set(envelope) == {"question", "language", "sources"}
        assert set(envelope["sources"][0]) == {"source", "start_line", "end_line", "text"}
        content = (
            '{"status":"answer","status":"answer","passages":[]}'
            if fault == "duplicate"
            else json.dumps(SELECTION)
        )
        message = {"role": "assistant", "content": content}
        if fault == "tools":
            message["tool_calls"] = [{"name": "do_something"}]
        return httpx.Response(
            200,
            json={
                "model": settings.document_answer_model,
                "done": True,
                "done_reason": "length" if fault == "truncated" else "stop",
                "message": message,
            },
        )

    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(local_answer_transport.httpx, "Client", client)
    result = local_answer_transport.select_passages(
        "What is total?",
        "en",
        SOURCE,
        settings.ollama_url,
        settings.document_answer_model,
        settings.document_answer_digest,
    )
    assert result["status"] == ("selected" if fault == "none" else "unavailable")
    assert calls.count("/api/chat") <= 1
    if fault == "none":
        assert calls == ["/api/tags", "/api/chat", "/api/tags"]
        assert result["selection"] == SELECTION


def test_disabled_transport_does_not_open_a_client(monkeypatch):
    monkeypatch.setattr(
        local_answer_transport.httpx,
        "Client",
        lambda **kwargs: pytest.fail("Disabled transport reached"),
    )
    assert answer_adapter.select_passages("Synthetic", "en", SOURCE)["invoked"] is False


def test_enabled_adapter_requires_explicit_model_and_manifest():
    with pytest.raises(ValueError):
        Settings(
            postgres_password="synthetic-password-only-0123456789", document_answers_enabled=True
        )
    with pytest.raises(ValueError):
        Settings(
            postgres_password="synthetic-password-only-0123456789",
            document_answer_model="implicit-model",
        )


@pytest.mark.parametrize("timeout,dispatched", [(False, True), (True, False), (True, True)])
def test_process_deadline_kills_transport_and_never_inherits_secrets(
    monkeypatch, timeout, dispatched
):
    configured(monkeypatch)
    calls = []

    class Child:
        returncode = 0
        killed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def kill(self):
            self.killed = True

        def communicate(self, input=None, timeout=None):
            if input is not None:
                body = json.loads(input)
                assert set(body["sources"][0]) == {"source", "start_line", "end_line", "text"}
                assert answer_adapter.select_passages("Nested", "en", SOURCE)["invoked"] is False
                if timeout_case:
                    raise answer_adapter.subprocess.TimeoutExpired("fixed transport", timeout)
            outcome = {"status": "selected", "invoked": dispatched, "selection": SELECTION}
            return (b"D\n" if dispatched else b"") + json.dumps(outcome).encode(), None

    timeout_case = timeout
    child = Child()

    def popen(args, **kwargs):
        calls.append(args)
        assert args[1:] == ["-m", "app.local_answer_transport"]
        assert set(kwargs["env"]) == {"PYTHONDONTWRITEBYTECODE", "LANG"}
        assert kwargs["close_fds"] is True and kwargs["start_new_session"] is True
        return child

    monkeypatch.setattr(answer_adapter.subprocess, "Popen", popen)
    result = answer_adapter.select_passages(
        "TOTAL", "en", [{**SOURCE[0], "document": {"private": "not needed by model"}}]
    )
    assert len(calls) == 1 and child.killed is timeout
    assert result["invoked"] is dispatched
    assert result["status"] == ("unavailable" if timeout else "selected")
