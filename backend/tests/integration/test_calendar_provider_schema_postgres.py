"""Migration 0035 on real PostgreSQL: ownership chain, guards, F1, grants, limits, crash, races.

Every refusal is a direct-SQL statement run as the restricted ``butler_runtime`` role. The
assertion names the constraint or trigger that refused it (``diag.constraint_name``) and checks
that no row of the calendar tables changed (a fingerprint of the whole content before and after).
"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import RUNTIME_PASSWORD, SYNTHETIC_PASSWORD
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app import calendar_codes as codes
from app.config import settings
from app.manage import provision
from app.runtime_role import configure

pytestmark = pytest.mark.integration

SCOPE = "household_shared"
TABLES = (
    "calendar_sources",
    "calendar_provider_links",
    "calendar_series",
    "calendar_overrides",
    "calendar_changes",
    "calendar_sync_state",
)
UPSERT_HASH = "a" * 64
LITERAL_TOMBSTONE = "136a90c93d282c605c5a7003b6a381fa429e9bce3201d454cb59a41480005b01"
DATA = json.dumps({"status": "setup_required", "label": "Synthetic provider"})


def now():
    return datetime.now(UTC)


class World:
    """Synthetic fixtures plus the SQL helpers shared by the tests."""

    def __init__(self, admin_engine, runtime_engine):
        self.admin = admin_engine
        self.rt = runtime_engine
        maker = sessionmaker(bind=admin_engine, expire_on_commit=False)
        with maker.begin() as db:
            self.owner = provision(
                db, "synthetic-" + uuid4().hex, "Synthetic A", SYNTHETIC_PASSWORD, {SCOPE}
            ).id
            self.other = provision(
                db, "synthetic-" + uuid4().hex, "Synthetic B", SYNTHETIC_PASSWORD, {SCOPE}
            ).id

    # -- fixtures -------------------------------------------------------------------------
    def source(self, owner=None, scope=SCOPE, link=True, state=True):
        sid, owner, t = uuid4(), owner or self.owner, now()
        with self.rt.begin() as c:
            c.execute(
                text(
                    "INSERT INTO calendar_sources (id, owner_id, scope_key, state, revision, data,"
                    " created_at, updated_at) VALUES (:id, :o, :s, 'active', 1, CAST(:d AS jsonb), :t, :t)"
                ),
                {"id": sid, "o": owner, "s": scope, "d": DATA, "t": t},
            )
            if link:
                c.execute(
                    text(
                        "INSERT INTO calendar_provider_links (source_id, owner_id, scope_key,"
                        " provider_kind, provider_ref, created_at)"
                        " VALUES (:id, :o, :s, 'synthetic', 'household', :t)"
                    ),
                    {"id": sid, "o": owner, "s": scope, "t": t},
                )
                if state:
                    c.execute(
                        text(
                            "INSERT INTO calendar_sync_state (source_id, owner_id, scope_key, status,"
                            " applied_seq, attempts, revision, updated_at)"
                            " VALUES (:id, :o, :s, 'never', 0, 0, 1, :t)"
                        ),
                        {"id": sid, "o": owner, "s": scope, "t": t},
                    )
        return sid

    def series(self, src, uid="u1", sequence=1, state="active", owner=None, conn=None):
        sid, t, owner = uuid4(), now(), owner or self.owner
        params = {"id": sid, "src": src, "o": owner, "uid": uid, "seq": sequence, "t": t}
        if state == "active":
            sql = (
                "INSERT INTO calendar_series (id, source_id, owner_id, scope_key, uid, state, kind,"
                " status, sequence, title, start_local, zone, duration_seconds, rule, exdates, rdates,"
                " revision, created_at, updated_at) VALUES (:id, :src, :o, 'household_shared', :uid,"
                " 'active', 'timed', 'confirmed', :seq, 'Synthetic', '2026-03-15 09:00:00',"
                " 'Europe/Paris', 3600, NULL, CAST('[]' AS jsonb), CAST('[]' AS jsonb), 1, :t, :t)"
            )
        else:
            sql = (
                "INSERT INTO calendar_series (id, source_id, owner_id, scope_key, uid, state,"
                " sequence, revision, created_at, updated_at, deleted_at) VALUES (:id, :src, :o,"
                " 'household_shared', :uid, 'deleted', :seq, 1, :t, :t, :t)"
            )
        self._run(conn, sql, params)
        return sid

    def override(
        self, src, series, rid="2026-03-22T09:00:00", sequence=1, state="active", conn=None
    ):
        oid, t = uuid4(), now()
        params = {
            "id": oid,
            "ser": series,
            "src": src,
            "o": self.owner,
            "rid": rid,
            "seq": sequence,
            "t": t,
        }
        if state == "active":
            sql = (
                "INSERT INTO calendar_overrides (id, series_id, source_id, owner_id, scope_key,"
                " recurrence_id, state, status, sequence, revision, created_at, updated_at)"
                " VALUES (:id, :ser, :src, :o, 'household_shared', :rid, 'active', 'cancelled',"
                " :seq, 1, :t, :t)"
            )
        else:
            sql = (
                "INSERT INTO calendar_overrides (id, series_id, source_id, owner_id, scope_key,"
                " recurrence_id, state, sequence, revision, created_at, updated_at, deleted_at)"
                " VALUES (:id, :ser, :src, :o, 'household_shared', :rid, 'deleted', :seq, 1, :t,"
                " :t, :t)"
            )
        self._run(conn, sql, params)
        return oid

    def change(
        self, src, seq, target, *, entity="series", operation="upsert", sequence=1, conn=None
    ):
        """Insert one change row and bump ``applied_seq`` to it in the same transaction."""
        digest = LITERAL_TOMBSTONE if operation == "delete" else UPSERT_HASH
        column = "series_id" if entity == "series" else "override_id"
        params = {
            "id": uuid4(),
            "src": src,
            "o": self.owner,
            "seq": seq,
            "e": entity,
            "target": target,
            "op": operation,
            "sequence": sequence,
            "h": digest,
            "run": uuid4(),
            "t": now(),
        }
        sql = (
            f"INSERT INTO calendar_changes (id, source_id, owner_id, scope_key, seq, entity, {column},"
            " operation, sequence, content_hash, snapshot, sync_run_id, cursor_after, applied_at)"
            " VALUES (:id, :src, :o, 'household_shared', :seq, :e, :target, :op, :sequence, :h,"
            " CAST('{\"title\": \"Synthetic\"}' AS jsonb), :run, 'v1:1', :t)"
        )
        bump = (
            "UPDATE calendar_sync_state SET applied_seq=:seq, revision=revision+1, updated_at=:t"
            " WHERE source_id=:src"
        )
        if conn is not None:
            conn.execute(text(sql), params)
            conn.execute(text(bump), params)
        else:
            with self.rt.begin() as c:
                c.execute(text(sql), params)
                c.execute(text(bump), params)

    # -- helpers --------------------------------------------------------------------------
    def _run(self, conn, sql, params):
        if conn is not None:
            return conn.execute(text(sql), params)
        with self.rt.begin() as c:
            return c.execute(text(sql), params)

    def run(self, sql, **params):
        with self.rt.begin() as c:
            return c.execute(text(sql), params)

    def one(self, sql, **params):
        with self.admin.connect() as c:
            return c.execute(text(sql), params).one()

    def scalar(self, sql, **params):
        with self.admin.connect() as c:
            return c.execute(text(sql), params).scalar()

    def fingerprint(self):
        with self.admin.connect() as c:
            return [
                c.execute(
                    text(
                        f"SELECT md5(COALESCE(string_agg(x::text, '|' ORDER BY x::text), '')) FROM {t} x"
                    )
                ).scalar()
                for t in TABLES
            ]

    def refused(self, sql, constraint=None, sqlstate=None, engine=None, **params):
        before = self.fingerprint()
        with pytest.raises(DBAPIError) as caught, (engine or self.rt).begin() as c:
            c.execute(text(sql), params)
        diag = caught.value.orig.diag
        if constraint is not None:
            assert diag.constraint_name == constraint, (diag.constraint_name, diag.message_primary)
        if sqlstate is not None:
            assert caught.value.orig.sqlstate == sqlstate
        assert self.fingerprint() == before, "a refused statement changed a row"
        return caught.value

    def refused_txn(self, statements, constraint, **params):
        """Several statements in one transaction; the last statement or the commit refuses."""
        before = self.fingerprint()
        with pytest.raises(DBAPIError) as caught, self.rt.begin() as c:
            for sql in statements:
                c.execute(text(sql), params)
        assert caught.value.orig.diag.constraint_name == constraint, (
            caught.value.orig.diag.constraint_name,
            caught.value.orig.diag.message_primary,
        )
        assert self.fingerprint() == before
        return caught.value


@pytest.fixture
def world(postgres_engine, runtime_engine):
    return World(postgres_engine, runtime_engine)


UPDATE_SERIES = "UPDATE calendar_series SET {set}, revision=revision+1, updated_at=:t WHERE id=:id"
DELETE_SERIES = (
    "UPDATE calendar_series SET state='deleted', sequence=:seq, kind=NULL, status=NULL, title=NULL,"
    " start_local=NULL, zone=NULL, duration_seconds=NULL, rule=NULL, exdates=NULL, rdates=NULL,"
    " provider_version=NULL, deleted_at=:t, revision=revision+1, updated_at=:t WHERE id=:id"
)
DELETE_OVERRIDE = (
    "UPDATE calendar_overrides SET state='deleted', deleted_by_cascade=:cascade, sequence=:seq,"
    " status=NULL, start_wall=NULL, duration=NULL, title=NULL, deleted_at=:t,"
    " revision=revision+1, updated_at=:t WHERE id=:id"
)
RAISE_OVERRIDE_FLOOR = (
    "UPDATE calendar_overrides SET deleted_by_cascade=false, sequence=:seq, revision=revision+1,"
    " updated_at=:t WHERE id=:id"
)
REVIVE_OVERRIDE = (
    "UPDATE calendar_overrides SET state='active', deleted_by_cascade=false, status='cancelled',"
    " sequence=:seq, deleted_at=NULL, revision=revision+1, updated_at=:t WHERE id=:id"
)
REVIVE_SERIES = (
    "UPDATE calendar_series SET state='active', kind='timed', status='confirmed', sequence=:seq,"
    " title='Synthetic', start_local='2026-03-15 09:00:00', zone='Europe/Paris',"
    " duration_seconds=3600, exdates=CAST('[]' AS jsonb), rdates=CAST('[]' AS jsonb),"
    " deleted_at=NULL, revision=revision+1, updated_at=:t WHERE id=:id"
)


def override_state(world, oid):
    return world.one(
        "SELECT state, deleted_by_cascade, sequence, deleted_at, revision"
        " FROM calendar_overrides WHERE id=:id",
        id=oid,
    )


# ------------------------------------------------------------------------------------------
# Ownership chain
# ------------------------------------------------------------------------------------------
def test_ownership_chain_is_enforced_by_composite_foreign_keys(world):
    src = world.source()
    ser = world.series(src)
    ovr = world.override(src, ser)
    foreign = world.source(owner=world.other)
    foreign_series = world.series(foreign, owner=world.other)
    foreign_override = uuid4()
    t = now()
    manual = world.source(link=False)
    unstated = world.source(state=False)
    common = {"t": t, "o": world.owner, "other": world.other}

    link = (
        "INSERT INTO calendar_provider_links (source_id, owner_id, scope_key, provider_kind,"
        " provider_ref, created_at) VALUES (:src, :owner, :scope, 'synthetic', 'household', :t)"
    )
    for owner, scope in ((world.other, SCOPE), (world.owner, "member_a_private")):
        fresh = world.source(link=False)
        world.refused(link, "fk_calendar_link_source", src=fresh, owner=owner, scope=scope, t=t)

    series = (
        "INSERT INTO calendar_series (id, source_id, owner_id, scope_key, uid, state, kind, status,"
        " sequence, title, start_local, zone, duration_seconds, exdates, rdates, revision,"
        " created_at, updated_at) VALUES (:id, :src, :owner, :scope, 'x', 'active', 'timed',"
        " 'confirmed', 1, 'T', '2026-03-15 09:00:00', 'UTC', 60, CAST('[]' AS jsonb),"
        " CAST('[]' AS jsonb), 1, :t, :t)"
    )
    for src_id, owner, scope in (
        (src, world.other, SCOPE),
        (src, world.owner, "member_b_private"),
        (manual, world.owner, SCOPE),  # a series on a manual-mode (unlinked) source
    ):
        world.refused(
            series, "fk_calendar_series_link", id=uuid4(), src=src_id, owner=owner, scope=scope, t=t
        )

    override = (
        "INSERT INTO calendar_overrides (id, series_id, source_id, owner_id, scope_key,"
        " recurrence_id, state, status, sequence, revision, created_at, updated_at) VALUES"
        " (:id, :ser, :src, :owner, :scope, '2026-04-01T09:00:00', 'active', 'cancelled', 1, 1,"
        " :t, :t)"
    )
    for ser_id, src_id, owner, scope in (
        (ser, foreign, world.owner, SCOPE),  # series belongs to another source
        (ser, src, world.other, SCOPE),
        (ser, src, world.owner, "member_a_private"),
        (foreign_series, src, world.owner, SCOPE),
    ):
        world.refused(
            override,
            "fk_calendar_override_series",
            id=uuid4(),
            ser=ser_id,
            src=src_id,
            owner=owner,
            scope=scope,
            t=t,
        )

    change = (
        "INSERT INTO calendar_changes (id, source_id, owner_id, scope_key, seq, entity, series_id,"
        " override_id, operation, sequence, content_hash, actor_id, sync_run_id, cursor_after,"
        " applied_at) VALUES (:id, :src, :o, 'household_shared', 1, :entity, :series, :override,"
        " 'upsert', 1, :h, :actor, :run, 'v1:1', :t)"
    )
    base = {"id": uuid4(), "src": src, "h": UPSERT_HASH, "actor": None, "run": uuid4(), **common}
    cases = (
        ("series", foreign_series, None, "fk_calendar_change_series", None),
        ("series", ser, ovr, "ck_calendar_change_target", None),  # both ids
        ("series", None, None, "ck_calendar_change_target", None),  # neither id
        ("series", None, ovr, "ck_calendar_change_target", None),  # entity does not match
        ("override", ser, None, "ck_calendar_change_target", None),
        ("series", ser, None, "ck_calendar_change_actor", uuid4()),  # actor must stay NULL
    )
    for entity, series_id, override_id, expected, actor in cases:
        world.refused(
            change,
            expected,
            **{
                **base,
                "id": uuid4(),
                "entity": entity,
                "series": series_id,
                "override": override_id,
                "actor": actor,
            },
        )
    world.refused(  # an override of another source cannot be referenced
        change,
        "fk_calendar_change_override",
        **{**base, "entity": "override", "series": None, "override": foreign_override},
    )

    state = (
        "INSERT INTO calendar_sync_state (source_id, owner_id, scope_key, status, applied_seq,"
        " attempts, revision, updated_at) VALUES (:src, :owner, :scope, 'never', 0, 0, 1, :t)"
    )
    for owner, scope in ((world.other, SCOPE), (world.owner, "member_a_private")):
        world.refused(state, "fk_calendar_sync_link", src=unstated, owner=owner, scope=scope, t=t)


# ------------------------------------------------------------------------------------------
# Identity immutability, deletion, grants
# ------------------------------------------------------------------------------------------
def test_identity_columns_and_uid_are_immutable(world):
    src = world.source()
    other = world.source()
    ser = world.series(src)
    ovr = world.override(src, ser)
    t = now()
    for column, value in (
        ("id", uuid4()),
        ("source_id", other),
        ("owner_id", world.other),
        ("scope_key", "member_a_private"),
        ("created_at", t - timedelta(days=1)),
        ("uid", "renamed"),
    ):
        world.refused(
            UPDATE_SERIES.format(set=f"{column}=:v"),
            "butler_calendar_series_identity",
            id=ser,
            v=value,
            t=t,
        )
    other_series = world.series(src, uid="u2")
    for column, value in (
        ("id", uuid4()),
        ("series_id", other_series),
        ("source_id", other),
        ("owner_id", world.other),
        ("scope_key", "member_a_private"),
        ("recurrence_id", "2030-01-01T00:00:00"),
        ("created_at", t - timedelta(days=1)),
    ):
        world.refused(
            f"UPDATE calendar_overrides SET {column}=:v, revision=revision+1, updated_at=:t WHERE id=:id",
            "butler_calendar_override_identity",
            id=ovr,
            v=value,
            t=t,
        )
    for column, value in (
        ("source_id", other),
        ("owner_id", world.other),
        ("scope_key", "member_a_private"),
    ):
        world.refused(
            f"UPDATE calendar_sync_state SET {column}=:v, revision=revision+1, updated_at=:t"
            " WHERE source_id=:src",
            "butler_calendar_sync_identity",
            v=value,
            src=src,
            t=t,
        )
    world.refused(
        "UPDATE calendar_provider_links SET provider_ref='other' WHERE source_id=:src",
        "butler_calendar_link_immutable",
        src=src,
    )
    world.refused(
        "UPDATE calendar_provider_links SET provider_ref=NULL WHERE source_id=:src",
        "butler_calendar_link_immutable",  # only while the source reads as forgotten
        src=src,
    )


@pytest.mark.parametrize(
    "table",
    [
        "calendar_provider_links",
        "calendar_series",
        "calendar_overrides",
        "calendar_changes",
        "calendar_sync_state",
    ],
)
def test_no_role_can_delete_or_truncate(world, runtime_engine, postgres_engine, table):
    src = world.source()  # every table needs a row, or a row-level DELETE trigger never fires
    ser = world.series(src)
    world.override(src, ser)
    world.change(src, 1, ser)
    world.refused(f"DELETE FROM {table}", sqlstate="42501")
    world.refused(f"TRUNCATE {table} CASCADE", sqlstate="42501")
    # even the owner role is stopped by the seal triggers
    world.refused(f"DELETE FROM {table}", "butler_calendar_provider_sealed", engine=postgres_engine)
    world.refused(
        f"TRUNCATE {table} CASCADE", "butler_calendar_provider_sealed", engine=postgres_engine
    )


def test_runtime_grants_are_exactly_the_documented_ones(world):
    with world.rt.connect() as c:

        def table(name, privilege):
            return c.execute(
                text("SELECT has_table_privilege(current_user, :t, :p)"),
                {"t": name, "p": privilege},
            ).scalar()

        def column(name, col):
            return c.execute(
                text("SELECT has_column_privilege(current_user, :t, :c, 'UPDATE')"),
                {"t": name, "c": col},
            ).scalar()

        for name in ("calendar_series", "calendar_overrides", "calendar_sync_state"):
            assert [
                table(name, p) for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
            ] == [
                True,
                True,
                True,
                False,
                False,
            ]
        for name in ("calendar_provider_links", "calendar_changes"):
            assert [
                table(name, p) for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
            ] == [
                True,
                True,
                False,
                False,
                False,
            ]
        assert column("calendar_provider_links", "provider_ref")
        assert not column("calendar_provider_links", "provider_kind")
        assert column("calendar_changes", "snapshot")
        assert not column("calendar_changes", "sequence")
        assert not column("calendar_changes", "seq")


def test_out_of_contract_updates_by_the_runtime_role_are_denied(world):
    src = world.source()
    ser = world.series(src)
    world.change(src, 1, ser)
    world.refused(
        "UPDATE calendar_changes SET sequence=sequence+1 WHERE source_id=:s",
        sqlstate="42501",
        s=src,
    )
    world.refused(
        "UPDATE calendar_provider_links SET provider_kind='synthetic' WHERE source_id=:s",
        sqlstate="42501",
        s=src,
    )
    # snapshot redaction is allowed by the grant but refused by the guard while the source is live
    world.refused(
        "UPDATE calendar_changes SET snapshot=NULL WHERE source_id=:s",
        "butler_calendar_change_sealed",
        s=src,
    )


# ------------------------------------------------------------------------------------------
# Series and override transitions, F1
# ------------------------------------------------------------------------------------------
def test_series_transitions_follow_the_documented_lifecycle(world):
    src = world.source()
    ser = world.series(src, sequence=3)
    t = now()
    sql = UPDATE_SERIES.format(set="sequence=:seq, title='Changed'")
    for sequence in (3, 2):  # equal and lower sequence are refused
        world.refused(sql, "butler_calendar_series_transition", id=ser, seq=sequence, t=t)
    world.refused(
        "UPDATE calendar_series SET title='X', sequence=4, revision=revision+2, updated_at=:t WHERE id=:id",
        "butler_calendar_series_revision",
        id=ser,
        t=t,
    )
    world.refused(
        "UPDATE calendar_series SET title='X', sequence=4, revision=revision+1, updated_at=:t"
        " WHERE id=:id",
        "butler_calendar_series_revision",
        id=ser,
        t=t - timedelta(days=1),
    )
    world.run(sql, id=ser, seq=4, t=t)
    world.run(DELETE_SERIES, id=ser, seq=6, t=t)
    deleted_at = world.scalar("SELECT deleted_at FROM calendar_series WHERE id=:id", id=ser)
    # a floor-raising delete preserves deleted_at and a moved deleted_at is refused
    world.refused(
        "UPDATE calendar_series SET sequence=7, deleted_at=:moved, revision=revision+1, updated_at=:t"
        " WHERE id=:id",
        "butler_calendar_series_transition",
        id=ser,
        moved=t + timedelta(hours=1),
        t=t,
    )
    world.run(
        "UPDATE calendar_series SET sequence=7, revision=revision+1, updated_at=:t WHERE id=:id",
        id=ser,
        t=t,
    )
    assert world.scalar("SELECT deleted_at FROM calendar_series WHERE id=:id", id=ser) == deleted_at
    world.refused(REVIVE_SERIES, "butler_calendar_series_transition", id=ser, seq=7, t=t)
    world.run(REVIVE_SERIES, id=ser, seq=8, t=t)
    assert world.one(
        "SELECT state, sequence, revision, deleted_at FROM calendar_series WHERE id=:id", id=ser
    ) == ("active", 8, 5, None)
    # content must be present exactly when active
    world.refused(
        "UPDATE calendar_series SET title=NULL, sequence=9, revision=revision+1, updated_at=:t"
        " WHERE id=:id",
        "ck_calendar_series_content",
        id=ser,
        t=t,
    )
    world.refused(
        "UPDATE calendar_series SET state='deleted', sequence=9, revision=revision+1, updated_at=:t,"
        " deleted_at=:t WHERE id=:id",
        "ck_calendar_series_content",  # a tombstone keeps no content
        id=ser,
        t=t,
    )


def test_f1_cascade_origin_is_coupled_to_the_floor_by_the_database(world):
    src = world.source()
    ser = world.series(src, sequence=2)
    ovr = world.override(src, ser, sequence=3)
    t = now()

    # The flag cannot be set while the series is still active ...
    world.refused(
        DELETE_OVERRIDE,
        "butler_calendar_override_floor_origin",
        id=ovr,
        cascade=True,
        seq=3,
        t=now(),
    )
    # ... nor with a changed floor, even after the series was deleted in the same transaction
    before = world.fingerprint()
    with pytest.raises(DBAPIError) as caught, world.rt.begin() as c:
        c.execute(text(DELETE_SERIES), {"id": ser, "seq": 5, "t": now()})
        c.execute(text(DELETE_OVERRIDE), {"id": ovr, "cascade": True, "seq": 4, "t": now()})
    assert caught.value.orig.diag.constraint_name == "butler_calendar_override_floor_origin"
    assert world.fingerprint() == before
    # the application's order: series first, then the cascade, one transaction
    with world.rt.begin() as c:
        c.execute(text(DELETE_SERIES), {"id": ser, "seq": 5, "t": now()})
        c.execute(text(DELETE_OVERRIDE), {"id": ovr, "cascade": True, "seq": 3, "t": now()})
    assert override_state(world, ovr)[:3] == ("deleted", True, 3)
    deleted_at = override_state(world, ovr)[3]

    # A cascade tombstone cannot be edited while keeping the flag, and a bare flag reset or a
    # same-floor update is refused: floor and origin change only together, upward.
    touch = "UPDATE calendar_overrides SET {set}, revision=revision+1, updated_at=:t WHERE id=:id"
    for sql, params, constraint in (
        (RAISE_OVERRIDE_FLOOR, {"seq": 3}, "butler_calendar_override_transition"),
        (RAISE_OVERRIDE_FLOOR, {"seq": 2}, "butler_calendar_override_transition"),
        (touch.format(set="sequence=9"), {}, "butler_calendar_override_floor_origin"),
        (touch.format(set="deleted_by_cascade=true"), {}, "butler_calendar_override_floor_origin"),
    ):
        world.refused(sql, constraint, id=ovr, t=now(), **params)
    # the flag cannot be turned on for a delete-origin tombstone, nor on an active row
    plain = world.override(src, world.series(src, uid="u2"), sequence=1, state="deleted")
    world.refused(
        touch.format(set="deleted_by_cascade=true"),
        "butler_calendar_override_floor_origin",
        id=plain,
        t=now(),
    )
    world.refused(
        touch.format(set="deleted_by_cascade=true"),
        "butler_calendar_override_floor_origin",
        id=world.override(src, world.series(src, uid="u3")),
        t=now(),
    )
    # a floor-raising delete: strictly higher sequence, flag false, deleted_at preserved
    world.refused(
        "UPDATE calendar_overrides SET deleted_by_cascade=false, sequence=4, deleted_at=:moved,"
        " revision=revision+1, updated_at=:t WHERE id=:id",
        "butler_calendar_override_transition",
        id=ovr,
        moved=t + timedelta(hours=1),
        t=now(),
    )
    world.run(RAISE_OVERRIDE_FLOOR, id=ovr, seq=4, t=now())
    state = override_state(world, ovr)
    assert state[:3] == ("deleted", False, 4) and state[3] == deleted_at
    # a delete-origin tombstone's floor rises with the flag staying false
    world.run(RAISE_OVERRIDE_FLOOR, id=ovr, seq=5, t=now())
    assert override_state(world, ovr)[:3] == ("deleted", False, 5)
    # the cascade flag cannot come back on a tombstone (only the active -> deleted cascade sets it)
    world.refused(
        "UPDATE calendar_overrides SET deleted_by_cascade=true, revision=revision+1, updated_at=:t WHERE id=:id",
        "butler_calendar_override_floor_origin",
        id=ovr,
        t=now(),
    )


def test_f1_flag_on_an_insert_and_with_an_active_state_is_refused(world):
    src = world.source()
    ser = world.series(src)
    t = now()
    insert = (
        "INSERT INTO calendar_overrides (id, series_id, source_id, owner_id, scope_key, recurrence_id,"
        " state, deleted_by_cascade, sequence, revision, created_at, updated_at, deleted_at)"
        " VALUES (:id, :ser, :src, :o, 'household_shared', '2026-03-22T09:00:00', :state, true, 1, 1,"
        " :t, :t, :deleted)"
    )
    for state, deleted in (("deleted", t), ("active", None)):
        world.refused(
            insert,
            "butler_calendar_override_insert",
            id=uuid4(),
            ser=ser,
            src=src,
            o=world.owner,
            state=state,
            t=t,
            deleted=deleted,
        )


def test_f1_cascade_revive_and_resend_paths(world):
    src = world.source()
    ser = world.series(src, sequence=2)
    ovr = world.override(src, ser, sequence=3)
    t = now()
    with world.rt.begin() as c:  # the application's order: series first, then the cascade
        c.execute(text(DELETE_SERIES), {"id": ser, "seq": 5, "t": t})
        c.execute(text(DELETE_OVERRIDE), {"id": ovr, "cascade": True, "seq": 3, "t": t})
    # an override cannot be revived while its series is deleted, nor at or below its floor
    world.refused(REVIVE_OVERRIDE, "butler_calendar_override_series_active", id=ovr, seq=4, t=t)
    with world.rt.begin() as c:  # series revived with a strictly higher sequence
        c.execute(text(REVIVE_SERIES), {"id": ser, "seq": 6, "t": t})
    assert override_state(world, ovr)[:3] == ("deleted", True, 3)  # old overrides stay deleted
    for sequence in (3, 2):
        world.refused(
            REVIVE_OVERRIDE, "butler_calendar_override_transition", id=ovr, seq=sequence, t=t
        )
    world.run(REVIVE_OVERRIDE, id=ovr, seq=4, t=t)
    assert override_state(world, ovr)[:4] == ("active", False, 4, None)
    assert world.scalar("SELECT count(*) FROM calendar_overrides WHERE series_id=:s", s=ser) == 1


def test_a_series_deleted_and_revived_in_one_transaction_commits_with_its_override_resent(world):
    """The deferred orphan check is about the state at commit, not about the transient delete."""
    src = world.source()
    ser = world.series(src, sequence=2)
    ovr = world.override(src, ser, sequence=3)
    t = now()
    with (
        world.rt.begin() as c
    ):  # delete, cascade, revive, resend: the whole page in one transaction
        c.execute(text(DELETE_SERIES), {"id": ser, "seq": 5, "t": t})
        c.execute(text(DELETE_OVERRIDE), {"id": ovr, "cascade": True, "seq": 3, "t": t})
        c.execute(text(REVIVE_SERIES), {"id": ser, "seq": 6, "t": t})
        c.execute(text(REVIVE_OVERRIDE), {"id": ovr, "seq": 7, "t": t})
    assert world.scalar("SELECT state FROM calendar_series WHERE id=:id", id=ser) == "active"
    assert override_state(world, ovr)[:4] == ("active", False, 7, None)
    # the same transaction still cannot end with the override active under a deleted series
    world.refused_txn(
        [DELETE_SERIES.replace(":seq", "9")], "butler_calendar_override_series_active", id=ser, t=t
    )


def test_an_active_override_cannot_outlive_its_series(world):
    src = world.source()
    ser = world.series(src, sequence=1)
    ovr = world.override(src, ser)
    t = now()
    # deleting the series and leaving its override active cannot commit
    world.refused_txn(
        [DELETE_SERIES.replace(":seq", "5")], "butler_calendar_override_series_active", id=ser, t=t
    )
    assert world.scalar("SELECT state FROM calendar_series WHERE id=:id", id=ser) == "active"
    # the override is never inserted or revived as active under a non-active series
    dead = world.series(src, uid="gone", sequence=1, state="deleted")
    world.refused(
        "INSERT INTO calendar_overrides (id, series_id, source_id, owner_id, scope_key, recurrence_id,"
        " state, status, sequence, revision, created_at, updated_at) VALUES (:id, :ser, :src, :o,"
        " 'household_shared', '2026-03-22T09:00:00', 'active', 'cancelled', 1, 1, :t, :t)",
        "butler_calendar_override_series_active",
        id=uuid4(),
        ser=dead,
        src=src,
        o=world.owner,
        t=t,
    )
    assert ovr


def test_override_transitions_and_limits_on_state_and_content(world):
    src = world.source()
    ser = world.series(src)
    ovr = world.override(src, ser, sequence=2)
    now()
    for sequence in (2, 1):
        world.refused(
            "UPDATE calendar_overrides SET title='Moved', sequence=:seq, revision=revision+1,"
            " updated_at=:t WHERE id=:id",
            "butler_calendar_override_transition",
            id=ovr,
            seq=sequence,
            t=now(),
        )
    world.refused(
        "UPDATE calendar_overrides SET title='Moved', sequence=3, revision=revision+2, updated_at=:t"
        " WHERE id=:id",
        "butler_calendar_override_revision",
        id=ovr,
        t=now(),
    )
    world.refused(
        "UPDATE calendar_overrides SET state='deleted', sequence=3, deleted_at=:t, revision=revision+1,"
        " updated_at=:t WHERE id=:id",
        "ck_calendar_override_content",  # a tombstone keeps no content
        id=ovr,
        t=now(),
    )
    world.run(
        "UPDATE calendar_overrides SET title='Moved', start_wall='2026-03-22T10:00:00', duration=1800,"
        " sequence=3, revision=revision+1, updated_at=:t WHERE id=:id",
        id=ovr,
        t=now(),
    )
    world.run(DELETE_OVERRIDE, id=ovr, cascade=False, seq=4, t=now())  # explicit delete
    assert override_state(world, ovr)[:3] == ("deleted", False, 4)


# ------------------------------------------------------------------------------------------
# Change log
# ------------------------------------------------------------------------------------------
def test_change_sequence_is_gapless_and_the_log_is_append_only(world):
    src = world.source()
    ser = world.series(src)
    other = world.series(src, uid="u2")
    t = now()
    insert = (
        "INSERT INTO calendar_changes (id, source_id, owner_id, scope_key, seq, entity, series_id,"
        " operation, sequence, content_hash, sync_run_id, cursor_after, applied_at) VALUES (:id, :src,"
        " :o, 'household_shared', :seq, 'series', :ser, 'upsert', :sequence, :h, :run, 'v1:1', :t)"
    )
    params = {
        "src": src,
        "o": world.owner,
        "ser": ser,
        "h": UPSERT_HASH,
        "run": uuid4(),
        "t": t,
        "sequence": 1,
    }
    for seq in (2, 5):  # a gap and a larger gap on an empty log
        world.refused(insert, "butler_calendar_change_seq", id=uuid4(), seq=seq, **params)
    world.refused(insert, "butler_calendar_change_seq", id=uuid4(), seq=0, **params)
    world.change(src, 1, ser)
    for seq in (1, 3):  # a duplicate and a gap
        world.refused(insert, "butler_calendar_change_seq", id=uuid4(), seq=seq, **params)
    world.change(src, 2, other, sequence=1)
    # duplicate application of the same entity, sequence and hash is refused even at the next seq
    world.refused(insert, "uq_calendar_change_applied", id=uuid4(), seq=3, **params)
    for statement, constraint in (
        (
            "UPDATE calendar_sync_state SET applied_seq=3, revision=revision+1, updated_at=:t WHERE source_id=:src",
            "butler_calendar_sync_applied_seq",
        ),
        (
            "UPDATE calendar_sync_state SET applied_seq=1, revision=revision+1, updated_at=:t WHERE source_id=:src",
            "butler_calendar_sync_applied_seq",
        ),
    ):
        world.refused(statement, constraint, src=src, t=now())
    # updates other than the NULL redaction, and any redaction on a live source, are refused
    world.refused(
        "UPDATE calendar_changes SET snapshot=NULL WHERE source_id=:src",
        "butler_calendar_change_sealed",
        src=src,
    )


def test_change_rows_and_the_counter_commit_together(world):
    src = world.source()
    ser = world.series(src)
    t = now()
    insert = (
        "INSERT INTO calendar_changes (id, source_id, owner_id, scope_key, seq, entity, series_id,"
        " operation, sequence, content_hash, sync_run_id, cursor_after, applied_at) VALUES (:id, :src,"
        " :o, 'household_shared', 1, 'series', :ser, 'upsert', 1, :h, :run, 'v1:1', :t)"
    )
    params = {
        "id": uuid4(),
        "src": src,
        "o": world.owner,
        "ser": ser,
        "h": UPSERT_HASH,
        "run": uuid4(),
        "t": t,
    }
    world.refused_txn([insert], "butler_calendar_change_counter", **params)
    assert world.scalar("SELECT count(*) FROM calendar_changes WHERE source_id=:s", s=src) == 0
    # the counter bumped with no row behind it is refused at the statement
    world.refused(
        "UPDATE calendar_sync_state SET applied_seq=1, revision=revision+1, updated_at=:t WHERE source_id=:src",
        "butler_calendar_sync_applied_seq",
        src=src,
        t=t,
    )


def test_delete_rows_carry_the_literal_tombstone_hash_and_nothing_else_does(world):
    src = world.source()
    ser = world.series(src)
    world.change(src, 1, ser, operation="delete")
    assert world.scalar("SELECT content_hash FROM calendar_changes WHERE source_id=:s", s=src) == (
        LITERAL_TOMBSTONE
    )
    assert codes.TOMBSTONE_HASH == LITERAL_TOMBSTONE
    insert = (
        "INSERT INTO calendar_changes (id, source_id, owner_id, scope_key, seq, entity, series_id,"
        " operation, sequence, content_hash, sync_run_id, cursor_after, applied_at) VALUES (:id, :src,"
        " :o, 'household_shared', 2, 'series', :ser, :op, 2, :h, :run, 'v1:1', :t)"
    )
    base = {"src": src, "o": world.owner, "ser": ser, "run": uuid4(), "t": now()}
    world.refused(insert, "ck_calendar_change_hash", id=uuid4(), op="delete", h=UPSERT_HASH, **base)
    world.refused(
        insert, "ck_calendar_change_hash", id=uuid4(), op="upsert", h=LITERAL_TOMBSTONE, **base
    )
    world.refused(
        insert, "ck_calendar_change_hash", id=uuid4(), op="revive", h=LITERAL_TOMBSTONE, **base
    )
    world.refused(
        insert, "ck_calendar_change_hash", id=uuid4(), op="upsert", h="XYZ" * 21 + "A", **base
    )
    count = (
        "INSERT INTO calendar_changes (id, source_id, owner_id, scope_key, seq, entity, series_id,"
        " operation, sequence, cascade_count, content_hash, sync_run_id, cursor_after, applied_at)"
        " VALUES (:id, :src, :o, 'household_shared', 2, :e, :ser, :op, 2, :n, :h, :run, 'v1:1', :t)"
    )
    for args in (
        {"e": "series", "op": "upsert", "n": 1},  # cascade_count only on delete or revive
        {"e": "series", "op": "delete", "n": 101},
        {"e": "series", "op": "delete", "n": -1},
    ):
        world.refused(
            count,
            "ck_calendar_change_cascade",
            id=uuid4(),
            h=LITERAL_TOMBSTONE if args["op"] == "delete" else UPSERT_HASH,
            **args,
            **base,
        )


# ------------------------------------------------------------------------------------------
# Sync-state guard
# ------------------------------------------------------------------------------------------
CLAIM = (
    "UPDATE calendar_sync_state SET claim_token=:token, claim_expires_at=now()+interval '120 seconds',"
    " last_attempt_at=now(), revision=revision+1, updated_at=:t WHERE source_id=:src"
)
SUCCESS = (
    "UPDATE calendar_sync_state SET cursor=:cursor, claim_token=NULL, claim_expires_at=NULL,"
    " status='ok', attempts=0, last_success_at=GREATEST(clock_timestamp(),"
    " COALESCE(last_success_at, '-infinity'::timestamptz) + interval '1 microsecond'),"
    " revision=revision+1, updated_at=:t WHERE source_id=:src"
)


def sync(world, src):
    return world.one(
        "SELECT status, cursor, applied_seq, claim_token, attempts, last_success_at, revision"
        " FROM calendar_sync_state WHERE source_id=:s",
        s=src,
    )


def test_the_worker_transition_is_accepted_and_every_other_cursor_change_is_refused(world):
    src = world.source()
    ser = world.series(src)
    world.change(src, 1, ser)
    now()
    # a bare cursor update, even though applied_seq already equals max(seq)
    world.refused(
        "UPDATE calendar_sync_state SET cursor='v1:9', revision=revision+1, updated_at=:t WHERE source_id=:src",
        "butler_calendar_sync_cursor",
        src=src,
        t=now(),
    )
    # advancing last_success_at without a held claim
    world.refused(
        "UPDATE calendar_sync_state SET cursor='v1:9', last_success_at=now(), revision=revision+1,"
        " updated_at=:t WHERE source_id=:src",
        "butler_calendar_sync_cursor",
        src=src,
        t=now(),
    )
    world.run(CLAIM, src=src, token=uuid4(), t=now())
    assert sync(world, src)[3] is not None
    # releasing the claim with a new cursor but without advancing last_success_at
    world.refused(
        "UPDATE calendar_sync_state SET cursor='v1:9', claim_token=NULL, claim_expires_at=NULL,"
        " revision=revision+1, updated_at=:t WHERE source_id=:src",
        "butler_calendar_sync_cursor",
        src=src,
        t=now(),
    )
    # a cursor change that keeps the claim held
    world.refused(
        "UPDATE calendar_sync_state SET cursor='v1:9', last_success_at=now(), revision=revision+1,"
        " updated_at=:t WHERE source_id=:src",
        "butler_calendar_sync_cursor",
        src=src,
        t=now(),
    )
    # the legitimate transition, with an ARBITRARY cursor value: the guard checks necessary
    # conditions only and claims nothing about the cursor's value (section 6.5)
    world.run(SUCCESS, src=src, cursor="not-even-a-real-cursor", t=now())
    status, cursor, applied, token, attempts, first, _revision = sync(world, src)
    assert (status, cursor, applied, token, attempts) == (
        "ok",
        "not-even-a-real-cursor",
        1,
        None,
        0,
    )
    # once a cursor exists it never becomes NULL outside the forgetting transition
    world.run(CLAIM, src=src, token=uuid4(), t=now())
    world.refused(
        SUCCESS.replace(":cursor", "NULL"), "butler_calendar_sync_cursor", src=src, t=now()
    )
    # last_success_at strictly advances on every write, even back to back
    world.run(CLAIM, src=src, token=uuid4(), t=now())
    world.run(SUCCESS, src=src, cursor="v1:1", t=now())
    assert sync(world, src)[5] > first
    # even when the stored value sits in the future (clock stepped back) the step is one microsecond
    world.run(CLAIM, src=src, token=uuid4(), t=now())
    world.run(
        "UPDATE calendar_sync_state SET last_success_at=now()+interval '1 day', claim_token=NULL,"
        " claim_expires_at=NULL, revision=revision+1, updated_at=:t WHERE source_id=:src",
        src=src,
        t=now(),
    )
    future = sync(world, src)[5]
    world.run(CLAIM, src=src, token=uuid4(), t=now())
    world.run(SUCCESS, src=src, cursor="v1:2", t=now())
    assert sync(world, src)[5] == future + timedelta(microseconds=1)
    # last_success_at never decreases
    world.run(CLAIM, src=src, token=uuid4(), t=now())
    world.refused(
        "UPDATE calendar_sync_state SET last_success_at=:old, claim_token=NULL, claim_expires_at=NULL,"
        " revision=revision+1, updated_at=:t WHERE source_id=:src",
        "butler_calendar_sync_cursor",
        src=src,
        old=first,
        t=now(),
    )


def test_applied_seq_never_decreases_and_never_exceeds_the_log(world):
    src = world.source()
    ser = world.series(src)
    other = world.series(src, uid="u2")
    world.change(src, 1, ser)
    world.change(src, 2, other)
    now()
    for value in (0, 1, 3, 5000):
        world.refused(
            "UPDATE calendar_sync_state SET applied_seq=:v, revision=revision+1, updated_at=:t WHERE source_id=:src",
            "butler_calendar_sync_applied_seq",
            v=value,
            src=src,
            t=now(),
        )
    assert sync(world, src)[2] == 2


def test_the_attempt_counter_resets_only_on_success_or_an_explicit_claim_of_a_failed_source(world):
    src = world.source()
    now()
    world.run(
        "UPDATE calendar_sync_state SET status='retry_wait', attempts=3, revision=revision+1,"
        " updated_at=:t WHERE source_id=:src",
        src=src,
        t=now(),
    )
    world.refused(
        "UPDATE calendar_sync_state SET attempts=0, revision=revision+1, updated_at=:t WHERE source_id=:src",
        "butler_calendar_sync_attempts",
        src=src,
        t=now(),
    )
    world.run(
        "UPDATE calendar_sync_state SET status='failed', attempts=5, revision=revision+1,"
        " updated_at=:t WHERE source_id=:src",
        src=src,
        t=now(),
    )
    world.run(  # the explicit owner claim of a failed source resets attempts to 0
        "UPDATE calendar_sync_state SET attempts=0, claim_token=:token,"
        " claim_expires_at=now()+interval '120 seconds', revision=revision+1, updated_at=:t"
        " WHERE source_id=:src",
        src=src,
        token=uuid4(),
        t=now(),
    )
    assert sync(world, src)[4] == 0


def test_sync_state_consistency_checks(world):
    src = world.source()
    now()
    bump = "revision=revision+1, updated_at=:t WHERE source_id=:src"
    for assignment, constraint in (
        ("status='blocked'", "ck_calendar_sync_blocked"),  # blocked needs a reason
        ("blocked_reason='cursor_invalid'", "ck_calendar_sync_blocked"),  # and only when blocked
        ("status='blocked', blocked_reason='not_a_code'", "ck_calendar_sync_blocked_reason"),
        ("last_error_code='boom'", "ck_calendar_sync_error"),
        ("claim_token=gen_random_uuid()", "ck_calendar_sync_claim"),
        ("attempts=6", "ck_calendar_sync_attempts"),
        ("status='nope'", "ck_calendar_sync_status"),
        ("blocked_detail=CAST('{}' AS jsonb)", "ck_calendar_sync_detail"),
        (
            "status='blocked', blocked_reason='cursor_invalid', blocked_detail=CAST(:big AS jsonb)",
            "ck_calendar_sync_detail",
        ),
    ):
        world.refused(
            f"UPDATE calendar_sync_state SET {assignment}, {bump}",
            constraint,
            src=src,
            t=now(),
            big=json.dumps({"x": "y" * 1100}),
        )
    world.run(
        "UPDATE calendar_sync_state SET status='blocked', blocked_reason='cursor_invalid',"
        f" blocked_detail=CAST(:d AS jsonb), {bump}",
        src=src,
        t=now(),
        d=json.dumps({"code": "cursor_invalid"}),
    )
    world.refused(  # revision must advance by exactly one
        "UPDATE calendar_sync_state SET status='ok', blocked_reason=NULL, blocked_detail=NULL,"
        " revision=revision+2, updated_at=:t WHERE source_id=:src",
        "butler_calendar_sync_revision",
        src=src,
        t=now(),
    )
    world.refused(  # a new sync state starts as never / empty
        "INSERT INTO calendar_sync_state (source_id, owner_id, scope_key, status, applied_seq,"
        " attempts, revision, updated_at) SELECT :src, owner_id, scope_key, 'ok', 0, 0, 1, :t"
        " FROM calendar_provider_links WHERE source_id=:src",
        "butler_calendar_sync_insert",
        src=src,
        t=now(),
    )


# ------------------------------------------------------------------------------------------
# Forgetting and exclusivity
# ------------------------------------------------------------------------------------------
FORGET_SOURCE = (
    "UPDATE calendar_sources SET state='forgotten', data=NULL, revision=revision+:bump,"
    " updated_at=:t WHERE id=:src"
)
SCRUB = (
    (
        "UPDATE calendar_series SET state='forgotten', uid=NULL, kind=NULL, status=NULL, title=NULL,"
        " start_local=NULL, start_date=NULL, zone=NULL, duration_seconds=NULL, duration_days=NULL,"
        " rule=NULL, exdates=NULL, rdates=NULL, provider_version=NULL, deleted_at=NULL,"
        " revision=revision+1, updated_at=:t WHERE source_id=:src"
    ),
    (
        "UPDATE calendar_overrides SET state='forgotten', deleted_by_cascade=false, status=NULL,"
        " start_wall=NULL, duration=NULL, title=NULL, deleted_at=NULL, revision=revision+1,"
        " updated_at=:t WHERE source_id=:src"
    ),
    "UPDATE calendar_changes SET snapshot=NULL WHERE source_id=:src",
    "UPDATE calendar_provider_links SET provider_ref=NULL WHERE source_id=:src",
    (
        "UPDATE calendar_sync_state SET status='blocked', blocked_reason='source_forgotten', cursor=NULL,"
        " claim_token=NULL, claim_expires_at=NULL, blocked_detail=NULL, next_attempt_at=NULL,"
        " revision=revision+1, updated_at=:t WHERE source_id=:src"
    ),
)


def seeded_source(world):
    src = world.source()
    ser = world.series(src, sequence=2)
    ovr = world.override(src, ser, sequence=3)
    gone = world.series(src, uid="u2", sequence=1, state="deleted")
    world.change(src, 1, ser)
    return src, ser, ovr, gone


def forget(world, src, *, skip=None, bump=1, t=None):
    t = t or now()
    with world.rt.begin() as c:
        c.execute(text(FORGET_SOURCE), {"src": src, "t": t, "bump": bump})
        for index, sql in enumerate(SCRUB):
            if index != skip:
                c.execute(text(sql), {"src": src, "t": t})


def test_forgetting_a_provider_source_commits_only_when_completely_scrubbed(world):
    src, ser, ovr, _gone = seeded_source(world)
    now()
    # one scrub step missing at a time: the commit is refused and nothing is kept
    for skip in range(len(SCRUB)):
        before = world.fingerprint()
        with pytest.raises(DBAPIError) as caught:
            forget(world, src, skip=skip)
        assert caught.value.orig.diag.constraint_name in {
            "butler_calendar_provider_scrubbed",
            None,
        }, caught.value.orig.diag.message_primary
        assert world.fingerprint() == before
    forget(world, src, t=now())
    assert world.one("SELECT state, data, revision FROM calendar_sources WHERE id=:s", s=src) == (
        "forgotten",
        None,
        2,
    )
    assert world.one(
        "SELECT status, blocked_reason, cursor, applied_seq FROM calendar_sync_state WHERE source_id=:s",
        s=src,
    ) == ("blocked", "source_forgotten", None, 1)
    assert (
        world.scalar("SELECT provider_ref FROM calendar_provider_links WHERE source_id=:s", s=src)
        is None
    )
    assert (
        world.scalar(
            "SELECT count(*) FROM calendar_series WHERE source_id=:s AND (state<>'forgotten' OR uid IS NOT NULL)",
            s=src,
        )
        == 0
    )
    # a terminal sync-state row is immutable, even from a later transaction
    world.refused(
        "UPDATE calendar_sync_state SET attempts=0, revision=revision+1, updated_at=:t WHERE source_id=:src",
        "butler_calendar_sync_terminal",
        src=src,
        t=now(),
    )
    # and so are the scrubbed rows and the source itself
    world.refused(REVIVE_SERIES, "butler_calendar_series_terminal", id=ser, seq=9, t=now())
    world.refused(REVIVE_OVERRIDE, "butler_calendar_override_terminal", id=ovr, seq=9, t=now())
    world.refused(
        "UPDATE calendar_sources SET revision=revision+1, updated_at=:t WHERE id=:id",
        sqlstate="23514",
        id=src,
        t=now(),
    )


def test_exact_forgetting_columns_sync_state(world):
    """Each deviation of the terminal statement is refused by the sync-state guard."""
    cases = {
        "cursor kept": "status='blocked', blocked_reason='source_forgotten', cursor='v1:1', claim_token=NULL, claim_expires_at=NULL, blocked_detail=NULL, next_attempt_at=NULL, revision=revision+1",
        "applied_seq changed": "status='blocked', blocked_reason='source_forgotten', cursor=NULL, claim_token=NULL, claim_expires_at=NULL, blocked_detail=NULL, next_attempt_at=NULL, applied_seq=0, revision=revision+1",
        "last_success_at changed": "status='blocked', blocked_reason='source_forgotten', cursor=NULL, claim_token=NULL, claim_expires_at=NULL, blocked_detail=NULL, next_attempt_at=NULL, last_success_at=now(), revision=revision+1",
        "attempts changed": "status='blocked', blocked_reason='source_forgotten', cursor=NULL, claim_token=NULL, claim_expires_at=NULL, blocked_detail=NULL, next_attempt_at=NULL, attempts=2, revision=revision+1",
        "last_attempt_at changed": "status='blocked', blocked_reason='source_forgotten', cursor=NULL, claim_token=NULL, claim_expires_at=NULL, blocked_detail=NULL, next_attempt_at=NULL, last_attempt_at=now(), revision=revision+1",
        "last_error_code changed": "status='blocked', blocked_reason='source_forgotten', cursor=NULL, claim_token=NULL, claim_expires_at=NULL, blocked_detail=NULL, next_attempt_at=NULL, last_error_code='provider_timeout', revision=revision+1",
        "revision + 2": "status='blocked', blocked_reason='source_forgotten', cursor=NULL, claim_token=NULL, claim_expires_at=NULL, blocked_detail=NULL, next_attempt_at=NULL, revision=revision+2",
        "next_attempt_at kept": "status='blocked', blocked_reason='source_forgotten', cursor=NULL, claim_token=NULL, claim_expires_at=NULL, blocked_detail=NULL, next_attempt_at=now(), revision=revision+1",
        "claim kept": "status='blocked', blocked_reason='source_forgotten', cursor=NULL, claim_token=gen_random_uuid(), claim_expires_at=now(), blocked_detail=NULL, next_attempt_at=NULL, revision=revision+1",
        "detail kept": "status='blocked', blocked_reason='source_forgotten', cursor=NULL, claim_token=NULL, claim_expires_at=NULL, blocked_detail=CAST('{}' AS jsonb), next_attempt_at=NULL, revision=revision+1",
    }
    for name, assignment in cases.items():
        src, *_ = seeded_source(world)
        t = now()
        world.run(CLAIM, src=src, token=uuid4(), t=t)
        world.run(SUCCESS, src=src, cursor="v1:1", t=t)
        before = world.fingerprint()
        with pytest.raises(DBAPIError) as caught, world.rt.begin() as c:
            c.execute(text(FORGET_SOURCE), {"src": src, "t": t, "bump": 1})
            for sql in SCRUB[:4]:
                c.execute(text(sql), {"src": src, "t": t})
            c.execute(
                text(
                    f"UPDATE calendar_sync_state SET {assignment}, updated_at=:t WHERE source_id=:src"
                ),
                {"src": src, "t": t},
            )
        constraint = caught.value.orig.diag.constraint_name
        assert constraint in {
            "butler_calendar_sync_forget",
            "butler_calendar_sync_revision",
            "ck_calendar_sync_blocked",
            "ck_calendar_sync_claim",
            "ck_calendar_sync_detail",
        }, (name, constraint, caught.value.orig.diag.message_primary)
        assert world.fingerprint() == before, name
    # a decreasing updated_at is refused as a revision violation
    src, *_ = seeded_source(world)
    with pytest.raises(DBAPIError) as caught, world.rt.begin() as c:
        c.execute(text(FORGET_SOURCE), {"src": src, "t": now(), "bump": 1})
        for sql in SCRUB[:4]:
            c.execute(text(sql), {"src": src, "t": now()})
        c.execute(
            text(
                "UPDATE calendar_sync_state SET status='blocked', blocked_reason='source_forgotten',"
                " cursor=NULL, claim_token=NULL, claim_expires_at=NULL, blocked_detail=NULL,"
                " next_attempt_at=NULL, revision=revision+1, updated_at='2000-01-01' WHERE source_id=:src"
            ),
            {"src": src},
        )
    assert caught.value.orig.diag.constraint_name == "butler_calendar_sync_revision"


def test_the_terminal_state_is_refused_while_the_source_is_not_forgotten(world):
    src = world.source()
    world.refused(
        SCRUB[4],
        "butler_calendar_sync_forget",
        src=src,
        t=now(),
    )
    world.refused(
        SCRUB[3],
        "butler_calendar_link_immutable",
        src=src,
    )


def test_exclusivity_trigger_refuses_everything_but_the_forgetting_transition(world):
    src = world.source()
    t = now()
    # manual import and any data change of a provider-mode source
    world.refused(
        "UPDATE calendar_sources SET data=CAST(:d AS jsonb), revision=revision+1, updated_at=:t WHERE id=:id",
        "butler_calendar_provider_exclusive",
        id=src,
        t=t,
        d=json.dumps({"status": "ready", "label": "Synthetic provider", "window": {"x": 1}}),
    )
    world.refused(
        "UPDATE calendar_sources SET data=CAST(:d AS jsonb), revision=revision+1, updated_at=:t WHERE id=:id",
        "butler_calendar_provider_exclusive",
        id=src,
        t=t,
        d=json.dumps({"status": "offline", "label": "Synthetic provider"}),
    )
    # forgetting with the wrong revision step, clock, data or identity is refused (by the sealed
    # calendar guard or by the exclusivity trigger, both of which stay in force)
    for assignment, params in (
        ("state='forgotten', data=NULL, revision=revision+2, updated_at=:t", {}),
        ("state='forgotten', data=NULL, revision=revision+1, updated_at=:old", {}),
        ("state='forgotten', data=CAST('{}' AS jsonb), revision=revision+1, updated_at=:t", {}),
        ("state='forgotten', data=NULL, revision=revision+1, updated_at=:t, owner_id=:other", {}),
        (
            "state='forgotten', data=NULL, revision=revision+1, updated_at=:t, scope_key='member_a_private'",
            {},
        ),
        ("state='forgotten', data=NULL, revision=revision+1, updated_at=:t, created_at=:old", {}),
        ("state='active', data=NULL, revision=revision+1, updated_at=:t", {}),
    ):
        error = world.refused(
            f"UPDATE calendar_sources SET {assignment} WHERE id=:id",
            id=src,
            t=t,
            old=t - timedelta(days=1),
            other=world.other,
            **params,
        )
        assert error.orig.sqlstate in {"23514", "23503"}
    # a forget that scrubs nothing cannot commit
    world.refused_txn([FORGET_SOURCE], "butler_calendar_provider_scrubbed", src=src, t=t, bump=1)
    # an unlinked legacy source is unaffected
    legacy = world.source(link=False)
    world.run(
        "UPDATE calendar_sources SET data=CAST(:d AS jsonb), revision=revision+1, updated_at=:t WHERE id=:id",
        id=legacy,
        t=now(),
        d=json.dumps({"status": "ready", "label": "Synthetic provider"}),
    )
    world.run(FORGET_SOURCE, src=legacy, t=now(), bump=1)
    assert world.scalar("SELECT state FROM calendar_sources WHERE id=:s", s=legacy) == "forgotten"


def test_a_provider_link_needs_an_unconfigured_unforgotten_source(world):
    t = now()
    link = (
        "INSERT INTO calendar_provider_links (source_id, owner_id, scope_key, provider_kind,"
        " provider_ref, created_at) VALUES (:src, :o, 'household_shared', 'synthetic', :ref, :t)"
    )
    imported = world.source(link=False)
    world.run(
        "UPDATE calendar_sources SET data=CAST(:d AS jsonb), revision=revision+1, updated_at=:t WHERE id=:id",
        id=imported,
        t=now(),
        d=json.dumps({"status": "ready", "label": "Synthetic provider"}),
    )
    world.refused(
        link, "butler_calendar_link_unconfigured", src=imported, o=world.owner, ref="household", t=t
    )
    forgotten = world.source(link=False)
    world.run(FORGET_SOURCE, src=forgotten, t=now(), bump=1)
    world.refused(
        link,
        "butler_calendar_link_unconfigured",
        src=forgotten,
        o=world.owner,
        ref="household",
        t=t,
    )
    fresh = world.source(link=False)
    for ref in ("../etc/passwd", "UPPER", "a b", "x" * 65, "", "a/b"):
        world.refused(link, None, src=fresh, o=world.owner, ref=ref, t=t)
    world.refused(
        link, "butler_calendar_link_unconfigured", src=fresh, o=world.owner, ref=None, t=t
    )
    world.refused(
        link.replace("'synthetic'", "'google'"),
        "ck_calendar_link_kind",
        src=fresh,
        o=world.owner,
        ref="household",
        t=t,
    )
    world.run(link, src=fresh, o=world.owner, ref="household", t=t)
    world.refused(link, None, src=fresh, o=world.owner, ref="household", t=t)  # one link per source


# ------------------------------------------------------------------------------------------
# Limits
# ------------------------------------------------------------------------------------------
def test_series_limits_are_200_active_and_400_total(world):
    src = world.source()
    with world.rt.begin() as c:
        for index in range(200):
            world.series(src, uid=f"a{index}", conn=c)
    world.refused_txn(
        [
            (
                "INSERT INTO calendar_series (id, source_id, owner_id, scope_key, uid, state, kind, status,"
                " sequence, title, start_local, zone, duration_seconds, exdates, rdates, revision,"
                " created_at, updated_at) VALUES (gen_random_uuid(), :src, :o, 'household_shared', 'over',"
                " 'active', 'timed', 'confirmed', 1, 'T', '2026-03-15 09:00:00', 'UTC', 60,"
                " CAST('[]' AS jsonb), CAST('[]' AS jsonb), 1, now(), now())"
            )
        ],
        "butler_calendar_series_limit",
        src=src,
        o=world.owner,
    )
    with world.rt.begin() as c:  # tombstones fill the total up to 400
        for index in range(200):
            world.series(src, uid=f"d{index}", state="deleted", conn=c)
    world.refused_txn(
        [
            (
                "INSERT INTO calendar_series (id, source_id, owner_id, scope_key, uid, state, sequence,"
                " revision, created_at, updated_at, deleted_at) VALUES (gen_random_uuid(), :src, :o,"
                " 'household_shared', 'over', 'deleted', 1, 1, now(), now(), now())"
            )
        ],
        "butler_calendar_series_limit",
        src=src,
        o=world.owner,
    )
    revive = world.scalar("SELECT id FROM calendar_series WHERE source_id=:s AND uid='d0'", s=src)
    world.refused(REVIVE_SERIES, "butler_calendar_series_limit", id=revive, seq=2, t=now())
    assert world.scalar("SELECT count(*) FROM calendar_series WHERE source_id=:s", s=src) == 400
    other = world.source()  # limits are per source
    world.series(other)


def test_override_limits_are_100_active_and_200_total_per_series(world):
    src = world.source()
    ser = world.series(src)
    with world.rt.begin() as c:
        for index in range(100):
            world.override(
                src, ser, rid=f"2026-01-01T{index // 60:02d}:{index % 60:02d}:00", conn=c
            )
    base = (
        "INSERT INTO calendar_overrides (id, series_id, source_id, owner_id, scope_key, recurrence_id,"
        " state, {cols} sequence, revision, created_at, updated_at{extra}) VALUES (gen_random_uuid(),"
        " :ser, :src, :o, 'household_shared', :rid, {values} 1, 1, now(), now(){dextra})"
    )
    active = base.format(cols="status,", values="'active', 'cancelled',", extra="", dextra="")
    world.refused_txn(
        [active],
        "butler_calendar_override_limit",
        ser=ser,
        src=src,
        o=world.owner,
        rid="2027-01-01T00:00:00",
    )
    with world.rt.begin() as c:
        for index in range(100):
            world.override(
                src,
                ser,
                rid=f"2026-02-01T{index // 60:02d}:{index % 60:02d}:00",
                state="deleted",
                conn=c,
            )
    deleted = base.format(cols="", values="'deleted',", extra=", deleted_at", dextra=", now()")
    world.refused_txn(
        [deleted],
        "butler_calendar_override_limit",
        ser=ser,
        src=src,
        o=world.owner,
        rid="2027-01-01T00:00:00",
    )
    assert world.scalar("SELECT count(*) FROM calendar_overrides WHERE series_id=:s", s=ser) == 200
    revive = world.scalar(
        "SELECT id FROM calendar_overrides WHERE series_id=:s AND state='deleted' LIMIT 1", s=ser
    )
    world.refused(REVIVE_OVERRIDE, "butler_calendar_override_limit", id=revive, seq=2, t=now())
    other = world.series(src, uid="other")  # limits are per series
    world.override(src, other)


# ------------------------------------------------------------------------------------------
# Concurrency, crash and recovery
# ------------------------------------------------------------------------------------------
def test_concurrent_change_inserts_serialize_on_the_source_lock(world):
    src = world.source()
    ser = world.series(src)
    ready, release = threading.Event(), threading.Event()
    outcome = {}

    def first():
        with world.rt.begin() as c:
            world.change(src, 1, ser, conn=c)
            ready.set()
            release.wait(5)

    def second():
        ready.wait(5)
        try:
            world.change(src, 1, ser)  # computed from the same stale max, must not be accepted
            outcome["second"] = "accepted"
        except DBAPIError as error:
            outcome["second"] = error.orig.diag.constraint_name

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    ready.wait(5)
    time.sleep(0.3)  # the second insert is now waiting on the source row lock
    waiting = world.scalar(
        "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%calendar_changes%'"
    )
    release.set()
    for thread in threads:
        thread.join(10)
    assert waiting == 1
    assert outcome["second"] == "butler_calendar_change_seq"
    assert world.scalar("SELECT max(seq) FROM calendar_changes WHERE source_id=:s", s=src) == 1
    assert (
        world.scalar("SELECT applied_seq FROM calendar_sync_state WHERE source_id=:s", s=src) == 1
    )


def invariant_holds(world, series_id, override_id):
    """The floor / origin coupling and lifecycle facts that must hold in every committed state."""
    row = world.one(
        "SELECT o.state, o.deleted_by_cascade, o.deleted_at IS NOT NULL, s.state"
        " FROM calendar_overrides o JOIN calendar_series s ON s.id=o.series_id WHERE o.id=:o",
        o=override_id,
    )
    state, cascade, has_deleted_at, series_state = row
    assert (state == "deleted") == has_deleted_at
    assert not cascade or state == "deleted"
    assert not (state == "active" and series_state != "active")


@pytest.mark.parametrize("attempt", range(4))
def test_cascade_and_explicit_override_writes_never_leave_an_invalid_state(world, attempt):
    """Writers that follow the lock protocol (source first) serialize; one that does not may
    deadlock, but never commits an invalid state."""
    src = world.source()
    ser = world.series(src, sequence=2)
    ovr = world.override(src, ser, sequence=3)
    t = now()
    errors = []

    def cascade():
        try:
            with world.rt.begin() as c:
                c.execute(
                    text("SELECT id FROM calendar_sources WHERE id=:s FOR UPDATE"), {"s": src}
                )
                c.execute(text(DELETE_SERIES), {"id": ser, "seq": 5, "t": t})
                c.execute(text(DELETE_OVERRIDE), {"id": ovr, "cascade": True, "seq": 3, "t": t})
        except DBAPIError as error:
            errors.append(("cascade", error.orig.sqlstate, error.orig.diag.constraint_name))

    def explicit():
        try:
            with world.rt.begin() as c:
                c.execute(
                    text("SELECT id FROM calendar_sources WHERE id=:s FOR UPDATE"), {"s": src}
                )
                c.execute(text(DELETE_OVERRIDE), {"id": ovr, "cascade": False, "seq": 4, "t": t})
        except DBAPIError as error:
            errors.append(("explicit", error.orig.sqlstate, error.orig.diag.constraint_name))

    threads = [threading.Thread(target=cascade), threading.Thread(target=explicit)]
    if attempt % 2:
        threads.reverse()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    invariant_holds(world, ser, ovr)
    state = override_state(world, ovr)
    # whichever order won, the floor and its origin are coupled in the committed row
    if state[1]:
        assert state[2] == 3  # a cascade tombstone keeps the sequence of its last upsert
    # the explicit delete either committed (floor 4, flag false) or was refused by the series
    # state; the series delete cannot have left an active override behind
    assert all(code in {"23514", "40P01"} for _, code, _ in errors), errors


def test_a_dropped_connection_mid_cascade_leaves_nothing_behind(world):
    src = world.source()
    ser = world.series(src, sequence=2)
    ovr = world.override(src, ser, sequence=3)
    before = world.fingerprint()
    connection = world.rt.connect()
    transaction = connection.begin()
    connection.execute(text(DELETE_SERIES), {"id": ser, "seq": 5, "t": now()})
    pid = connection.execute(text("SELECT pg_backend_pid()")).scalar()
    with world.admin.begin() as admin:
        admin.execute(text("SELECT pg_terminate_backend(:p)"), {"p": pid})
    with pytest.raises(DBAPIError):
        connection.execute(
            text(DELETE_OVERRIDE), {"id": ovr, "cascade": True, "seq": 3, "t": now()}
        )
    try:
        transaction.rollback()
    except DBAPIError:
        pass
    connection.close()
    assert world.fingerprint() == before
    invariant_holds(world, ser, ovr)
    # recovery: the same cascade can be applied afterwards in a fresh transaction
    with world.rt.begin() as c:
        c.execute(text(DELETE_SERIES), {"id": ser, "seq": 5, "t": now()})
        c.execute(text(DELETE_OVERRIDE), {"id": ovr, "cascade": True, "seq": 3, "t": now()})
    assert override_state(world, ovr)[:3] == ("deleted", True, 3)


CRASH_SCRIPT = """
import os, sys, psycopg
dsn, series, override = sys.argv[1:4]
with psycopg.connect(dsn, autocommit=False) as c:
    c.execute("UPDATE calendar_series SET state='deleted', sequence=5, kind=NULL, status=NULL,"
              " title=NULL, start_local=NULL, zone=NULL, duration_seconds=NULL, exdates=NULL,"
              " rdates=NULL, deleted_at=now(), revision=revision+1, updated_at=now() WHERE id=%s", (series,))
    c.execute("UPDATE calendar_overrides SET state='deleted', deleted_by_cascade=true, status=NULL,"
              " deleted_at=now(), revision=revision+1, updated_at=now() WHERE id=%s", (override,))
    os._exit(9)  # the process dies with both writes uncommitted
"""


def test_a_real_process_crash_before_commit_rolls_back_the_whole_cascade(world, runtime_engine):
    src = world.source()
    ser = world.series(src, sequence=2)
    ovr = world.override(src, ser, sequence=3)
    before = world.fingerprint()
    url = runtime_engine.url.render_as_string(hide_password=False).replace("+psycopg", "")
    done = subprocess.run(
        [sys.executable, "-I", "-c", CRASH_SCRIPT, url, str(ser), str(ovr)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ},
    )
    assert done.returncode == 9, done.stderr
    assert world.fingerprint() == before
    assert settings.postgres_db.startswith("butler_test")
    invariant_holds(world, ser, ovr)


def test_a_crash_during_forgetting_keeps_the_source_fully_live_and_recoverable(world):
    src, _ser, _ovr, _gone = seeded_source(world)
    before = world.fingerprint()
    connection = world.rt.connect()
    transaction = connection.begin()
    t = now()
    connection.execute(text(FORGET_SOURCE), {"src": src, "t": t, "bump": 1})
    connection.execute(text(SCRUB[0]), {"src": src, "t": t})
    pid = connection.execute(text("SELECT pg_backend_pid()")).scalar()
    with world.admin.begin() as admin:
        admin.execute(text("SELECT pg_terminate_backend(:p)"), {"p": pid})
    with pytest.raises(DBAPIError):
        connection.execute(text(SCRUB[1]), {"src": src, "t": t})
    try:
        transaction.rollback()
    except DBAPIError:
        pass
    connection.close()
    assert world.fingerprint() == before  # no half-forgotten source exists
    assert world.scalar("SELECT state FROM calendar_sources WHERE id=:s", s=src) == "active"
    forget(world, src)  # the retried forget commits completely
    assert world.scalar("SELECT state FROM calendar_sources WHERE id=:s", s=src) == "forgotten"


def test_downgrade_removes_every_new_object_and_reupgrade_restores_them(world):
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]

    def migrate(*args):
        result = subprocess.run(
            ["alembic", *args], cwd=backend, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def objects():
        return world.one(
            "SELECT (SELECT count(*) FROM pg_proc WHERE proname LIKE 'butler_calendar\\_%'),"
            " (SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'butler\\_calendar\\_%'"
            "   AND NOT tgisinternal),"
            " (SELECT count(*) FROM pg_class WHERE relname IN ('calendar_provider_links',"
            "   'calendar_series','calendar_overrides','calendar_changes','calendar_sync_state',"
            "   'uq_calendar_source_identity'))"
        )

    legacy = world.source(link=False)
    linked = world.source()
    world.series(linked)
    assert objects() == (10, 23, 6)
    migrate("downgrade", "0034_invoice_filing_execution")
    # only the pre-existing guards of the sealed legacy tables remain
    assert objects() == (0, 4, 0)
    assert world.scalar("SELECT state FROM calendar_sources WHERE id=:s", s=legacy) == "active"
    assert world.scalar("SELECT state FROM calendar_sources WHERE id=:s", s=linked) == "active"
    migrate("upgrade", "head")
    migrate("check")
    with world.admin.begin() as connection:  # new tables need the restricted role's grants again
        configure(connection.connection.driver_connection, RUNTIME_PASSWORD)
    assert objects() == (10, 23, 6)
    assert (
        world.scalar("SELECT count(*) FROM calendar_series") == 0
    )  # provider data is lost by design
    assert world.scalar("SELECT state FROM calendar_sources WHERE id=:s", s=legacy) == "active"
    # the exclusivity trigger applies to a re-linked source again
    relinked = world.source()
    world.refused(
        "UPDATE calendar_sources SET data=CAST(:d AS jsonb), revision=revision+1, updated_at=:t"
        " WHERE id=:id",
        "butler_calendar_provider_exclusive",
        id=relinked,
        t=now(),
        d=json.dumps({"status": "ready", "label": "Synthetic provider"}),
    )
