"""Real catalog, TCP credential refusal, reviewed batches and transactional role DDL."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from work_credential_helpers import FIRST
from work_credential_helpers import apply as bootstrap
from work_storage_helpers import connect

from app import restore_credentials as recovery
from app.config import settings
from app.manage import set_scope
from app.models import User
from app.work_authority import REGISTRY_KEY
from app.work_credentials import login_name
from app.work_storage import role_name

pytestmark = pytest.mark.integration


@pytest.fixture
def case(credential_case, scenario):
    case = dict(credential_case)
    _, _, _, maker, operator = scenario
    with maker.begin() as db:
        set_scope(db, db.get(User, operator), "technical_admin", True)
    case["operator"] = operator
    bootstrap(case)
    orphan = 4000000001
    with connect() as db:
        assert not db.execute("SELECT 1 FROM pg_database WHERE oid=%s", (orphan,)).fetchone()
        db.execute(
            sql.SQL("REVOKE {} FROM {}").format(
                sql.Identifier(case["role"]), sql.Identifier(case["login"])
            )
        )
        role, login = role_name(orphan, case["workspace"]), login_name(orphan, case["workspace"])
        for name in (role, login):
            db.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(name)))
        db.execute(
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(login), sql.Literal(FIRST)
            )
        )
        db.execute(
            sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                sql.Identifier(role), sql.Identifier(login)
            )
        )
    case.update(orphan=orphan, orphan_role=role, orphan_login=login)
    try:
        yield case
    finally:
        with connect() as db:
            for name in (login, role):
                db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(name)))
                db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))


def request(case, **changes):
    return recovery.Request(
        **(
            {
                "restored_database": settings.postgres_db,
                "operator_id": case["operator"],
                "workspace_id": case["workspace"],
                "namespace_oids": sorted([case["oid"], case["orphan"]]),
            }
            | changes
        )
    )


def run(case, **changes):
    with connect() as db, db.transaction():
        return recovery.reconcile(db, request(case, **changes))


def apply(case, plan, **changes):
    return run(
        case,
        **(
            {
                "issued_at": datetime.fromisoformat(plan["issued_at"]),
                "reviewed_hash": plan["reviewed_hash"],
                "decision": "revoke_restored_credentials",
            }
            | changes
        ),
    )


def test_inventory_and_atomic_revoke_preserve_unselected_identity(case):
    with connect(case["managed"], FIRST):
        pass
    with connect(case["orphan_login"], FIRST):
        pass
    plan = run(case)
    assert len(plan["inventory"]) == 2 and plan["selected_profiles_verified"]
    assert FIRST not in str(plan) and "SCRAM" not in str(plan)
    assert not plan["recovery_complete"] and not plan["activation_authorized"]
    result = apply(case, plan)
    assert result["post_commit_inspection_required"] and not result["recovery_complete"]
    for name in (case["managed"], case["orphan_login"]):
        with pytest.raises(psycopg.OperationalError):
            connect(name, FIRST)
        with connect() as db:
            assert db.execute(
                "SELECT rolcanlogin,rolpassword FROM pg_authid WHERE rolname=%s", (name,)
            ).fetchone() == (False, None)
            assert not db.execute(
                "SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)",
                (name,),
            ).fetchone()
    with connect() as db:
        assert db.execute(
            "SELECT rolcanlogin FROM pg_roles WHERE rolname=%s", (case["login"],)
        ).fetchone() == (True,)
        assert (
            db.execute(
                "SELECT metadata_json FROM audit_events WHERE id=%s", (result["receipt_id"],)
            ).fetchone()[0]
            == result
        )
        assert db.execute(
            "SELECT is_active FROM work_workspaces WHERE id=%s", (case["workspace"],)
        ).fetchone() == (False,)
    with pytest.raises(ValueError, match="changed"):
        apply(case, plan)
    after = run(case)
    assert all(not item["login"]["can_login"] for item in after["inventory"])
    with pytest.raises(ValueError, match="No live"):
        apply(case, after)


def test_selected_namespace_only_and_catalog_drift(case):
    plan = run(case, namespace_oids=[case["oid"]])
    with pytest.raises(ValueError, match="changed"):
        apply(case, plan, namespace_oids=[case["orphan"]])
    apply(case, plan, namespace_oids=[case["oid"]])
    with connect(case["orphan_login"], FIRST):
        pass


def test_live_source_namespace_refused(case):
    # The current database is allowed; another existing OID is never treated as orphan.
    with connect() as db:
        source = db.execute("SELECT oid FROM pg_database WHERE datname='postgres'").fetchone()[0]
        role, login = role_name(source, case["workspace"]), login_name(source, case["workspace"])
        db.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(role)))
        db.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(login)))
    try:
        with pytest.raises(ValueError, match="source database still exists"):
            run(case, namespace_oids=[source])
    finally:
        with connect() as db:
            db.execute(
                sql.SQL("DROP ROLE {},{}").format(sql.Identifier(login), sql.Identifier(role))
            )


def test_observed_connection_blocks_apply_and_changed_count_invalidates_plan(case):
    before = run(case)
    with connect(case["orphan_login"], FIRST):
        with pytest.raises(ValueError, match="changed"):
            apply(case, before)
        busy = run(case)
        with pytest.raises(ValueError, match="Drain"):
            apply(case, busy)
    apply(case, before)


@pytest.mark.parametrize("drift", ["inherit", "membership", "incoming", "direct", "settings"])
def test_profile_drift_refused_without_repair(case, drift):
    with connect() as db:
        login = sql.Identifier(case["managed"])
        if drift == "inherit":
            db.execute(sql.SQL("ALTER ROLE {} INHERIT").format(login))
        elif drift == "membership":
            db.execute(
                sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                    sql.Identifier(case["peer_role"]), login
                )
            )
        elif drift == "incoming":
            db.execute(
                sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                    login, sql.Identifier(case["login"])
                )
            )
        elif drift == "direct":
            db.execute(sql.SQL("GRANT SELECT ON public.users TO {}").format(login))
        else:
            db.execute(sql.SQL("ALTER ROLE {} SET statement_timeout='1s'").format(login))
    with pytest.raises(ValueError, match="Unreviewed"):
        run(case)


def test_audit_error_rolls_back_all_role_changes(case):
    from unittest.mock import patch

    plan = run(case)
    identifier = uuid4()
    with connect() as db:
        db.execute(
            "INSERT INTO audit_events(id,occurred_at,environment,initiator_type,initiator_id,scope_key,event_type,result_status) VALUES(%s,now(),'test','system','synthetic','technical_admin','synthetic.receipt.collision','success')",
            (identifier,),
        )
    with (
        patch.object(recovery, "uuid4", return_value=identifier),
        pytest.raises(psycopg.errors.UniqueViolation),
    ):
        apply(case, plan)
    for name in (case["managed"], case["orphan_login"]):
        with connect(name, FIRST):
            pass


@pytest.mark.parametrize(
    "fault",
    ["target", "operator", "workspace", "active", "expired", "hash", "isolation", "missing"],
)
def test_invalid_context_does_not_revoke(case, fault):
    changes = {}
    if fault == "target":
        changes["restored_database"] = "butler_test_other"
    if fault == "operator":
        changes["operator_id"] = uuid4()
    if fault == "workspace":
        changes["workspace_id"] = uuid4()
    if fault == "missing":
        changes["namespace_oids"] = [3999999999]
    if fault == "expired":
        changes["issued_at"] = datetime.now(UTC) - timedelta(minutes=6)
    if fault == "hash":
        changes.update(
            decision="revoke_restored_credentials",
            issued_at=datetime.now(UTC),
            reviewed_hash="a" * 64,
        )
    with connect() as db:
        if fault == "active":
            db.execute(
                "UPDATE work_workspaces SET is_active=true WHERE id=%s", (case["workspace"],)
            )
    with pytest.raises(ValueError), connect() as db, db.transaction():
        if fault == "isolation":
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        recovery.reconcile(db, request(case, **changes))
    with connect(case["managed"], FIRST):
        pass


def test_registry_busy_fails_before_writes(case):
    with connect() as blocker:
        blocker.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
        with pytest.raises(ValueError, match="busy"):
            run(case)


def test_inventory_without_selection_and_malformed_reserved_name(case):
    report = run(case, namespace_oids=[])
    assert len(report["inventory"]) == 2
    assert not report["selected_profiles_verified"]
    malformed = "butler_wlogin_01_" + case["workspace"].hex
    with connect() as db:
        db.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(malformed)))
    try:
        with pytest.raises(ValueError, match="Malformed"):
            run(case, namespace_oids=[])
    finally:
        with connect() as db:
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(malformed)))


def test_no_partial_namespace_inventory(case):
    names = [role_name(3900000000 + n, case["workspace"]) for n in range(24)]
    with connect() as db:
        for name in names:
            db.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(name)))
    try:
        with pytest.raises(ValueError, match="cap"):
            run(case, namespace_oids=[])
    finally:
        with connect() as db:
            for name in names:
                db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))


def test_grants_and_restricted_owner_fail_closed(case):
    with connect() as db:
        db.execute(
            "INSERT INTO public.work_access_grants(user_id,workspace_id,capability,created_at) VALUES(%s,%s,'work_private',now())",
            (case["operator"], case["workspace"]),
        )
    with pytest.raises(ValueError, match="Remove all"):
        run(case)
    with connect() as db:
        db.execute(
            "DELETE FROM public.work_access_grants WHERE workspace_id=%s", (case["workspace"],)
        )
    with pytest.raises(ValueError, match="Clean superuser"), connect() as db, db.transaction():
        db.execute("SET LOCAL ROLE butler_runtime")
        recovery.reconcile(db, request(case))


def test_business_writer_busy_fails_without_catalog_change(case):
    with connect() as blocker:
        blocker.execute(
            "UPDATE public.work_workspaces SET is_active=is_active WHERE id=%s",
            (case["workspace"],),
        )
        with pytest.raises((ValueError, psycopg.errors.LockNotAvailable)):
            run(case)
    with connect(case["managed"], FIRST):
        pass
