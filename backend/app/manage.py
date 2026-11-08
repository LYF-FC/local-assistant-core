"""Trusted local administration. No public endpoint and no password CLI argument."""

import argparse
import re
import sys
from getpass import getpass

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app import identity
from app.config import settings
from app.db import SessionLocal
from app.models import AuditEvent, AuthSession, Credential, Scope, User, UserScope


def record(db: Session, event: str, user: User, before=None, after=None) -> None:
    db.add(
        AuditEvent(
            environment=settings.env,
            initiator_type="local_admin",
            initiator_id="trusted_host_operator",
            scope_key="technical_admin",
            event_type=event,
            entity_type="user",
            entity_id=str(user.id),
            result_status="success",
            before_json=before,
            after_json=after,
            source_context={},
            metadata_json={},
        )
    )
    db.flush()


def provision(db: Session, slug: str, display_name: str, password: str, scopes: set[str]) -> User:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", slug):
        raise ValueError("Invalid user slug")
    if (
        not display_name.strip()
        or len(display_name) > 128
        or any(ord(x) < 32 for x in display_name)
    ):
        raise ValueError("Invalid display name")
    if not scopes <= identity.SCOPES:
        raise ValueError("Unknown scope")
    if db.scalar(select(User).where(User.slug == slug)):
        raise ValueError("User already exists")
    records = list(db.scalars(select(Scope).where(Scope.key.in_(scopes))))
    if len(records) != len(scopes):
        raise ValueError("Scope migrations are incomplete")
    hashed = identity.password_hash(password)
    user = User(slug=slug, display_name=display_name.strip())
    db.add(user)
    db.flush()
    db.add(Credential(user_id=user.id, password_hash=hashed, changed_at=identity.now_utc()))
    for scope in records:
        db.add(UserScope(user_id=user.id, scope_id=scope.id))
    record(db, "admin.user_created", user, after={"scopes": sorted(scopes)})
    return user


def revoke_sessions(db: Session, user: User) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=identity.now_utc())
    )


def replace_password(db: Session, user: User, password: str) -> None:
    credential = db.get(Credential, user.id)
    if credential is None:
        raise ValueError("User has no credential")
    credential.password_hash = identity.password_hash(password)
    credential.changed_at = identity.now_utc()
    revoke_sessions(db, user)
    record(db, "admin.password_changed", user)


def set_active(db: Session, user: User, active: bool) -> None:
    before = user.is_active
    user.is_active = active
    if not active:
        revoke_sessions(db, user)
    record(db, "admin.user_status_changed", user, {"active": before}, {"active": active})


def set_scope(db: Session, user: User, key: str, grant: bool) -> None:
    if key not in identity.SCOPES:
        raise ValueError("Unknown scope")
    scope = db.scalar(select(Scope).where(Scope.key == key))
    if scope is None:
        raise ValueError("Scope migrations are incomplete")
    before = identity.memberships(db, user)
    membership = db.get(UserScope, (user.id, scope.id))
    if grant and membership is None:
        db.add(UserScope(user_id=user.id, scope_id=scope.id))
    elif not grant:
        db.execute(
            delete(UserScope).where(UserScope.user_id == user.id, UserScope.scope_id == scope.id)
        )
    db.flush()
    record(
        db,
        "admin.scope_changed",
        user,
        {"scopes": before},
        {"scopes": identity.memberships(db, user)},
    )


def read_password() -> str:
    if not sys.stdin.isatty():
        raise ValueError("Password administration requires an interactive local terminal")
    password = getpass("New password: ")
    if password != getpass("Repeat password: "):
        raise ValueError("Passwords differ")
    return password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument(
        "action",
        choices=[
            "create-user",
            "set-password",
            "disable-user",
            "enable-user",
            "grant-scope",
            "revoke-scope",
        ],
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--display-name")
    parser.add_argument("--scope", action="append", default=[])
    args = parser.parse_args()
    if settings.env != args.environment:
        parser.error("Environment does not match the configured development/test target")
    if args.action == "create-user" and not args.display_name:
        parser.error("--display-name is required")
    if args.action in {"grant-scope", "revoke-scope"} and len(args.scope) != 1:
        parser.error("Exactly one --scope is required")
    password = read_password() if args.action in {"create-user", "set-password"} else None
    with SessionLocal.begin() as db:
        if args.action == "create-user":
            provision(db, args.slug, args.display_name, password, set(args.scope))
        else:
            user = db.scalar(select(User).where(User.slug == args.slug).with_for_update())
            if user is None:
                raise ValueError("User not found")
            if args.action == "set-password":
                replace_password(db, user, password)
            elif args.action in {"enable-user", "disable-user"}:
                set_active(db, user, args.action == "enable-user")
            else:
                set_scope(db, user, args.scope[0], args.action == "grant-scope")
    print("Local administration committed; no secrets are displayed")


if __name__ == "__main__":
    main()
