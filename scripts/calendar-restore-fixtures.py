"""Synthetic bounded calendar history sentinel for the logical recovery drill."""

import sys
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, update

from app import calendars, identity
from app.calendar_contracts import Window
from app.config import settings
from app.db import SessionLocal
from app.models import CalendarRevision, CalendarSource, User

assert settings.env == "test" and settings.postgres_db in {"butler_test", "butler_test_restore"}
assert settings.postgres_user == "postgres"
phase = sys.argv[1]
assert phase in {"seed", "check"}
with SessionLocal.begin() as db:
    owner = db.get(User, UUID("22222222-2222-4222-8222-222222222222"))
    assert owner and owner.slug == "synthetic-queue-restore"
    for name in ("active", "forgotten"):
        identifier = uuid5(NAMESPACE_URL, "butler-synthetic-calendar-restore-" + name)
        if phase == "seed":
            now = identity.now_utc()
            row = CalendarSource(
                id=identifier,
                owner_id=owner.id,
                scope_key="household_shared",
                state="active",
                revision=1,
                data={
                    "label": "Synthetic restore calendar",
                    "status": "setup_required",
                    "window": None,
                    "attempt_at": None,
                    "changes": None,
                },
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            calendars.remember(db, owner, row)
            db.flush()
            snapshot = Window.model_validate(
                {
                    "complete": True,
                    "cursor": "synthetic-restore-cursor",
                    "fetched_at": now.isoformat(),
                    "timezone": "Europe/Paris",
                    "start_date": "2026-10-25",
                    "end_date": "2026-10-26",
                    "events": [
                        {
                            "kind": "timed",
                            "uid": "synthetic-recurring",
                            "recurrence_id": "2026-10-25T09:00:00+01:00",
                            "sequence": 2,
                            "title": "Synthetic restore event",
                            "timezone": "Europe/Paris",
                            "start": "2026-10-25T09:00:00+01:00",
                            "end": "2026-10-25T10:00:00+01:00",
                        }
                    ],
                }
            ).canonical()
            row.data = {
                **row.data,
                "status": "offline",
                "window": snapshot,
                "attempt_at": now.isoformat(),
                "changes": calendars.changes(None, snapshot),
            }
            row.revision += 1
            row.updated_at = identity.now_utc()
            calendars.remember(db, owner, row)
            db.flush()
            if name == "forgotten":
                row.state, row.data = "forgotten", None
                row.revision += 1
                row.updated_at = identity.now_utc()
                db.flush()
                db.execute(
                    update(CalendarRevision)
                    .where(CalendarRevision.source_id == identifier)
                    .values(snapshot=None)
                )
                calendars.remember(db, owner, row)
        else:
            row = db.get(CalendarSource, identifier)
            history = list(
                db.scalars(
                    select(CalendarRevision)
                    .where(CalendarRevision.source_id == identifier)
                    .order_by(CalendarRevision.revision)
                )
            )
            assert row.owner_id == owner.id and row.scope_key == "household_shared"
            if name == "active":
                assert row.revision == 2 and row.data["status"] == "offline" and len(history) == 2
                assert history[-1].snapshot == row.data
                event = row.data["window"]["events"][0]
                assert event["start"] == "2026-10-25T08:00:00+00:00" and event["sequence"] == 2
                assert event["recurrence_id"] == "2026-10-25T09:00:00+01:00"
            else:
                assert row.state == "forgotten" and row.revision == 3 and row.data is None
                assert len(history) == 3 and all(r.snapshot is None for r in history)
print("Synthetic calendar snapshot/history/scrubbing recovery verified")
