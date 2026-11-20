"""Read-only identity checks for a disposable synthetic restored database.

This report is never activation authority. In particular, a matching installation
and migration head say nothing about newer forgetting decisions or external effects.
"""

import os
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings


@dataclass(frozen=True)
class BindingReport:
    binding_valid: bool
    reasons: tuple[str, ...]

    @property
    def quarantined(self) -> bool:
        return True

    @property
    def restore_eligible(self) -> bool:
        return False


def inspect_restored_binding(
    connection: Connection, *, installation_id: str, schema_head: str
) -> BindingReport:
    """Compare trusted expectations with singleton rows, without changing the DB.

    Only explicitly opted-in disposable test databases are supported by this first
    slice. The caller must keep every restored target isolated; this function does
    not provision isolation or make an arbitrary target safe to restore into.
    """
    try:
        valid_id = str(UUID(installation_id)) == installation_id
    except (ValueError, TypeError, AttributeError):
        valid_id = False
    if (
        not valid_id
        or not isinstance(schema_head, str)
        or not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", schema_head)
    ):
        raise ValueError("Explicit canonical binding expectations required")
    if (
        not isinstance(connection, Connection)
        or connection.dialect.name != "postgresql"
        or settings.env != "test"
        or os.environ.get("BUTLER_RUN_DB_TESTS") != "1"
    ):
        raise ValueError("Explicit disposable PostgreSQL test connection required")

    try:
        database = connection.scalar(text("SELECT current_database()"))
        if not isinstance(database, str) or not database.startswith("butler_test"):
            raise ValueError("Disposable test database required")
        # A savepoint preserves the caller's transaction if malformed restored
        # metadata makes one of the read-only statements fail.
        with connection.begin_nested():
            tables = connection.execute(
                text(
                    "SELECT to_regclass('public.installation_config'), "
                    "to_regclass('public.alembic_version')"
                )
            ).one()
            if any(table is None for table in tables):
                return BindingReport(False, ("binding_metadata_missing",))
            identities = connection.execute(
                text("SELECT id, installation_id FROM public.installation_config LIMIT 2")
            ).all()
            heads = connection.execute(
                text("SELECT version_num FROM public.alembic_version LIMIT 2")
            ).all()
            if (
                len(identities) != 1
                or type(identities[0][0]) is not int
                or identities[0][0] != 1
                or len(heads) != 1
            ):
                return BindingReport(False, ("binding_metadata_shape_invalid",))
            reasons = []
            if str(identities[0][1]) != installation_id:
                reasons.append("restored_installation_mismatch")
            if heads[0][0] != schema_head:
                reasons.append("restored_schema_head_mismatch")
            return BindingReport(not reasons, tuple(reasons))
    except SQLAlchemyError:
        return BindingReport(False, ("binding_metadata_unreadable",))
