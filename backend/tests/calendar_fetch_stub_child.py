"""A scripted stand-in for the fetch child, selected by ``calendar_sync.CHILD_ARGV`` in tests.

Run as ``python -I -S calendar_fetch_stub_child.py <scenario> [path]``. It speaks the same JSON
protocol as the real child (or deliberately breaks it) so the parent's guarantees can be proven
against any child behaviour: hanging, ignoring SIGTERM, starting grandchildren, garbage output.
"""

import json
import os
import signal
import subprocess
import sys
import time

scenario = sys.argv[1]
target = sys.argv[2] if len(sys.argv) > 2 else None
sys.stdin.buffer.read()


def say(payload):
    sys.stdout.buffer.write(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
    sys.stdout.buffer.flush()


def page(cursor, has_more=False, items=()):
    return {"ok": {"items": list(items), "next_cursor": cursor, "has_more": has_more}}


if scenario == "hang":  # ignores SIGTERM, records its pid and a grandchild's, never answers
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    with open(target, "w") as handle:
        handle.write(f"{os.getpid()} {grandchild.pid}")
    time.sleep(120)
elif scenario == "environment":
    with open(target, "w") as handle:
        handle.write(json.dumps({"env": dict(os.environ), "cwd": os.getcwd()}))
    say(page("v1:0"))
elif scenario == "same_cursor":  # a page that never progresses
    say(page("v1:0", has_more=True))
elif scenario == "garbage":
    say(b"not json {")
elif scenario == "huge":
    say(b'{"ok":"' + b"x" * (10 * 1024 * 1024) + b'"}')
elif scenario == "empty_exit":
    sys.exit(3)
elif scenario == "wrong_shape":
    say({"ok": {"items": [{"entity": "series"}], "next_cursor": "v1:0", "has_more": False}})
elif scenario == "extra_keys":
    say({"ok": {"items": [], "next_cursor": "v1:0", "has_more": False}, "error": {}})
elif scenario.startswith("error:"):
    say({"error": {"kind": scenario.split(":", 1)[1], "index": 4}})
elif scenario == "ok":
    item = {
        "entity": "series",
        "operation": "delete",
        "uid": "u",
        "sequence": 2,
        "recurrence_id": None,
        "body": None,
    }
    say(page("v1:9", items=[item]))
else:
    raise SystemExit(f"unknown scenario {scenario}")
