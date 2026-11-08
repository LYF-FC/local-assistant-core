"""Transaction-local work identity authority; never a transferable storage permission."""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, SessionTransaction

from app import identity
from app.models import AuthSession, User

# Reserved two-int transaction advisory key; duplicated in migration 0008 by contract.
REGISTRY_KEY = (1508310, 1)


def registry_barrier(db: Session, *, exclusive: bool = False) -> None:
    if db.get_bind().dialect.name == "postgresql":
        if db.scalar(text("SELECT current_setting('transaction_isolation')")) != "read committed":
            raise SQLAlchemyError("Work authority requires READ COMMITTED isolation")
        db.execute(text("SET LOCAL lock_timeout = '2s'"))
        db.execute(text("SET LOCAL statement_timeout = '5s'"))
        function = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
        db.execute(
            text(f"SELECT {function}(:namespace,:key)"),
            {"namespace": REGISTRY_KEY[0], "key": REGISTRY_KEY[1]},
        )


@dataclass(frozen=True, repr=False)
class WorkAuthority:
    user: User = field(repr=False)
    session: AuthSession = field(repr=False)
    _db: Session = field(repr=False)
    _transaction: SessionTransaction = field(repr=False)

    def checked_now(self) -> datetime | None:
        if (
            self._db.get_transaction() is not self._transaction
            or not self._transaction.is_active
            or not self._db.is_active
        ):
            raise RuntimeError("Work authority belongs only to its originating transaction")
        now = identity.now_utc()
        if (
            not self.user.is_active
            or self.session.user_id != self.user.id
            or self.session.revoked_at is not None
            or identity.aware(self.session.expires_at) <= now
            or identity.aware(self.session.last_seen_at) <= now - identity.IDLE_LIFETIME
        ):
            return None
        return now


def resolve(db: Session, token: str | None) -> WorkAuthority | identity.Result:
    if not token or not 40 <= len(token) <= 128:
        return identity.denied(db, 401, "work.access_session_denied")
    # Fetch only a scalar: do not cache a pre-wait ORM session snapshot.
    user_id = db.scalar(
        select(AuthSession.user_id).where(AuthSession.token_hash == identity.digest(token))
    )
    if user_id is None:
        return identity.denied(db, 401, "work.access_session_denied")
    registry_barrier(db)
    # User first, then session, matching trusted identity administration ordering.
    user = db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    current = (
        identity.resolve(db, token, refresh_session=True)
        if user is not None and user.is_active
        else None
    )
    if current is None or current[0].id != user_id:
        return identity.denied(db, 401, "work.access_session_denied")
    transaction = db.get_transaction()
    if transaction is None:
        raise RuntimeError("Work access requires an active transaction")
    return WorkAuthority(user, current[1], db, transaction)
