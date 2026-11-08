"""Shared disposable managed-credential fixture; never used by runtime code."""

import pytest
from psycopg import sql
from work_storage_helpers import connect

from app import work_credentials as credentials

FIRST = "synthetic-first-work-secret-0123456789012345"
SECOND = "synthetic-second-work-secret-0123456789012345"


@pytest.fixture
def credential_case(storage_case):
    case = dict(storage_case["a"])
    case["peer_role"] = storage_case["b"]["role"]
    with connect() as db:
        oid = db.execute("SELECT oid FROM pg_database WHERE datname=current_database()").fetchone()[
            0
        ]
        db.execute("UPDATE work_workspaces SET is_active=false WHERE id=%s", (case["workspace"],))
    case["oid"] = oid
    case["managed"] = credentials.login_name(oid, case["workspace"])
    try:
        yield case
    finally:
        with connect() as db:
            if db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (case["managed"],)).fetchone():
                db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(case["managed"])))
                db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(case["managed"])))


def apply(case, action="bootstrap", password=FIRST):
    with connect() as db:
        return credentials.administer(
            db, action, case["slug"], None if action == "revoke" else password
        )


def audits(case):
    with connect() as db:
        return db.execute(
            "SELECT event_type,source_context,metadata_json FROM audit_events WHERE entity_id=%s AND event_type LIKE 'admin.work_credential_%%' ORDER BY occurred_at",
            (str(case["workspace"]),),
        ).fetchall()
