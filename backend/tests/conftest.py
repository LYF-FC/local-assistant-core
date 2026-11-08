import os
from contextlib import contextmanager
from uuid import uuid4

os.environ.setdefault("BUTLER_ENV", "test")
os.environ.setdefault("BUTLER_POSTGRES_PASSWORD", "synthetic-test-only-password-0123456789")
os.environ.setdefault("BUTLER_SPEECH_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth_routes import get_db
from app.config import settings
from app.db import Base
from app.identity import SCOPES
from app.main import app
from app.manage import provision
from app.models import Scope
from app.runtime_role import ROLE, configure

SYNTHETIC_PASSWORD = "synthetic-password-only-0123456789"


@pytest.fixture
def auth_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def auth_store(auth_engine):
    connection = auth_engine.connect()
    transaction = connection.begin()
    if auth_engine.dialect.name == "sqlite":
        connection.exec_driver_sql("BEGIN")
    maker = sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        with maker.begin() as db:
            for key in SCOPES:
                if db.query(Scope).filter_by(key=key).first() is None:
                    db.add(Scope(key=key, description="Synthetic scope"))
            db.flush()
            provision(db, "alice", "Synthetic Alice", SYNTHETIC_PASSWORD, {"household_shared"})
            provision(
                db,
                "bob",
                "Synthetic Bob",
                SYNTHETIC_PASSWORD,
                {"finance_private", "member_b_private"},
            )
        yield maker
    finally:
        transaction.rollback()
        connection.close()


@pytest.fixture
def auth_client(auth_store):
    def dependency():
        with auth_store() as db:
            yield db

    app.dependency_overrides[get_db] = dependency
    with TestClient(
        app, base_url="https://localhost:8443", headers={"Origin": "https://localhost:8443"}
    ) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


def require_disposable_postgres():
    if os.environ.get("BUTLER_RUN_DB_TESTS") != "1":
        pytest.skip("disposable database opt-in required")
    assert settings.env == "test" and settings.postgres_db.startswith("butler_test")


@pytest.fixture(scope="module")
def postgres_schema():
    """Bootstrap once per module; explicit migration/round-trip tests remain separate."""
    import subprocess
    from pathlib import Path

    require_disposable_postgres()
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def postgres_engine(postgres_schema):
    # Keep fresh pools and the disposable-target guard for every test. Existing tests
    # retain committed synthetic data; upgrade-to-head was never a data reset.
    require_disposable_postgres()
    engine = create_engine(settings.database_url, pool_size=8, max_overflow=0)
    yield engine
    engine.dispose()


RUNTIME_PASSWORD = "synthetic-runtime-password-only-0123456789"


@pytest.fixture
def runtime_engine(postgres_engine):
    # Privileged connection is limited to the disposable CI database.
    with postgres_engine.begin() as connection:
        configure(connection.connection.driver_connection, RUNTIME_PASSWORD)
        configure(connection.connection.driver_connection, RUNTIME_PASSWORD)  # idempotence
    url = make_url(settings.database_url).set(username=ROLE, password=RUNTIME_PASSWORD)
    engine = create_engine(url, pool_size=8, max_overflow=0)
    yield engine
    engine.dispose()


@contextmanager
def client_for(maker):
    def dependency():
        with maker() as db:
            yield db

    app.dependency_overrides[get_db] = dependency
    try:
        with TestClient(
            app,
            base_url="https://localhost:8443",
            headers={"Origin": "https://localhost:8443"},
            # Each independent scenario has its own synthetic login source. Keep the
            # real database rate limiter active without sharing its 30-login budget
            # across otherwise unrelated tests in the disposable PostgreSQL database.
            client=("synthetic-" + uuid4().hex, 50000),
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def scenario(postgres_engine, runtime_engine):
    admin = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    slug = "synthetic-" + uuid4().hex
    # Committed synthetic data is retained until the disposable migration round-trip;
    # do not bypass append-only guards just to clean a test fixture.
    with admin.begin() as db:
        user = provision(db, slug, "Synthetic PostgreSQL", SYNTHETIC_PASSWORD, {"household_shared"})
        user_id = user.id
    runtime = sessionmaker(bind=runtime_engine, expire_on_commit=False)
    with client_for(runtime) as client:
        response = client.post(
            "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
        )
        assert response.status_code == 200
        headers = {"X-CSRF-Token": response.json()["csrf_token"]}
        record_response = client.post(
            "/api/v1/approvals",
            headers=headers,
            json={
                "scope": "household_shared",
                "payload": {"negative_zero": -0.0, "note": "synthetic-only"},
            },
        )
        assert record_response.status_code == 201
        record = record_response.json()
        yield client, headers, record, admin, user_id


# Explicit root registration shares the restricted login fixture across PG modules.
pytest_plugins = ["work_storage_helpers", "work_credential_helpers", "work_review_helpers"]
