import json
import os
import sys
import warnings
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from test_memory import signin
from test_work_access import URL, setup_work

from app import work_adapter as adapter
from app import work_read
from app.config import settings

SECRET = "synthetic-file-work-secret-0123456789012345"


@pytest.fixture
def bundle(monkeypatch):
    monkeypatch.setattr(settings, "postgres_db", "butler_test_file")
    return adapter.Bundle(
        schema_version=1,
        environment="test",
        database=settings.postgres_db,
        database_oid=123,
        workspace_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        password=SECRET,
    )


def test_private_create_only_publication_and_no_secret_repr(tmp_path, bundle):
    tmp_path.chmod(0o700)
    adapter.publish(tmp_path, bundle)
    loaded = adapter.load_bundle(tmp_path)
    assert loaded.password.get_secret_value() == SECRET
    assert SECRET not in repr(loaded)
    assert loaded.workspace_id == bundle.workspace_id
    assert (tmp_path / adapter.FILE).stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        adapter.publish(tmp_path, bundle)
    assert list(tmp_path.iterdir()) == [tmp_path / adapter.FILE]


@pytest.mark.parametrize(
    "fault",
    [
        "directory_mode",
        "file_mode",
        "file_symlink",
        "directory_symlink",
        "hardlink",
        "oversize",
        "fifo",
        "owner",
        "missing",
        "malformed",
        "duplicate",
    ],
)
def test_protected_source_refuses_unsafe_files(tmp_path, bundle, fault, monkeypatch):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    adapter.publish(root, bundle)
    path = root / adapter.FILE
    if fault == "directory_mode":
        root.chmod(0o755)
    elif fault == "file_mode":
        path.chmod(0o644)
    elif fault in {"file_symlink", "fifo", "missing"}:
        path.unlink()
        if fault == "file_symlink":
            path.symlink_to(tmp_path / "nonexistent")
        elif fault == "fifo":
            os.mkfifo(path, mode=0o600)
    elif fault == "directory_symlink":
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        root = link
    elif fault == "hardlink":
        os.link(path, root / "another")
    elif fault == "oversize":
        path.write_bytes(b"x" * (adapter.MAX_BYTES + 1))
    elif fault == "owner":
        monkeypatch.setattr(adapter.os, "geteuid", lambda: path.stat().st_uid + 1)
    elif fault == "malformed":
        path.write_bytes(b"invalid-json")
    elif fault == "duplicate":
        path.write_text('{"schema_version":1,"schema_version":1}')
    with (
        pytest.raises(work_read.BrokerUnavailable),
        adapter.FileSource(root).lease(bundle.workspace_id),
    ):
        pytest.fail("Unsafe source must never yield an engine")


@pytest.mark.parametrize(
    "fault",
    [
        "environment",
        "database",
        "oid",
        "workspace",
        "expired",
        "naive",
        "long_lived",
        "extra_field",
        "boolean_version",
        "short_secret",
    ],
)
def test_bundle_binding_and_schema_fail_closed(tmp_path, bundle, fault):
    tmp_path.chmod(0o700)
    adapter.publish(tmp_path, bundle)
    path = tmp_path / adapter.FILE
    value = json.loads(path.read_text())
    fields = {
        "environment": ("environment", "production"),
        "database": ("database", "unapproved_database"),
        "oid": ("database_oid", "123"),
        "workspace": ("workspace_id", str(uuid4())),
        "expired": ("expires_at", (datetime.now(UTC) - timedelta(seconds=1)).isoformat()),
        "naive": ("expires_at", datetime.now().isoformat()),
        "long_lived": ("expires_at", (datetime.now(UTC) + timedelta(days=3)).isoformat()),
        "extra_field": ("dsn", "unapproved"),
        "boolean_version": ("schema_version", True),
        "short_secret": ("password", "short"),
    }
    key, replacement = fields[fault]
    value[key] = replacement
    path.write_text(json.dumps(value))
    with (
        pytest.raises(work_read.BrokerUnavailable),
        adapter.FileSource(tmp_path).lease(bundle.workspace_id),
    ):
        pytest.fail("Invalid bundle must never yield")


def test_each_lease_builds_and_disposes_its_own_engine_even_on_failure(
    tmp_path, bundle, monkeypatch
):
    tmp_path.chmod(0o700)
    adapter.publish(tmp_path, bundle)
    created, disposed = [], []

    class Engine:
        def dispose(self):
            disposed.append(self)

    def build(url):
        assert url.host == settings.postgres_host and url.database == settings.postgres_db
        assert url.username == adapter.login_name(bundle.database_oid, bundle.workspace_id)
        assert url.password == SECRET and not url.query
        engine = Engine()
        created.append(engine)
        return engine

    monkeypatch.setattr(adapter, "workspace_engine", build)
    source = adapter.FileSource(tmp_path)
    for _ in range(2):
        with pytest.raises(RuntimeError), source.lease(bundle.workspace_id):
            raise RuntimeError("synthetic operation failure")
    assert len(created) == 2 and created == disposed and created[0] is not created[1]


def test_unauthorized_requests_never_read_secret_file(
    auth_client, auth_store, monkeypatch, tmp_path
):
    ids = setup_work(auth_store)
    monkeypatch.setattr(settings, "work_synthetic_adapter_enabled", True)
    monkeypatch.setattr(settings, "work_synthetic_secret_directory", tmp_path)
    calls = []

    def unavailable(directory):
        calls.append(True)
        raise FileNotFoundError("synthetic-private-location")

    monkeypatch.setattr(adapter, "load_bundle", unavailable)
    url = f"{URL}/{ids['synthetic-team-a']}/validation-read"
    assert auth_client.post(url, json={}).status_code == 401
    headers = signin(auth_client)
    assert auth_client.post(url, json={}).status_code == 403
    assert (
        auth_client.post(
            f"{URL}/{ids['synthetic-team-b']}/validation-read", json={}, headers=headers
        ).status_code
        == 404
    )
    assert calls == []
    response = auth_client.post(url, json={}, headers=headers)
    assert response.status_code == 503 and "synthetic-private-location" not in response.text
    assert calls == [True]


def test_disabled_source_never_accesses_configured_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "work_synthetic_adapter_enabled", False)
    monkeypatch.setattr(settings, "work_synthetic_secret_directory", tmp_path)
    assert work_read.get_work_engines() is None


def cli(monkeypatch, directory):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "work_adapter",
            "--environment",
            "test",
            "--workspace",
            "synthetic-unit",
            "--directory",
            str(directory),
        ],
    )


def test_prepare_cli_non_tty_and_echo_fallback_fail_without_publication(
    tmp_path, bundle, monkeypatch
):
    tmp_path.chmod(0o700)
    cli(monkeypatch, tmp_path)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit):
        adapter.main()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def cannot_hide(prompt):
        warnings.warn("Echo unavailable", adapter.getpass.GetPassWarning, stacklevel=1)
        pytest.fail("Must stop before reading visible input")

    monkeypatch.setattr(adapter.getpass, "getpass", cannot_hide)
    with pytest.raises(SystemExit):
        adapter.main()
    assert list(tmp_path.iterdir()) == []


def test_prepare_commit_failure_never_publishes_or_echoes_secret(
    tmp_path, bundle, monkeypatch, capsys
):
    tmp_path.chmod(0o700)
    cli(monkeypatch, tmp_path)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(adapter.getpass, "getpass", lambda prompt: SECRET)

    @contextmanager
    def failure(**kwargs):
        yield object()
        raise adapter.psycopg.OperationalError("synthetic-private-driver-context")

    monkeypatch.setattr(adapter.psycopg, "connect", failure)
    monkeypatch.setattr(adapter, "prepare", lambda connection, slug, secret: bundle)
    with pytest.raises(SystemExit):
        adapter.main()
    output = capsys.readouterr()
    assert SECRET not in output.err + output.out
    assert "synthetic-private-driver-context" not in output.err + output.out
    assert list(tmp_path.iterdir()) == []
