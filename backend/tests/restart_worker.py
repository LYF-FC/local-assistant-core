"""Child entry point of the process-restart harness (test infrastructure only).

Runs the real `process()` function of the filing or notification worker for one row, against a
persistent synthetic ledger. At the requested crash point it announces itself and blocks until
the parent either kills it or releases it.
"""

import json
import sys
from uuid import UUID

from restart_support import FileChannel, FileDestination
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import FilingExecution, NotificationDelivery


def rendezvous(point):
    def hook(reached):
        if reached == point:
            print(f"REACHED {reached}", flush=True)
            sys.stdin.readline()  # blocks until released; a SIGKILL ends the process here

    return hook


def main():
    args = json.loads(sys.argv[1])
    # Same disposable-target guard as the workers' own entry points.
    assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
    maker = sessionmaker(bind=create_engine(args["db_url"]), expire_on_commit=False)
    target = UUID(args["target"])
    hook = rendezvous(args["crash_at"])
    if args["kind"] == "filing":
        from app import filing_worker

        model = FilingExecution
        columns = (model.id, model.owner_id, model.scope_key, model.document_id)
        process, collaborator = filing_worker.process, FileDestination(args["ledger"], hook)
    else:
        from app import notification_worker

        model = NotificationDelivery
        columns = (model.id, model.owner_id, model.scope_key)
        process, collaborator = notification_worker.process, FileChannel(args["ledger"], hook)
    with maker() as db:
        candidate = db.execute(select(*columns).where(model.id == target)).one()
    print(f"RESULT {process(maker, candidate, collaborator)}", flush=True)


if __name__ == "__main__":
    main()
