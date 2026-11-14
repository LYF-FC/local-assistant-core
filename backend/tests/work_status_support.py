"""Spec 073 PostgreSQL support: isolated databases, a technical-admin scenario and real-path rows.

The work-status view reports household-wide queue states, so its assertions need a database that
holds only the rows a test created. Each test gets a fresh copy of one migrated template database
(names start with ``butler_test``, dropped afterwards), with the restricted runtime role configured.
Rows are created through the real application write paths with a controlled application clock;
where a timestamp cannot be reached that way, a fixture arrangement on the owner connection
briefly disables the table's guard trigger, exactly as the existing worker tests do.
"""

import os
import subprocess
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from conftest import RUNTIME_PASSWORD, SYNTHETIC_PASSWORD, client_for, require_disposable_postgres
from psycopg import sql
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app import identity, operations
from app.config import settings
from app.manage import provision
from app.models import JobOutbox, NotificationDelivery, TaskReminder
from app.runtime_role import ROLE, configure

BACKEND = Path(__file__).resolve().parents[1]
G = operations.WORK_GRACE


def _base_url():
    return make_url(settings.database_url)


def _admin(command, name, template=None):
    engine = create_engine(_base_url().set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            raw = connection.connection.driver_connection
            statement = sql.SQL(command + " {}").format(sql.Identifier(name))
            if template:
                statement = sql.SQL("{} TEMPLATE {}").format(statement, sql.Identifier(template))
            connection.exec_driver_sql(statement.as_string(raw))
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def work_template():
    require_disposable_postgres()
    name = "butler_test_ws_tpl_" + uuid4().hex[:8]
    _admin("CREATE DATABASE", name)
    try:
        migrated = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=BACKEND,
            env={**os.environ, "BUTLER_POSTGRES_DB": name},
            capture_output=True,
            text=True,
            check=False,
        )
        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        owner = create_engine(_base_url().set(database=name))
        with owner.begin() as connection:
            configure(connection.connection.driver_connection, RUNTIME_PASSWORD)
        owner.dispose()
        yield name
    finally:
        _drop(name)


def _drop(name):
    engine = create_engine(_base_url().set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            raw = connection.connection.driver_connection
            connection.exec_driver_sql(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)")
                .format(sql.Identifier(name))
                .as_string(raw)
            )
    finally:
        engine.dispose()


@pytest.fixture
def fresh_database(work_template):
    """Factory: each call returns a new isolated copy of the migrated template."""
    created = []

    def make():
        name = "butler_test_ws_" + uuid4().hex[:10]
        _admin("CREATE DATABASE", name, template=work_template)
        url = _base_url().set(database=name)
        owner_engine = create_engine(url, pool_size=4, max_overflow=0)
        runtime_engine = create_engine(
            url.set(username=ROLE, password=RUNTIME_PASSWORD), pool_size=8, max_overflow=0
        )
        created.append((name, owner_engine, runtime_engine))
        return SimpleNamespace(
            name=name,
            owner_engine=owner_engine,
            runtime_engine=runtime_engine,
            owner=sessionmaker(bind=owner_engine, expire_on_commit=False),
            runtime=sessionmaker(bind=runtime_engine, expire_on_commit=False),
        )

    yield make
    for name, owner_engine, runtime_engine in created:
        owner_engine.dispose()
        runtime_engine.dispose()
        _drop(name)


@contextmanager
def signed_in(db_ns, scopes=("household_shared", "technical_admin")):
    """A provisioned synthetic user signed in through the real login path on the runtime role."""
    slug = "synthetic-ws-" + uuid4().hex
    with db_ns.owner.begin() as db:
        user = provision(db, slug, "Synthetic work status", SYNTHETIC_PASSWORD, set(scopes))
        uid = user.id
    with client_for(db_ns.runtime) as client:
        response = client.post(
            "/api/v1/auth/login", json={"slug": slug, "password": SYNTHETIC_PASSWORD}
        )
        assert response.status_code == 200, response.text
        headers = {"X-CSRF-Token": response.json()["csrf_token"]}
        yield SimpleNamespace(client=client, headers=headers, uid=uid, slug=slug, db=db_ns)


@pytest.fixture
def ws(fresh_database):
    db_ns = fresh_database()
    with signed_in(db_ns) as scenario:
        yield scenario


class Clock:
    """Controls ``identity.now_utc`` for application write paths, workers and the observer.

    ``real()`` hands control back to the real clock (for steps run by a separate process).
    """

    def __init__(self, monkeypatch, start):
        self.now = start
        self._real = identity.now_utc
        monkeypatch.setattr(
            identity, "now_utc", lambda: self._real() if self.now is None else self.now
        )

    def set(self, moment):
        self.now = moment
        return moment

    def real(self):
        self.now = None


def status(scenario, **body):
    return scenario.client.post(
        "/api/v1/operations/work-status",
        headers=scenario.headers,
        json={"scope": "technical_admin", **body},
    )


def states(scenario):
    response = status(scenario)
    assert response.status_code == 200, response.text
    return {row["key"]: row["state"] for row in response.json()["queues"]}


def observe(db_ns, now):
    """The observer exactly as the route runs it, on the restricted runtime role."""
    with db_ns.runtime() as db:
        return {row["key"]: row["state"] for row in operations.observe_work(db, now - G)}


# --- real-path builders -------------------------------------------------------------------------


def post(scenario, path, body):
    return scenario.client.post(path, headers=scenario.headers, json=body)


def save_policy(scenario, expected_revision, **changes):
    body = {
        "scope": "household_shared",
        "expected_revision": expected_revision,
        "enabled": True,
        "timezone": "UTC",
        "quiet_start": 0,
        "quiet_end": 0,
        "daily_limit": 20,
        **changes,
    }
    response = post(scenario, "/api/v1/reminders/preferences/save", body)
    assert response.status_code == 200, response.text
    return response.json()


def create_task(scenario):
    response = post(
        scenario,
        "/api/v1/tasks",
        {
            "scope": "household_shared",
            "title": "Synthetic work-status task " + uuid4().hex[:8],
            "details": "Synthetic only",
            "source_reference": "Synthetic source",
            "due_at": None,
            "assignment": "unknown",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def schedule(scenario, task, when):
    response = post(
        scenario,
        "/api/v1/reminders/schedule",
        {
            "scope": task["scope"],
            "task_id": task["id"],
            "expected_task_revision": task["revision"],
            "expected_revision": None,
            "scheduled_at": when.isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def reminder_candidate(db_ns, reminder_id):
    with db_ns.runtime() as db:
        return db.execute(
            select(
                TaskReminder.id, TaskReminder.owner_id, TaskReminder.task_id, TaskReminder.scope_key
            ).where(TaskReminder.id == UUID(reminder_id))
        ).one()


def deliver_reminder(db_ns, reminder_id):
    from app import reminder_worker

    candidate = reminder_candidate(db_ns, reminder_id)
    with db_ns.runtime.begin() as db:
        return reminder_worker.process(db, candidate)


def delivery_for(db_ns, reminder_id):
    with db_ns.runtime() as db:
        return db.execute(
            select(
                NotificationDelivery.id,
                NotificationDelivery.owner_id,
                NotificationDelivery.scope_key,
            ).where(NotificationDelivery.reminder_id == UUID(reminder_id))
        ).one()


@contextmanager
def unguarded(db_ns, table, trigger):
    """Fixture arrangement on the owner connection with one table guard briefly disabled."""
    with db_ns.owner.begin() as db:
        db.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
        yield db
        db.flush()
        db.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))


def approved_job(scenario):
    """An approval decided by the same synthetic user, then enqueued through the jobs route."""
    record = post(
        scenario,
        "/api/v1/approvals",
        {"scope": "household_shared", "payload": {"note": "synthetic-work-status"}},
    ).json()
    binding = {"payload_hash": record["payload_hash"], "policy_version": record["policy_version"]}
    decided = post(
        scenario, f"/api/v1/approvals/{record['id']}/decide", dict(binding, decision="approve")
    )
    assert decided.status_code == 200, decided.text
    queued = post(
        scenario,
        "/api/v1/jobs",
        dict(binding, approval_id=record["id"], idempotency_key="synthetic-" + uuid4().hex),
    )
    assert queued.status_code == 201, queued.text
    with scenario.db.owner() as db:
        return db.scalar(select(JobOutbox.id).where(JobOutbox.job_id == UUID(queued.json()["id"])))


def set_outbox(db_ns, outbox_id, **values):
    """job_outbox has no guard trigger; timestamps are arranged directly on the owner."""
    with db_ns.owner.begin() as db:
        row = db.get(JobOutbox, outbox_id)
        for key, value in values.items():
            setattr(row, key, value)


def ago(moment, seconds):
    return moment - timedelta(seconds=seconds)


def filing_request(scenario):
    """An approved invoice plan and its filing request through the real document routes."""
    from test_filing import body
    from test_invoice_filing import approved
    from test_invoice_review import TEXT, confirm, source

    from app.models import FilingExecution

    client, h = scenario.client, scenario.headers
    doc = source(client, h, TEXT + "\nSynthetic work-status filing " + uuid4().hex)
    receipt = approved(client, h, doc, confirm(client, h, doc))
    response = client.post("/api/v1/filing/request", headers=h, json=body(doc, receipt))
    assert response.status_code == 201, response.text
    with scenario.db.runtime() as db:
        return db.execute(
            select(
                FilingExecution.id,
                FilingExecution.owner_id,
                FilingExecution.scope_key,
                FilingExecution.document_id,
            ).where(FilingExecution.id == UUID(response.json()["filing"]["id"]))
        ).one()
