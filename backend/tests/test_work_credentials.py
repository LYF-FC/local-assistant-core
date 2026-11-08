import sys
import warnings
from uuid import UUID

import pytest

from app import work_credentials as credentials


def test_credential_name_is_database_workspace_bound_and_bounded():
    name = credentials.login_name(4294967295, UUID(int=1))
    assert name == "butler_wlogin_4294967295_00000000000000000000000000000001"
    assert len(name) <= 63
    assert name != credentials.login_name(1, UUID(int=1))
    assert name != credentials.login_name(4294967295, UUID(int=2))


@pytest.mark.parametrize(
    "password",
    [None, "", "a" * 31, "a" * 257, "a" * 32 + "\n", "é" * 32, " " * 32, "CHANGE_ME" * 5],
)
def test_secret_validation_never_echoes_input(password):
    with pytest.raises(ValueError) as error:
        credentials.validate_password(password)
    assert str(error.value) == "Use a distinct generated 32–256 character printable ASCII secret"


def test_secret_must_differ_from_migration_secret():
    with pytest.raises(ValueError):
        credentials.validate_password(credentials.settings.postgres_password.get_secret_value())
    credentials.validate_password("synthetic-work-credential-only-0123456789")


@pytest.mark.parametrize("environment", ["development", "production", "staging", "unknown"])
def test_target_refuses_unmatched_or_live_environment(environment):
    with pytest.raises(ValueError):
        credentials.validate_target(environment)


def test_test_database_must_be_disposable(monkeypatch):
    monkeypatch.setattr(credentials.settings, "postgres_db", "butler")
    with pytest.raises(ValueError):
        credentials.validate_target("test")


def invoke(monkeypatch, action="bootstrap"):
    monkeypatch.setattr(credentials.settings, "postgres_db", "butler_test_unit")
    monkeypatch.setattr(
        sys,
        "argv",
        ["work_credentials", "--environment", "test", action, "--workspace", "synthetic-unit"],
    )


def test_cli_noninteractive_input_never_connects(monkeypatch, capsys):
    invoke(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    calls = []
    monkeypatch.setattr(credentials.psycopg, "connect", lambda **kw: calls.append(True))
    with pytest.raises(SystemExit) as error:
        credentials.main()
    assert error.value.code == 1 and calls == []
    assert "No adapter activated" in capsys.readouterr().err


def test_cli_confirmation_mismatch_never_connects_or_echoes(monkeypatch, capsys):
    invoke(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    values = iter(["synthetic-secret-entry-0123456789012345", "different-synthetic-entry"])
    monkeypatch.setattr(credentials.getpass, "getpass", lambda prompt: next(values))
    calls = []
    monkeypatch.setattr(credentials.psycopg, "connect", lambda **kw: calls.append(True))
    with pytest.raises(SystemExit):
        credentials.main()
    output = capsys.readouterr()
    assert calls == [] and "synthetic-secret-entry" not in output.err + output.out


def test_cli_sanitizes_driver_errors_and_revoke_needs_no_prompt(monkeypatch, capsys):
    invoke(monkeypatch, "revoke")

    def forbidden(prompt):
        pytest.fail("Revoke must not request a secret")

    def fail(**kwargs):
        raise credentials.psycopg.OperationalError("synthetic-driver-private-detail")

    monkeypatch.setattr(credentials.getpass, "getpass", forbidden)
    monkeypatch.setattr(credentials.psycopg, "connect", fail)
    with pytest.raises(SystemExit):
        credentials.main()
    output = capsys.readouterr()
    assert "synthetic-driver-private-detail" not in output.err + output.out


def test_cli_refuses_visible_password_fallback(monkeypatch):
    invoke(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def cannot_hide(prompt):
        warnings.warn("Echo unavailable", credentials.getpass.GetPassWarning, stacklevel=1)
        pytest.fail("Must stop before reading visible input")

    monkeypatch.setattr(credentials.getpass, "getpass", cannot_hide)
    with pytest.raises(SystemExit) as error:
        credentials.main()
    assert error.value.code == 1


@pytest.mark.parametrize(
    "action,slug,password",
    [
        ("sql", "synthetic-a", None),
        ("bootstrap", "real-employer", "a" * 32),
        ("revoke", "synthetic-a", "a" * 32),
    ],
)
def test_invalid_operation_never_opens_cursor(monkeypatch, action, slug, password):
    monkeypatch.setattr(credentials.settings, "postgres_db", "butler_test_unit")
    with pytest.raises(ValueError):
        credentials.administer(None, action, slug, password)


def test_imported_administration_cannot_target_production(monkeypatch):
    monkeypatch.setattr(credentials.settings, "env", "production")
    with pytest.raises(ValueError):
        credentials.administer(None, "revoke", "synthetic-a")
