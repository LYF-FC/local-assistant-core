"""Synthetic provider-mode calendar sentinel for the logical recovery drill (Batch 3).

seed:  one synchronized provider source (series, an override, a series tombstone, a persisted
       cursor, gapless change rows) and one provider source that was forgotten after syncing.
check: after pg_restore, every row, counter, tombstone floor, cursor and scrub survived; a resumed
       sync from the restored cursor applies only what is new and never repeats a change.
No provider network, no external credential: the feed is a synthetic SQLite fixture file read by
the real isolated fetch child (the same path the worker uses), kept in the temp directory between
the seed and check phases.
"""

import shutil
import sys
import tempfile
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "tests"))

from calendar_synthetic_writer import SyntheticWriter
from sqlalchemy import func, select, update

from app import calendar_sync as sync
from app import calendars, identity
from app.config import settings
from app.db import SessionLocal
from app.manage import set_scope
from app.models import (
    CalendarChange,
    CalendarOverride,
    CalendarProviderLink,
    CalendarRevision,
    CalendarSeries,
    CalendarSource,
    CalendarSyncState,
    User,
)

assert settings.env == "test" and settings.postgres_db in {
    "butler_test",
    "butler_test_restore",
}
assert settings.postgres_user == "postgres"
phase = sys.argv[1]
assert phase in {"seed", "check"}
OWNER = UUID("22222222-2222-4222-8222-222222222222")
RID = "TZID=Europe/Paris:20260322T090000"
BODY = {
    "title": "Synthetic restore series",
    "dtstart": "TZID=Europe/Paris:20260315T090000",
    "duration": 3600,
    "rrule": "FREQ=WEEKLY;COUNT=4",
}


def ident(name):
    return uuid5(NAMESPACE_URL, "butler-synthetic-calendar-provider-restore-" + name)


def item(entity, operation, uid, sequence, recurrence_id, body):
    return {
        "entity": entity,
        "operation": operation,
        "uid": uid,
        "sequence": sequence,
        "recurrence_id": recurrence_id,
        "body": body,
    }


FIRST = [
    item("series", "upsert", "s1", 1, None, BODY),
    item("override", "upsert", "s1", 1, RID, {"recurrence_id": RID, "status": "cancelled"}),
    item("series", "upsert", "s2", 1, None, {**BODY, "title": "Synthetic to delete"}),
]
SECOND = [item("series", "delete", "s2", 2, None, None)]
THIRD = [item("series", "upsert", "s3", 1, None, {**BODY, "title": "Synthetic after restore"})]
# The synthetic fixture file the real fetch child reads; it must survive between the two phases.
FIXTURES = Path(tempfile.gettempdir()) / "butler-synthetic-calendar-restore"
settings.calendar_synthetic_directory = FIXTURES


def writer():
    if phase == "seed" and not hasattr(writer, "ready"):
        shutil.rmtree(FIXTURES, ignore_errors=True)
        FIXTURES.mkdir(mode=0o700)
        writer.ready = True
    assert FIXTURES.is_dir(), "the seed phase must run first on this host"
    return SyntheticWriter(FIXTURES / "household.sqlite")


def create(db, owner, name):
    now = identity.now_utc()
    row = CalendarSource(
        id=ident(name),
        owner_id=owner.id,
        scope_key="household_shared",
        state="active",
        revision=1,
        data={
            "label": "Synthetic restore provider " + name,
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
    db.add(
        CalendarProviderLink(
            source_id=row.id,
            owner_id=owner.id,
            scope_key=row.scope_key,
            provider_kind="synthetic",
            provider_ref="household",
            created_at=now,
        )
    )
    db.flush()
    db.add(
        CalendarSyncState(
            source_id=row.id,
            owner_id=owner.id,
            scope_key=row.scope_key,
            status="never",
            applied_seq=0,
            attempts=0,
            revision=1,
            updated_at=now,
        )
    )
    return row


def membership(grant):
    """The sync authority check needs the owner's scope; the drill grants it only while syncing."""
    with SessionLocal.begin() as db:
        set_scope(db, db.get(User, OWNER), "household_shared", grant)


def synchronize(source_id):
    outcome = sync.sync_source(SessionLocal, source_id, explicit=True)
    assert outcome["outcome"] == "ok", outcome
    return outcome


if phase == "seed":
    with SessionLocal.begin() as db:
        owner = db.get(User, OWNER)
        assert owner and owner.slug == "synthetic-queue-restore"
        create(db, owner, "active")
        create(db, owner, "forgotten")
    membership(True)
    try:
        # the first page, then (a second pass continues from the stored cursor) the delete page
        for batch in (FIRST, SECOND):
            writer().append(batch)
            for name in ("active", "forgotten"):
                synchronize(ident(name))
    finally:
        membership(False)
    with SessionLocal.begin() as db:
        # a series tombstone must exist before the dump
        assert (
            db.scalar(
                select(func.count())
                .select_from(CalendarSeries)
                .where(
                    CalendarSeries.source_id == ident("active"),
                    CalendarSeries.state == "deleted",
                )
            )
            == 1
        )
        owner = db.get(User, OWNER)
        row = db.get(CalendarSource, ident("forgotten"))
        now = identity.now_utc()
        row.state, row.data = "forgotten", None
        row.revision += 1
        row.updated_at = now
        db.flush()
        db.execute(
            update(CalendarRevision)
            .where(CalendarRevision.source_id == row.id)
            .values(snapshot=None)
        )
        calendars.remember(db, owner, row)
        sync.scrub(db, row.id, now)
else:
    with SessionLocal.begin() as db:
        source = ident("active")
        state = db.get(CalendarSyncState, source)
        assert state.status == "ok" and state.cursor == "v1:4" and state.applied_seq == 4, state
        assert state.claim_token is None and state.last_success_at is not None
        series = {
            r.uid: r
            for r in db.scalars(select(CalendarSeries).where(CalendarSeries.source_id == source))
        }
        assert series["s1"].state == "active" and series["s1"].title == "Synthetic restore series"
        assert (
            series["s2"].state == "deleted"
            and series["s2"].sequence == 2
            and series["s2"].title is None
        )
        override = db.scalars(
            select(CalendarOverride).where(CalendarOverride.source_id == source)
        ).one()
        assert override.state == "active" and override.status == "cancelled"
        seqs = sorted(
            db.scalars(select(CalendarChange.seq).where(CalendarChange.source_id == source))
        )
        assert seqs == [1, 2, 3, 4], seqs
        gone = ident("forgotten")
        row = db.get(CalendarSource, gone)
        assert row.state == "forgotten" and row.data is None
        assert db.get(CalendarProviderLink, gone).provider_ref is None
        scrubbed = db.get(CalendarSyncState, gone)
        assert scrubbed.status == "blocked" and scrubbed.blocked_reason == "source_forgotten"
        assert scrubbed.cursor is None
        assert all(
            r.state == "forgotten" and r.uid is None and r.title is None
            for r in db.scalars(select(CalendarSeries).where(CalendarSeries.source_id == gone))
        )
        assert all(
            c.snapshot is None
            for c in db.scalars(select(CalendarChange).where(CalendarChange.source_id == gone))
        )
    # resume from the restored cursor: only the new series is applied, nothing is repeated
    writer().append(THIRD)
    membership(True)
    try:
        outcome = synchronize(ident("active"))
        assert (
            sync.sync_source(SessionLocal, ident("forgotten"), explicit=True)["outcome"]
            == "skipped"
        )
    finally:
        membership(False)
    assert outcome["changes"] == 1, outcome
    with SessionLocal.begin() as db:
        seqs = sorted(
            db.scalars(
                select(CalendarChange.seq).where(CalendarChange.source_id == ident("active"))
            )
        )
        assert seqs == [1, 2, 3, 4, 5], seqs
    # the forgotten source stays closed
    assert sync.sync_source(SessionLocal, ident("forgotten"), explicit=True)["outcome"] == "skipped"
print("Synthetic provider calendar sync/cursor/tombstone/scrub recovery verified")
