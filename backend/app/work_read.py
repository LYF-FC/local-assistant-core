"""Bounded synthetic read broker. The deployed dependency has no engines/credentials."""

import hmac
import json
from collections.abc import Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from app import identity, work_access, work_authority
from app.models import WorkWorkspace
from app.work_storage import role_name


class BrokerUnavailable(Exception):
    pass


class EngineSource(Protocol):
    def lease(self, workspace_id: UUID) -> AbstractContextManager[Engine | None]: ...


@dataclass(frozen=True, repr=False, init=False)
class WorkspaceEngines:
    _engines: Mapping[UUID, Engine] = field(repr=False)

    def __init__(self, engines: Mapping[UUID, Engine]):
        if any(not isinstance(k, UUID) or not isinstance(v, Engine) for k, v in engines.items()):
            raise TypeError("Trusted workspace engine mapping required")
        object.__setattr__(self, "_engines", MappingProxyType(dict(engines)))

    def engine_for(self, workspace_id: UUID) -> Engine | None:
        return self._engines.get(workspace_id)

    @contextmanager
    def lease(self, workspace_id: UUID):
        yield self.engine_for(workspace_id)


def get_work_engines() -> EngineSource | None:
    from app.config import settings
    from app.work_adapter import FileSource

    if not settings.work_synthetic_adapter_enabled:
        return None
    # Configuration only: no file read or database checkout before authorization.
    return FileSource(settings.work_synthetic_secret_directory)


def workspace_engine(url: URL) -> Engine:
    """Trusted explicit configuration only; creates no connection until authorized use."""
    if not isinstance(url, URL):
        raise TypeError("Explicit trusted database URL required")
    if (
        url.drivername != "postgresql+psycopg"
        or url.query
        or not all((url.host, url.database, url.username, url.password))
    ):
        raise BrokerUnavailable("Work validation unavailable")
    return create_engine(
        url, pool_size=2, max_overflow=0, pool_timeout=2, connect_args={"connect_timeout": 3}
    )


def same_target(identity_db: Session, work_engine: Engine) -> None:
    bound = identity_db.get_bind()
    identity_engine = bound if isinstance(bound, Engine) else bound.engine
    a, b = identity_engine.url, work_engine.url
    timeout = work_engine.pool.timeout() if isinstance(work_engine.pool, QueuePool) else None
    if (
        type(timeout) not in {int, float}
        or not 0 <= timeout <= 2
        or a.drivername != "postgresql+psycopg"
        or b.drivername != a.drivername
        or a.query
        or b.query
        or (a.host, a.port or 5432, a.database) != (b.host, b.port or 5432, b.database)
    ):
        raise BrokerUnavailable("Work validation unavailable")


def restricted_identity(connection: Connection, database_oid: int, workspace_id: UUID) -> None:
    row = connection.execute(
        text(
            "SELECT session_user,current_user,current_setting('transaction_isolation'),(SELECT oid FROM pg_database WHERE datname=current_database())"
        )
    ).one()
    login, current, isolation, actual_oid = row
    if login != current or isolation != "read committed" or actual_oid != database_oid:
        raise BrokerUnavailable("Work validation unavailable")
    expected = role_name(database_oid, workspace_id)
    for name, can_login in ((login, True), (expected, False)):
        flags = connection.execute(
            text(
                "SELECT rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:name"
            ),
            {"name": name},
        ).one_or_none()
        if flags is None or tuple(flags) != (can_login, False, False, False, False, False, False):
            raise BrokerUnavailable("Work validation unavailable")
        owned = connection.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_class WHERE relowner=(SELECT oid FROM pg_roles WHERE rolname=:name) UNION ALL SELECT 1 FROM pg_namespace WHERE nspowner=(SELECT oid FROM pg_roles WHERE rolname=:name) UNION ALL SELECT 1 FROM pg_database WHERE datdba=(SELECT oid FROM pg_roles WHERE rolname=:name) UNION ALL SELECT 1 FROM pg_proc WHERE proowner=(SELECT oid FROM pg_roles WHERE rolname=:name))"
            ),
            {"name": name},
        )
        public_access = connection.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m') AND (has_table_privilege(:name,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(:name,c.oid,'SELECT,INSERT,UPDATE,REFERENCES'))) OR has_database_privilege(:name,current_database(),'CREATE,TEMPORARY') OR has_schema_privilege(:name,'public','CREATE') OR has_schema_privilege(:name,'work','CREATE')"
            ),
            {"name": name},
        )
        if owned or public_access:
            raise BrokerUnavailable("Work validation unavailable")
    memberships = connection.execute(
        text(
            "SELECT r.rolname,m.admin_option,m.inherit_option,m.set_option FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname=:login)"
        ),
        {"login": login},
    ).all()
    nested = connection.scalar(
        text(
            "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=:name)"
        ),
        {"name": expected},
    )
    if [tuple(r) for r in memberships] != [(expected, False, False, True)] or nested:
        raise BrokerUnavailable("Work validation unavailable")
    quoted = connection.dialect.identifier_preparer.quote(expected)
    connection.exec_driver_sql(f"SET LOCAL ROLE {quoted}")
    if connection.scalar(text("SELECT current_user")) != expected:
        raise BrokerUnavailable("Work validation unavailable")
    if connection.execute(text("SELECT id FROM work.active_workspace")).all() != [(workspace_id,)]:
        raise BrokerUnavailable("Work validation unavailable")


def record_attempt(
    connection: Connection,
    authority: work_authority.WorkAuthority,
    workspace_id: UUID,
    ids: list[str],
    *,
    denied: bool = False,
) -> str:
    identifier = connection.scalar(
        text(
            "INSERT INTO work.read_attempts (workspace_id,requested_by,session_id,event_type,record_count,record_ids,reason_code) VALUES (:workspace,:actor,:session,:event,:count,CAST(:ids AS jsonb),:reason) RETURNING id"
        ),
        {
            "workspace": workspace_id,
            "actor": authority.user.id,
            "session": authority.session.id,
            "event": "validation.read_denied" if denied else "validation.read_prepared",
            "count": len(ids),
            "ids": json.dumps(ids),
            "reason": "authority_expired" if denied else None,
        },
    )
    return str(identifier)


def read_validation(
    db: Session,
    token: str | None,
    csrf: str | None,
    workspace_id: UUID,
    limit: int,
    engines: EngineSource | None,
) -> identity.Result:
    authority = work_authority.resolve(db, token)
    if isinstance(authority, identity.Result):
        return authority
    user = authority.user
    if (
        not csrf
        or len(csrf) > 128
        or not hmac.compare_digest(authority.session.csrf_hash, identity.digest(csrf))
    ):
        return identity.denied(db, 403, "work.validation_csrf_denied", user=user)
    workspace = db.scalar(work_access.assigned(user).where(WorkWorkspace.id == workspace_id))
    if workspace is None:
        return identity.denied(db, 404, "work.validation_denied", user=user)
    if type(limit) is not int or not 1 <= limit <= 25:
        return identity.Result(422, {"detail": "Invalid request"})
    if engines is None:
        identity.audit(
            db,
            "work.validation_unavailable",
            "denied",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
        )
        return identity.Result(503, {"detail": "Work validation unavailable"})
    try:
        with engines.lease(workspace_id) as engine:
            if engine is None:
                raise BrokerUnavailable("Work validation unavailable")
            same_target(db, engine)
            database_oid = db.scalar(
                text("SELECT oid FROM pg_database WHERE datname=current_database()")
            )
            with engine.connect() as connection, connection.begin():
                connection.execute(text("SET LOCAL lock_timeout='2s'"))
                connection.execute(text("SET LOCAL statement_timeout='5s'"))
                try:
                    restricted_identity(connection, database_oid, workspace_id)
                except BrokerUnavailable:
                    connection.invalidate()
                    raise
                expired = authority.checked_now() is None
                rows = []
                if not expired:
                    rows = connection.execute(
                        text(
                            "SELECT id,marker,created_at FROM work.validation_records WHERE workspace_id=:workspace ORDER BY id LIMIT :limit"
                        ),
                        {"workspace": workspace_id, "limit": limit + 1},
                    ).all()
                    expired = authority.checked_now() is None
                ids = [] if expired else [str(row.id) for row in rows[:limit]]
                audit_id = record_attempt(connection, authority, workspace_id, ids, denied=expired)
        # Recheck after the credential lease has closed every connection.
        checked = authority.checked_now()
        if expired or checked is None:
            return identity.denied(db, 401, "work.validation_expired", user=user)
        items = [
            {
                "id": str(row.id),
                "marker": row.marker,
                "created_at": identity.aware(row.created_at).isoformat(),
            }
            for row in rows[:limit]
        ]
        authority.session.last_seen_at = checked
        identity.audit(
            db,
            "work.validation_read",
            "success",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
            metadata={"work_attempt_id": audit_id, "record_count": len(items)},
        )
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "mode": "synthetic_storage_preview",
                "workspace_id": str(workspace_id),
                "checked_at": checked.isoformat(),
                "work_attempt_id": audit_id,
                "items": items,
                "has_more": len(rows) > limit,
                "ingestion_allowed": False,
                "model_invoked": False,
                "execution_allowed": False,
            },
        )
    except (SQLAlchemyError, BrokerUnavailable):
        identity.audit(
            db,
            "work.validation_unavailable",
            "denied",
            user=user,
            entity=str(workspace_id),
            entity_type="work_access_registry",
        )
        return identity.Result(503, {"detail": "Work validation unavailable"})
