"""Explicit disposable test fixture. Never an inference service or real model."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

if os.environ.get("BUTLER_ENV") != "test":
    raise SystemExit("Synthetic test environment required")
MODEL = "synthetic-citation:fixture"
DIGEST = "1" * 64


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.send(200, {"synthetic": True})
        elif self.path == "/api/tags":
            self.send(200, {"models": [{"name": MODEL, "digest": DIGEST, "size": 1024, "details": {"format": "gguf"}}]})
        else:
            self.send(404, {})

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if self.path != "/api/chat" or not 1 <= size <= 16384:
                return self.send(400, {})
            value = json.loads(self.rfile.read(size))
            if value["model"] != MODEL or value["stream"] is not False or "tools" in value:
                return self.send(400, {})
            envelope = json.loads(value["messages"][1]["content"])
            question = envelope["question"]
            source = envelope["sources"][0]
            status = "conflicting" if "synthetic-conflict" in question else "insufficient" if "synthetic-insufficient" in question else "answer"
            passages = [{"source": 99 if "synthetic-invalid" in question else source["source"], "start_line": source["start_line"], "end_line": source["start_line"]}] if status == "answer" else []
            if "synthetic-unavailable" in question:
                return self.send(503, {})
            self.send(200, {"model": MODEL, "done": True, "done_reason": "stop", "message": {"role": "assistant", "content": json.dumps({"status": status, "passages": passages})}})
        except (ValueError, KeyError, TypeError, IndexError, OSError):
            self.send(400, {})


HTTPServer(("127.0.0.1", 11435), Handler).serve_forever()
