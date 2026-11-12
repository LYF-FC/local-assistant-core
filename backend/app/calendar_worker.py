"""Restricted calendar provider sync worker; synthetic fixtures only.

Runs one bounded pass (``--once``) or loops with a pause (``--loop``). Each source is claimed,
fetched outside any transaction and applied atomically by ``calendar_sync``. The worker exists
only in development and test with restricted runtime credentials and a configured synthetic
fixture directory; it has no network access and no write path to any provider.
"""

import argparse
import time

from app import calendar_sync
from app.config import settings

PAUSE_SECONDS = 30


def check_environment():
    if settings.env not in {"development", "test"} or settings.postgres_user != "butler_runtime":
        raise RuntimeError(
            "Calendar worker requires development/test restricted runtime credentials"
        )
    if settings.env == "test" and not settings.postgres_db.startswith("butler_test"):
        raise RuntimeError("Disposable test database required")
    if settings.calendar_synthetic_directory is None:
        raise RuntimeError("A synthetic calendar fixture directory is required")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Restricted calendar sync worker; synthetic fixtures only, no network"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true")
    group.add_argument("--loop", action="store_true")
    args = parser.parse_args(argv)
    check_environment()
    while True:
        result = calendar_sync.run_pass()
        print(
            "Synthetic calendar pass: " + ", ".join(f"{k}={v}" for k, v in result.items()),
            flush=True,
        )
        if args.once:
            if result.get("errors"):
                raise SystemExit(1)
            return
        time.sleep(PAUSE_SECONDS)


if __name__ == "__main__":
    main()
