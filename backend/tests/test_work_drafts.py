from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg.pq import TransactionStatus

from app import work_drafts as store
from app.config import settings


@pytest.mark.parametrize(
    "fault", ["production", "staging", "test_database", "workspace", "actor", "transaction"]
)
def test_storage_entry_refuses_invalid_target_metadata_and_implicit_transaction(monkeypatch, fault):
    monkeypatch.setattr(settings, "env", "test")
    monkeypatch.setattr(settings, "postgres_db", "butler_test_unit")
    workspace, actor = uuid4(), uuid4()
    db = SimpleNamespace(info=SimpleNamespace(transaction_status=TransactionStatus.IDLE))
    if fault in {"production", "staging"}:
        monkeypatch.setattr(settings, "env", fault)
    elif fault == "test_database":
        monkeypatch.setattr(settings, "postgres_db", "butler")
    elif fault == "workspace":
        workspace = str(workspace)
    elif fault == "actor":
        actor = str(actor)
    with pytest.raises(store.StoreError, match="Explicit local synthetic"):
        store.read(db, workspace, actor, uuid4())


@pytest.mark.parametrize(
    "profile",
    [
        (False, "read committed", True),
        (True, "repeatable read", True),
        (True, "read committed", False),
    ],
)
def test_owner_residue_and_isolation_refusal_precedes_any_workspace_access(monkeypatch, profile):
    monkeypatch.setattr(settings, "postgres_db", "butler_test_unit")
    calls = []

    def execute(query):
        calls.append(query)
        return SimpleNamespace(fetchone=lambda: profile)

    db = SimpleNamespace(
        info=SimpleNamespace(transaction_status=TransactionStatus.INTRANS), execute=execute
    )
    with pytest.raises(store.StoreError, match="Clean local storage owner"):
        store.read(db, uuid4(), uuid4(), uuid4())
    assert len(calls) == 1
