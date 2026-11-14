"""Spec 072: the count-only audit projection under the real restricted runtime role."""

import subprocess
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app import identity
from app.manage import set_scope
from app.models import AuditEvent, User

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[2]
CATEGORIES = [
    "sign_in",
    "denied_access",
    "access_change",
    "recovery_admin",
    "other_admin",
    "operations_read",
    "other_security",
]
# (event_type, result_status, expected category, expected outcome)
CASES = [
    ("auth.login", "success", "sign_in", "success"),
    ("auth.logout", "success", "sign_in", "success"),
    ("auth.session_bootstrap", "success", "sign_in", "success"),
    ("auth.login_denied", "denied", "denied_access", "denied"),
    ("auth.rate_limited", "denied", "denied_access", "denied"),
    ("operations.session_denied", "denied", "denied_access", "denied"),
    ("admin.user_created", "success", "access_change", "success"),
    ("admin.scope_changed", "success", "access_change", "success"),
    ("admin.recovery_assessed", "success", "recovery_admin", "success"),
    ("admin.restored_sessions_revoked", "success", "recovery_admin", "success"),
    ("admin.work_restore_quarantined", "success", "recovery_admin", "success"),
    ("admin.work_storage_provisioned", "success", "other_admin", "success"),
    ("admin.brand_new_event", "success", "other_admin", "success"),
    ("operations.read", "success", "operations_read", "success"),
    ("operations.audit_summary", "success", "operations_read", "success"),
    ("auth.scope_read", "success", "other_security", "success"),
    ("auth.brand_new_event", "success", "other_security", "success"),
    ("operations.brand_new_event", "success", "other_security", "success"),
    ("auth.login", "failed", "sign_in", "other"),
    ("admin.user_status_changed", "weird_status", "access_change", "other"),
]
# Never counted: content-domain activity, lookalike prefixes and unrelated families.
EXCLUDED = [
    "documents.read",
    "tasks.created",
    "work.confirmation_status",
    "authx.login",
    "admins.x",
]


def grant(admin, uid, on=True):
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "technical_admin", on)


def summary(admin, uid, end, hours=24):
    with admin() as db:
        rows = db.execute(
            text("SELECT * FROM public.butler_audit_summary(:a,:e,:h)"),
            {"a": uid, "e": end, "h": hours},
        ).all()
    return {(r[0], r[1]): r[2] for r in rows}


def insert(admin, uid, event_type, status, when):
    with admin.begin() as db:
        db.add(
            AuditEvent(
                environment="test",
                initiator_type="human",
                initiator_id=str(uuid4()),
                scope_key="technical_admin",
                event_type=event_type,
                result_status=status,
                occurred_at=when,
                entity_id="synthetic-private-entity",
                metadata_json={"secret": "synthetic-private-body"},
                source_context={"body": "synthetic-private-source"},
            )
        )


def request(client, headers, **body):
    return client.post(
        "/api/v1/operations/audit-summary",
        headers=headers,
        json={"scope": "technical_admin", "window": "24h", **body},
    )


def test_mapping_window_and_exclusions_are_exact(scenario):
    _, _, _, admin, uid = scenario
    grant(admin, uid)
    end = identity.now_utc()
    before = summary(admin, uid, end)
    wide_before = summary(admin, uid, end, 168)
    inside = end - timedelta(hours=1)
    for event_type, status, _, _ in CASES:
        insert(admin, uid, event_type, status, inside)
    for event_type in EXCLUDED:
        insert(admin, uid, event_type, "success", inside)
    # Outside 24 hours but inside 7 days, and beyond 7 days, and in the future.
    insert(admin, uid, "auth.login", "success", end - timedelta(hours=30))
    insert(admin, uid, "auth.login", "success", end - timedelta(hours=200))
    insert(admin, uid, "auth.login", "success", end + timedelta(hours=1))
    after = summary(admin, uid, end)
    wide_after = summary(admin, uid, end, 168)
    expected: dict = {}
    for _, _, category, outcome in CASES:
        expected[(category, outcome)] = expected.get((category, outcome), 0) + 1
    delta = {
        key: after.get(key, 0) - before.get(key, 0)
        for key in set(after) | set(before)
        if after.get(key, 0) != before.get(key, 0)
    }
    assert delta == expected
    wide = {
        key: wide_after.get(key, 0) - wide_before.get(key, 0)
        for key in set(wide_after) | set(wide_before)
        if wide_after.get(key, 0) != wide_before.get(key, 0)
    }
    assert wide == {**expected, ("sign_in", "success"): expected[("sign_in", "success")] + 1}
    assert {category for category, _ in after} <= set(CATEGORIES)
    grant(admin, uid, False)


def refuse(engine, statement, match=None, **params):
    with pytest.raises(DBAPIError, match=match), engine.begin() as db:
        db.execute(text(statement), params)


CALL = "SELECT * FROM public.butler_audit_summary(:a,:e,:h)"


def test_function_guards_and_privileges(scenario, runtime_engine, postgres_engine):
    _client, _, _, admin, uid = scenario
    end = identity.now_utc()
    with postgres_engine.connect() as db:
        proc = db.execute(
            text(
                "SELECT prosecdef, provolatile, proconfig, "
                "has_function_privilege('butler_runtime', oid, 'EXECUTE'), "
                "has_function_privilege('public', oid, 'EXECUTE'), pg_get_userbyid(proowner) "
                "FROM pg_proc WHERE proname='butler_audit_summary'"
            )
        ).one()
        assert proc[0] is True and proc[1] == "s" and proc[2] == ["search_path=pg_catalog"]
        assert proc[3] is True and proc[4] is False
        assert proc[5] != "butler_runtime"
    # Without the current technical_admin grant the projection refuses.
    refuse(runtime_engine, CALL, "Technical administration is required", a=uid, e=end, h=24)
    grant(admin, uid)
    try:
        for hours in (0, 23, 25, 167, 169, 720):
            refuse(runtime_engine, CALL, "Unsupported audit summary window", a=uid, e=end, h=hours)
        refuse(
            runtime_engine,
            "SELECT * FROM public.butler_audit_summary(:a,NULL,24)",
            "Unsupported audit summary window",
            a=uid,
        )
        # Another actor id that does not hold the grant is refused.
        refuse(runtime_engine, CALL, "Technical administration is required", a=uuid4(), e=end, h=24)
        # The runtime role still has no table access to the audit history.
        refuse(runtime_engine, "SELECT occurred_at FROM public.audit_events LIMIT 1")
        refuse(runtime_engine, "SELECT count(*) FROM public.audit_events")
        # Append-only triggers are unchanged.
        refuse(
            postgres_engine,
            "DELETE FROM public.audit_events WHERE id IN (SELECT id FROM public.audit_events LIMIT 1)",
            "append-only",
        )
    finally:
        grant(admin, uid, False)


def test_api_shape_denials_and_metadata_only_audit(scenario):
    client, h, _, admin, uid = scenario
    assert request(client, h).status_code == 403
    grant(admin, uid)
    try:
        assert request(client, {}).status_code == 403
        assert request(client, {**h, "Origin": "https://invalid.example"}).status_code == 403
        for bad in ({"window": "30d"}, {"window": ""}, {"extra": 1}, {"scope": "household_shared"}):
            assert request(client, h, **bad).status_code == 422
        with admin() as db:
            before = db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "operations.audit_summary",
                    AuditEvent.initiator_id == str(uid),
                )
            )
        response = request(client, h, window="7d")
        assert response.status_code == 200, response.text
        body = response.json()
        assert list(body) == [
            "schema_version",
            "scope",
            "actor_id",
            "checked_at",
            "valid_until",
            "window",
            "window_start",
            "window_end",
            "categories",
            "totals",
            "excludes",
        ]
        assert body["actor_id"] == str(uid) and body["window"] == "7d"
        assert [c["key"] for c in body["categories"]] == CATEGORIES
        assert all(list(c) == ["key", "success", "denied", "other"] for c in body["categories"])
        assert body["totals"] == {
            o: sum(c[o] for c in body["categories"]) for o in ("success", "denied", "other")
        }
        assert body["excludes"] == [
            "content_domain_events",
            "overdue_jobs",
            "capacity",
            "per_event_detail",
        ]
        assert "synthetic-private" not in response.text
        with admin() as db:
            rows = list(
                db.scalars(
                    select(AuditEvent).where(
                        AuditEvent.event_type == "operations.audit_summary",
                        AuditEvent.initiator_id == str(uid),
                    )
                )
            )
        assert len(rows) == before + 1
        assert rows[-1].metadata_json == {"window": "7d"} or any(
            r.metadata_json == {"window": "7d"} for r in rows
        )
        # The summary excludes the audit event written by this same request: a second
        # read must count the first read's event.
        again = request(client, h, window="7d").json()
        first = next(c for c in body["categories"] if c["key"] == "operations_read")
        second = next(c for c in again["categories"] if c["key"] == "operations_read")
        assert second["success"] >= first["success"] + 1
    finally:
        grant(admin, uid, False)


def test_audit_failure_withholds_the_summary(scenario, runtime_engine):
    client, h, _, admin, uid = scenario
    grant(admin, uid)

    def count():
        with admin() as db:
            return db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "operations.audit_summary",
                    AuditEvent.initiator_id == str(uid),
                )
            )

    before = count()

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("synthetic-private-error")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        response = request(client, h)
        assert response.status_code == 503
        assert "categories" not in response.text and "synthetic-private" not in response.text
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
        grant(admin, uid, False)
    assert count() == before


def test_revoked_grant_and_migration_round_trip(scenario, postgres_engine):
    client, h, _, admin, uid = scenario
    grant(admin, uid)
    assert request(client, h).status_code == 200
    grant(admin, uid, False)
    assert request(client, h).status_code == 403
    previous = "0036_notification_recheck"

    def migrate(*args):
        result = subprocess.run(
            ["alembic", *args], cwd=BACKEND, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def exists():
        with postgres_engine.connect() as db:
            return db.scalar(
                text("SELECT count(*) FROM pg_proc WHERE proname='butler_audit_summary'")
            )

    assert exists() == 1
    try:
        migrate("downgrade", previous)
        assert exists() == 0
    finally:
        migrate("upgrade", "head")
        # A recreated function has no runtime grant until role configuration runs, as in deploy.
        with postgres_engine.begin() as db:
            db.execute(
                text(
                    "GRANT EXECUTE ON FUNCTION public.butler_audit_summary(uuid,timestamptz,integer)"
                    " TO butler_runtime"
                )
            )
    assert exists() == 1
