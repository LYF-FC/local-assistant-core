from datetime import timedelta

import pytest
from sqlalchemy import select, update
from test_memory import signin
from test_work_access import URL, setup_work

from app import identity, work_authority
from app.models import AuthSession


def test_authority_handle_cannot_escape_or_cross_its_transaction(auth_client, auth_store):
    setup_work(auth_store)
    signin(auth_client)
    token = auth_client.cookies.get(identity.COOKIE)
    with auth_store.begin() as db:
        authority = work_authority.resolve(db, token)
        assert isinstance(authority, work_authority.WorkAuthority)
        assert authority.checked_now() is not None
        assert "synthetic" not in repr(authority) and token not in repr(authority)
    with pytest.raises(RuntimeError):
        authority.checked_now()
    with auth_store.begin(), pytest.raises(RuntimeError):
        authority.checked_now()


@pytest.mark.parametrize("mode", ["absolute", "idle"])
def test_expiry_between_initial_authority_and_final_sql_releases_no_metadata(
    auth_client, auth_store, monkeypatch, mode
):
    ids = setup_work(auth_store)
    signin(auth_client)
    now = identity.now_utc()
    with auth_store.begin() as db:
        session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == identity.digest(auth_client.cookies.get(identity.COOKIE))
            )
        )
        if mode == "absolute":
            session.expires_at = now + timedelta(seconds=1)
        else:
            session.last_seen_at = now - identity.IDLE_LIFETIME + timedelta(seconds=1)
    times = iter([now, now + timedelta(seconds=2)])
    monkeypatch.setattr(identity, "now_utc", lambda: next(times))
    response = auth_client.get(f"{URL}/{ids['synthetic-team-a']}/status")
    assert response.status_code == 401 and "workspace" not in response.json()


def test_current_check_is_snapshot_metadata_not_a_storage_capability(auth_client, auth_store):
    ids = setup_work(auth_store)
    signin(auth_client)
    status = auth_client.get(f"{URL}/{ids['synthetic-team-a']}/status").json()
    assert status["authority_mode"] == "transaction_snapshot"
    assert status["checked_at"] and "token" not in status
    assert status["ingestion_allowed"] is False


def test_work_authority_refreshes_a_preloaded_revoked_session(auth_client, auth_store):
    setup_work(auth_store)
    signin(auth_client)
    token = auth_client.cookies.get(identity.COOKIE)
    with auth_store.begin() as db:
        cached = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == identity.digest(token))
        )
        db.execute(
            update(AuthSession)
            .where(AuthSession.id == cached.id)
            .values(revoked_at=identity.now_utc())
            .execution_options(synchronize_session=False)
        )
        assert cached.revoked_at is None
        result = work_authority.resolve(db, token)
        assert isinstance(result, identity.Result) and result.status == 401
        assert cached.revoked_at is not None
