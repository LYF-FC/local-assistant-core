from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg.pq import TransactionStatus
from pydantic import ValidationError

from app import work_parties
from app.config import settings


def values(**changes):
    now = datetime.now(UTC)
    data = {
        "workspace_id": uuid4(),
        "id": uuid4(),
        "policy_id": uuid4(),
        "revision": 1,
        "state": "active",
        "marker": "synthetic:explicit-party",
        "retain_until": now + timedelta(hours=1),
        "created_at": now,
        "updated_at": now,
    }
    data.update(changes)
    return data


@pytest.mark.parametrize(
    "changes",
    [
        {"marker": "real colleague"},
        {"marker": "synthetic:"},
        {"marker": "synthetic:" + "a" * 247},
        {"marker": None},
        {"state": "forgotten"},
        {"revision": True},
        {"revision": 4},
        {"state": "unknown"},
        {"email": "synthetic@example.invalid"},
        {"retain_until": datetime.now()},
        {"created_at": datetime.now(UTC) + timedelta(days=1)},
    ],
)
def test_strict_synthetic_party_contract(changes):
    with pytest.raises((ValidationError, ValueError)):
        work_parties.Party(**values(**changes))


def test_party_label_hidden_and_forgotten_contract():
    item = work_parties.Party(**values())
    assert "synthetic:explicit-party" not in repr(item)
    forgotten = work_parties.Party(**values(state="forgotten", marker=None, revision=2))
    assert forgotten.marker is None


@pytest.mark.parametrize("fault", ["production", "staging", "database", "workspace", "transaction"])
def test_local_target_and_transaction_guards(monkeypatch, fault):
    monkeypatch.setattr(settings, "env", "test")
    monkeypatch.setattr(settings, "postgres_db", "butler_test_unit")
    if fault in {"production", "staging"}:
        monkeypatch.setattr(settings, "env", fault)
    elif fault == "database":
        monkeypatch.setattr(settings, "postgres_db", "butler_live")
    db = SimpleNamespace(info=SimpleNamespace(transaction_status=TransactionStatus.IDLE))
    with pytest.raises(ValueError):
        work_parties._begin(db, "invalid" if fault == "workspace" else uuid4())


@pytest.mark.parametrize(
    "revision,action",
    [(True, "retire"), (0, "retire"), (3, "forget"), (1, "activate"), ("1", "retire")],
)
def test_explicit_revision_and_terminal_action_required(revision, action):
    with pytest.raises(ValueError):
        work_parties.transition(None, uuid4(), uuid4(), revision, action)


@pytest.mark.parametrize(
    "profile",
    [
        (False, "read committed", True),
        (True, "repeatable read", True),
        (True, "read committed", False),
    ],
)
def test_clean_actual_owner_required_before_workspace_access(monkeypatch, profile):
    monkeypatch.setattr(settings, "env", "test")
    monkeypatch.setattr(settings, "postgres_db", "butler_test_unit")
    calls = []

    def execute(query):
        calls.append(query)
        return SimpleNamespace(fetchone=lambda: profile)

    db = SimpleNamespace(
        info=SimpleNamespace(transaction_status=TransactionStatus.INTRANS), execute=execute
    )
    with pytest.raises(ValueError, match="Clean local party storage owner"):
        work_parties._begin(db, uuid4())
    assert len(calls) == 1
