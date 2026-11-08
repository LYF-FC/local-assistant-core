"""Opt-in local synthetic credential file; no secret or connection cache."""

import argparse
import getpass
import json
import os
import stat
import sys
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from sqlalchemy.engine import URL

from app.config import settings
from app.work_authority import REGISTRY_KEY
from app.work_credentials import check_role, login_name, validate_password, validate_target
from app.work_read import BrokerUnavailable, workspace_engine
from app.work_storage import role_name

FILE = "adapter.json"
MAX_BYTES = 4096


class Bundle(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    schema_version: int = Field(strict=True, ge=1, le=1)
    environment: str
    database: str
    database_oid: int = Field(strict=True, ge=1, le=4294967295)
    workspace_id: UUID
    expires_at: datetime
    password: SecretStr = Field(repr=False)

    def check(self) -> None:
        validate_target(self.environment)
        validate_password(self.password.get_secret_value())
        now = datetime.now(UTC)
        if (
            self.database != settings.postgres_db
            or self.expires_at.tzinfo is None
            or not now < self.expires_at <= now + timedelta(hours=25)
        ):
            raise ValueError("Invalid local credential binding or expiry")


@contextmanager
def private_directory(directory: Path | None):
    if directory is None or not directory.is_absolute():
        raise ValueError("Absolute private directory required")
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("Owned mode-0700 directory required")
        yield fd
    finally:
        os.close(fd)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate credential field")
        result[key] = value
    return result


def load_bundle(directory: Path | None) -> Bundle:
    with private_directory(directory) as parent:
        fd = os.open(
            FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent
        )
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
                or not 1 <= info.st_size <= MAX_BYTES
            ):
                raise ValueError("Protected bounded regular credential file required")
            data = os.read(fd, MAX_BYTES + 1)
        finally:
            os.close(fd)
    if len(data) > MAX_BYTES:
        raise ValueError("Credential file too large")
    bundle = Bundle.model_validate(json.loads(data, object_pairs_hook=unique_object))
    bundle.check()
    return bundle


def publish(directory: Path, bundle: Bundle) -> None:
    """Create-only atomic publication. Caller already recorded preparation audit."""
    bundle.check()
    body = bundle.model_dump(mode="json")
    body["password"] = bundle.password.get_secret_value()
    encoded = json.dumps(body).encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise ValueError("Credential file too large")
    with private_directory(directory) as parent:
        temporary = ".stage-" + uuid4().hex
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent,
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, FILE, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        finally:
            os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)


@dataclass(frozen=True, repr=False)
class FileSource:
    directory: Path | None

    @contextmanager
    def lease(self, workspace_id: UUID):
        engine = None
        try:
            bundle = load_bundle(self.directory)
            if bundle.workspace_id != workspace_id:
                raise ValueError("Workspace binding mismatch")
            engine = workspace_engine(
                URL.create(
                    "postgresql+psycopg",
                    host=settings.postgres_host,
                    port=settings.postgres_port,
                    database=settings.postgres_db,
                    username=login_name(bundle.database_oid, workspace_id),
                    password=bundle.password.get_secret_value(),
                )
            )
        except (OSError, ValueError, ValidationError, UnicodeError):
            raise BrokerUnavailable("Work validation unavailable") from None
        try:
            yield engine
        finally:
            if engine is not None:
                engine.dispose()


def prepare(connection, workspace_slug: str, password: str) -> Bundle:
    """Verify only a disabled synthetic managed login; audit preparation, not delivery."""
    import re

    validate_target(settings.env)
    validate_password(password)
    if not re.fullmatch(r"synthetic-[a-z0-9][a-z0-9_-]{0,53}", workspace_slug):
        raise ValueError("Synthetic workspace required")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT session_user=current_user,rolsuper,current_setting('transaction_isolation') FROM pg_roles WHERE rolname=current_user"
        )
        if cursor.fetchone() != (True, True, "read committed"):
            raise ValueError("Clean privileged connection required")
        cursor.execute("SET LOCAL lock_timeout='2s'")
        cursor.execute("SET LOCAL statement_timeout='5s'")
        cursor.execute("SELECT pg_advisory_xact_lock(%s,%s)", REGISTRY_KEY)
        cursor.execute(
            "SELECT id,is_active FROM public.work_workspaces WHERE slug=%s FOR UPDATE",
            (workspace_slug,),
        )
        row = cursor.fetchone()
        if row is None or row[1]:
            raise ValueError("Disabled synthetic workspace required")
        workspace = row[0]
        cursor.execute("SELECT oid FROM pg_database WHERE datname=current_database()")
        oid = cursor.fetchone()[0]
        login = login_name(oid, workspace)
        check_role(cursor, role_name(oid, workspace), login=False, expected_membership=None)
        check_role(cursor, login, login=True, expected_membership=role_name(oid, workspace))
        cursor.execute("SELECT rolvaliduntil FROM pg_roles WHERE rolname=%s", (login,))
        expiry = cursor.fetchone()[0]
        bundle = Bundle(
            schema_version=1,
            environment=settings.env,
            database=settings.postgres_db,
            database_oid=oid,
            workspace_id=workspace,
            expires_at=expiry,
            password=SecretStr(password),
        )
        bundle.check()
        # New TCP authentication, no privileged fallback and no marker read.
        with psycopg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=login,
            password=password,
            connect_timeout=3,
        ) as probe:
            if probe.execute("SELECT session_user,current_user").fetchone() != (login, login):
                raise ValueError("Unexpected login identity")
        cursor.execute(
            "INSERT INTO public.audit_events (id,occurred_at,environment,initiator_type,initiator_id,scope_key,event_type,entity_type,entity_id,result_status,source_context,metadata_json) VALUES (gen_random_uuid(),statement_timestamp(),%s,'local_admin','trusted_host_operator','technical_admin','admin.work_secret_prepared','work_access_registry',%s,'prepared','{}','{}')",
            (settings.env, str(workspace)),
        )
        return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=["development", "test"])
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        validate_target(args.environment)
        # Reject unsafe/occupied destination before prompting or touching the database.
        with private_directory(args.directory) as parent:
            try:
                os.stat(FILE, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("Credential destination already exists")
        if not sys.stdin.isatty():
            raise ValueError("Hidden local TTY input required")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("Current generated workspace secret: ")
        with psycopg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password.get_secret_value(),
            connect_timeout=5,
        ) as connection:
            bundle = prepare(connection, args.workspace, password)
        # DB prepared audit is committed before publication, with honest non-atomic semantics.
        publish(args.directory, bundle)
    except (
        OSError,
        psycopg.Error,
        ValueError,
        EOFError,
        KeyboardInterrupt,
        getpass.GetPassWarning,
    ):
        parser.exit(
            1,
            "Synthetic adapter preparation failed; inspect protected local configuration. No workspace enabled.\n",
        )
    print(
        "Synthetic credential file prepared; explicit adapter opt-in and workspace enable still required"
    )


if __name__ == "__main__":
    main()
