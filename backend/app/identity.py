"""Local identity. Call inside a transaction and commit before releasing a result."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import case, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditEvent, AuthRateWindow, AuthSession, Credential, Scope, User, UserScope

SCOPES = frozenset(
    {
        "household_shared",
        "member_a_private",
        "member_b_private",
        "parents_child",
        "member_business",
        "finance_private",
        "technical_admin",
    }
)
COOKIE = "__Host-butler_session"
SESSION_LIFETIME = timedelta(hours=8)
IDLE_LIFETIME = timedelta(minutes=30)
RATE_WINDOW = timedelta(minutes=15)
_hasher = PasswordHasher()
_dummy_hash = _hasher.hash(secrets.token_urlsafe(32))
_hash_slots = BoundedSemaphore(2)


def now_utc() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str) -> str:
    if not 14 <= len(password) or len(password.encode()) > 1024:
        raise ValueError("Password must contain at least 14 characters and at most 1024 bytes")
    with _hash_slots:
        return _hasher.hash(password)


def audit(
    db: Session,
    event: str,
    result: str,
    *,
    user: User | None = None,
    scope: str = "technical_admin",
    entity: str | None = None,
    metadata: dict | None = None,
    entity_type: str = "identity",
    approval_id=None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    # Security-event scope is metadata, not a grant of technical_admin access.
    db.add(
        AuditEvent(
            environment=settings.env,
            initiator_type="human" if user else "anonymous",
            initiator_id=str(user.id) if user else "anonymous",
            scope_key=scope,
            event_type=event,
            entity_type=entity_type,
            approval_id=approval_id,
            before_json=before,
            after_json=after,
            entity_id=entity,
            result_status=result,
            source_context={},
            metadata_json=metadata or {},
        )
    )
    db.flush()  # Any audit persistence error aborts the enclosing operation.


def attempt(db: Session, key: str, limit: int, now: datetime) -> bool:
    table = AuthRateWindow.__table__
    factory = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    stale = table.c.window_started_at <= now - RATE_WINDOW
    stmt = factory(table).values(key=digest(key), window_started_at=now, attempts=1)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.key],
        set_={
            "window_started_at": case((stale, now), else_=table.c.window_started_at),
            "attempts": case((stale, 1), else_=table.c.attempts + 1),
        },
    ).returning(table.c.attempts)
    return db.execute(stmt).scalar_one() <= limit


@dataclass
class Result:
    status: int
    payload: dict = field(repr=False)
    token: str | None = field(default=None, repr=False)
    csrf: str | None = field(default=None, repr=False)


def denied(
    db: Session,
    status: int,
    event: str,
    *,
    user: User | None = None,
    scope: str = "technical_admin",
) -> Result:
    audit(db, event, "denied", user=user, scope=scope)
    return Result(status, {"detail": "Too many attempts" if status == 429 else "Access denied"})


def login(db: Session, slug: str, password: str, source: str, old_token: str | None) -> Result:
    now = now_utc()
    if not attempt(db, "source:" + source, 30, now):
        return denied(db, 429, "auth.rate_limited")
    if not attempt(db, "account:" + slug, 5, now):
        return denied(db, 429, "auth.rate_limited")
    user = db.scalar(select(User).where(User.slug == slug).with_for_update())
    credential = db.get(Credential, user.id) if user else None
    hashed = credential.password_hash if credential else _dummy_hash
    try:
        with _hash_slots:
            valid = _hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid or user is None or not user.is_active or credential is None:
        # Never reveal whether the slug exists or is disabled.
        return denied(db, 401, "auth.login_denied")
    if _hasher.check_needs_rehash(hashed):
        credential.password_hash = password_hash(password)
        credential.changed_at = now
    if old_token and len(old_token) <= 128:
        db.execute(
            update(AuthSession)
            .where(AuthSession.token_hash == digest(old_token))
            .values(revoked_at=now)
        )
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    session = AuthSession(
        user_id=user.id,
        token_hash=digest(token),
        csrf_hash=digest(csrf),
        created_at=now,
        last_seen_at=now,
        expires_at=now + SESSION_LIFETIME,
    )
    db.add(session)
    db.flush()
    audit(db, "auth.login", "success", user=user, entity=str(session.id))
    return Result(200, {"user_id": str(user.id), "csrf_token": csrf}, token, csrf)


def resolve(
    db: Session, token: str | None, *, refresh_session: bool = False
) -> tuple[User, AuthSession] | None:
    if not token or not 40 <= len(token) <= 128:
        return None
    # Lock session while checking/touching it so logout is serialized.
    session = db.scalar(
        select(AuthSession)
        .where(AuthSession.token_hash == digest(token))
        .with_for_update()
        .execution_options(populate_existing=refresh_session)
    )
    if session is None:
        return None
    user = db.get(User, session.user_id)
    now = now_utc()
    if (
        user is None
        or not user.is_active
        or session.revoked_at is not None
        or aware(session.expires_at) <= now
        or aware(session.last_seen_at) <= now - IDLE_LIFETIME
    ):
        return None
    return user, session


def memberships(db: Session, user: User) -> list[str]:
    return list(
        db.scalars(
            select(Scope.key)
            .join(UserScope, UserScope.scope_id == Scope.id)
            .where(UserScope.user_id == user.id)
            .order_by(Scope.key)
        )
    )


def inspect_identity(db: Session, token: str | None, scope: str | None = None) -> Result:
    identity = resolve(db, token)
    if identity is None:
        return denied(db, 401, "auth.session_denied")
    user, session = identity
    scopes = memberships(db, user)
    if scope is not None and (scope not in SCOPES or scope not in scopes):
        return denied(
            db,
            403,
            "auth.scope_denied",
            user=user,
            scope=scope if scope in SCOPES else "technical_admin",
        )
    session.last_seen_at = now_utc()
    audit(
        db,
        "auth.scope_read" if scope else "auth.identity_read",
        "success",
        user=user,
        scope=scope or "technical_admin",
        entity=str(session.id),
    )
    return Result(
        200,
        {"id": str(user.id), "display_name": user.display_name, "scopes": scopes}
        if scope is None
        else {"scope": scope, "allowed": True},
    )


def logout(db: Session, token: str | None, csrf: str | None) -> Result:
    identity = resolve(db, token)
    if identity is None:
        return denied(db, 401, "auth.session_denied")
    user, session = identity
    if not csrf or len(csrf) > 128 or not hmac.compare_digest(session.csrf_hash, digest(csrf)):
        return denied(db, 403, "auth.csrf_denied", user=user)
    session.revoked_at = now_utc()
    audit(db, "auth.logout", "success", user=user, entity=str(session.id))
    return Result(200, {"status": "signed_out"})


def bootstrap_session(db: Session, token: str | None) -> Result:
    current = resolve(db, token)
    if current is None:
        return denied(db, 401, "auth.session_denied")
    user, session = current
    csrf = secrets.token_urlsafe(32)
    session.csrf_hash = digest(csrf)
    session.last_seen_at = now_utc()
    audit(db, "auth.session_bootstrap", "success", user=user, entity=str(session.id))
    return Result(
        200,
        {
            "user": {
                "id": str(user.id),
                "display_name": user.display_name,
                "scopes": memberships(db, user),
            },
            "csrf_token": csrf,
        },
        csrf=csrf,
    )
