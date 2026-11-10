from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_finance import call, create, values

from app.manage import set_scope
from app.models import FinancialRecord, FinancialRevision, User

pytestmark = pytest.mark.integration


def ready(scenario):
    client, h, _, admin, uid = scenario
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "finance_private", True)
    return client, h, admin, uid


def test_financial_runtime_lifecycle_and_acceptance(scenario):
    client, h, admin, uid = ready(scenario)
    r = create(client, h, "plan")
    assert r.status_code == 201, r.json()
    row = r.json()
    accepted = call(client, h, row, "accept", acknowledge_record_only=True).json()
    assert accepted["accepted_by"] == str(uid)
    corrected = call(
        client, h, accepted, "correct", values=values(basis="forecast", amount="0", currency="EUR")
    ).json()
    assert corrected["plan_status"] == "proposed" and corrected["values"]["amount"] == "0.00"
    forgotten = call(client, h, corrected, "forget").json()
    assert forgotten["state"] == "forgotten"
    from uuid import UUID

    with admin() as db:
        snapshots = list(
            db.scalars(
                select(FinancialRevision.snapshot).where(
                    FinancialRevision.record_id == UUID(row["id"])
                )
            )
        )
        assert len(snapshots) == 4 and all(value is None for value in snapshots)
    assert all(r["snapshot"] is None for r in call(client, h, forgotten, "history").json()["items"])


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM financial_records",
        "TRUNCATE financial_records CASCADE",
        "UPDATE financial_records SET owner_id=gen_random_uuid(),revision=revision+1",
        "UPDATE financial_records SET revision=revision",
        'UPDATE financial_records SET payload=payload || \'{"secret":"synthetic"}\'::jsonb,revision=revision+1',
        "DELETE FROM financial_revisions",
        "UPDATE financial_revisions SET snapshot='{}'::jsonb",
    ],
)
def test_financial_sql_guards(scenario, runtime_engine, statement):
    client, h, _, _ = ready(scenario)
    assert create(client, h).status_code == 201
    with pytest.raises(DBAPIError), runtime_engine.begin() as db:
        db.execute(text(statement))


def test_financial_concurrent_revision_and_audit_rollback(scenario, runtime_engine):
    client, h, _admin, _ = ready(scenario)
    row = create(client, h).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                call, client, h, row, "correct", values=values(title="Synthetic correction")
            )
            for _ in range(2)
        ]
        assert sorted(f.result(timeout=5).status_code for f in futures) == [200, 409]
    latest = call(client, h, row, "read").json()

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise SQLAlchemyError("Synthetic finance audit failure")

    event.listen(runtime_engine, "before_cursor_execute", fail)
    try:
        assert call(client, h, latest, "forget").status_code == 503
    finally:
        event.remove(runtime_engine, "before_cursor_execute", fail)
    assert call(client, h, latest, "read").json() == latest


def test_financial_quota_serializes_two_creates(scenario):
    client, h, _, _ = ready(scenario)
    for _ in range(99):
        assert create(client, h).status_code == 201
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create, client, h) for _ in range(2)]
        assert sorted(f.result(timeout=5).status_code for f in futures) == [201, 429]


@pytest.mark.parametrize("operation", ["read", "history", "correct", "accept", "forget", "export"])
def test_financial_expiry_after_record_wait(scenario, monkeypatch, operation):
    import time
    from datetime import timedelta

    from app import identity
    from app.models import AuthSession

    client, h, admin, uid = ready(scenario)
    row = create(client, h, "plan").json()
    with admin() as db:
        expiry = db.scalar(select(AuthSession.expires_at).where(AuthSession.user_id == uid))
    extra = (
        {"values": values(title="Synthetic late correction")}
        if operation == "correct"
        else {"acknowledge_record_only": True}
        if operation == "accept"
        else {"expected_revision": row["revision"], "acknowledge_copy_limits": True}
        if operation == "export"
        else {}
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        with admin.begin() as db:
            db.scalar(
                select(FinancialRecord).where(FinancialRecord.id == row["id"]).with_for_update()
            )
            pending = pool.submit(call, client, h, row, operation, **extra)
            end = time.monotonic() + 5
            while time.monotonic() < end:
                with admin() as check:
                    if check.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%financial_records%FOR %'"
                        )
                    ):
                        break
                time.sleep(0.02)
            else:
                raise AssertionError("No financial record wait observed")
            monkeypatch.setattr(
                identity, "now_utc", lambda: identity.aware(expiry) + timedelta(seconds=1)
            )
        assert pending.result(timeout=5).status_code == 401


def test_financial_other_owner_and_revoked_grant(scenario, runtime_engine):
    from uuid import uuid4

    from conftest import SYNTHETIC_PASSWORD, client_for
    from sqlalchemy.orm import sessionmaker

    from app.auth_routes import get_db
    from app.main import app
    from app.manage import provision

    client, h, admin, uid = ready(scenario)
    row = create(client, h).json()
    slug = "synthetic-finance-" + uuid4().hex
    with admin.begin() as db:
        provision(
            db,
            slug,
            "Synthetic second finance owner",
            SYNTHETIC_PASSWORD,
            {"finance_private", "technical_admin"},
        )
    override = app.dependency_overrides.get(get_db)
    try:
        with client_for(sessionmaker(bind=runtime_engine, expire_on_commit=False)) as other:
            login = other.post(
                "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
            )
            assert login.status_code == 200
            oh = {"X-CSRF-Token": login.json()["csrf_token"]}
            for op in ["read", "history", "forget"]:
                assert call(other, oh, row, op).status_code == 404
            assert (
                other.post(
                    "/api/v1/finance/export",
                    headers=oh,
                    json={"scope": "finance_private", "acknowledge_copy_limits": True},
                ).json()["items"]
                == []
            )
    finally:
        if override is not None:
            app.dependency_overrides[get_db] = override
    with admin.begin() as db:
        set_scope(db, db.get(User, uid), "technical_admin", True)
        set_scope(db, db.get(User, uid), "finance_private", False)
    assert call(client, h, row, "read").status_code == 403
