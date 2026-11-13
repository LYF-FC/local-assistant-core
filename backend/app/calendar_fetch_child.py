"""One bounded provider call in a fresh interpreter (run as a script by ``calendar_sync.fetch``).

This is the only place provider code runs. It is started with exec (never forked from the API or
worker process), so it inherits no lock, thread, database connection or secret from its parent.
It reads one JSON request from stdin, makes one ``changes`` call and writes one JSON answer to
stdout; the parent enforces the deadline with SIGKILL, and this process also arms its own alarm so
it ends itself shortly after the timeout even if its parent has died.

It imports only the standard library, ``calendar_codes`` and ``calendar_provider`` (neither
imports settings, a database driver or any network library).
"""

import json
import math
import os
import signal
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.append(ROOT)  # appended: the standard library always wins over a same-named module

REQUEST_BYTES_MAX = 65536


def answer(payload):
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    sys.stdout.buffer.flush()
    os._exit(0)


def read_request():
    request = json.loads(sys.stdin.buffer.read(REQUEST_BYTES_MAX))
    keys = {"directory", "ref", "since", "limit", "timeout"}
    well_formed = (
        isinstance(request, dict)
        and set(request) == keys
        and isinstance(request["directory"], str)
        and isinstance(request["ref"], str)
        and (request["since"] is None or isinstance(request["since"], str))
        and type(request["limit"]) is int
        and type(request["timeout"]) in (int, float)
        and 0 < request["timeout"] < 3600
    )
    if not well_formed:
        raise ValueError("unexpected request")
    return request


def main():
    try:
        request = read_request()
        signal.alarm(max(1, math.ceil(request["timeout"]) + 1))
        from app import calendar_provider as provider_module

        try:
            provider = provider_module.SyntheticProvider(request["directory"], request["ref"])
            page = provider.changes(request["since"], request["limit"])
        except provider_module.MalformedItem as error:
            answer({"error": {"kind": "MalformedItem", "index": error.index}})
        except provider_module.ProviderError as error:
            answer({"error": {"kind": type(error).__name__}})
        answer(
            {
                "ok": {
                    "items": [
                        {
                            "entity": item.entity,
                            "operation": item.operation,
                            "uid": item.uid,
                            "sequence": item.sequence,
                            "recurrence_id": item.recurrence_id,
                            "body": item.body,
                        }
                        for item in page.items
                    ],
                    "next_cursor": page.next_cursor,
                    "has_more": page.has_more,
                }
            }
        )
    except BaseException:  # noqa: BLE001 - whatever happens, the parent gets a typed answer
        answer({"error": {"kind": "ProviderUnavailable"}})


if __name__ == "__main__":
    main()
