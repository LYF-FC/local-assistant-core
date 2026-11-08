"""Private one-shot deterministic no-op worker; never activates a scheduler."""

from sqlalchemy.exc import SQLAlchemyError

from app import jobs
from app.config import settings
from app.db import SessionLocal


def run_once(maker=SessionLocal) -> bool:
    with maker.begin() as db:
        lease = jobs.claim(db)
    if lease is None:
        return False
    # A crash here leaves a committed lease for bounded recovery.
    with maker.begin() as db:
        return jobs.finish(db, lease)


def main():
    if settings.env not in {"development", "test"}:
        raise RuntimeError("Worker is development/test only")
    if settings.postgres_user != "butler_runtime":
        raise RuntimeError("Worker requires restricted runtime credentials")
    if settings.env == "test" and not settings.postgres_db.startswith("butler_test"):
        raise RuntimeError("Tests require a disposable database")
    try:
        run_once()
    except SQLAlchemyError:
        raise RuntimeError("Local worker unavailable; transaction aborted") from None
    print("Local no-op worker pass completed")


if __name__ == "__main__":
    main()
