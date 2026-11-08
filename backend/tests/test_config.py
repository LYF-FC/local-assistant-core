import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize("password", ["short", "CHANGE_ME_WITH_A_LONG_RANDOM_VALUE"])
def test_unsafe_passwords_rejected(password):
    with pytest.raises(ValidationError):
        Settings(postgres_password=password)


def test_password_is_masked_and_url_escaped():
    password = "a@b:with/%special#symbols-123456789"
    config = Settings(postgres_password=password)
    assert password not in repr(config)
    from sqlalchemy.engine import make_url

    assert make_url(config.database_url).password == password


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com",
        "http://unapproved.lan:11434",
        "http://localhost.evil:11434",
        "http://user:secret@localhost:11434",
        "file:///etc/passwd",
        "http://localhost?target=cloud",
    ],
)
def test_unapproved_runtime_urls_rejected(url):
    with pytest.raises(ValidationError):
        Settings(ollama_url=url)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_unfinished_release_cannot_start_in_protected_environments(monkeypatch, environment):
    from app.main import settings

    monkeypatch.setattr(settings, "env", environment)
    with pytest.raises(RuntimeError, match="production gates"):
        create_app()


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8443",
        "https://localhost:8443/",
        "https://user:secret@localhost",
        "https://localhost?query=1",
    ],
)
def test_auth_origin_requires_exact_https_origin(origin):
    with pytest.raises(ValidationError):
        Settings(auth_origin=origin)


def test_development_api_rejects_migration_credentials(monkeypatch):
    from app.main import create_app, settings

    monkeypatch.setattr(settings, "env", "development")
    monkeypatch.setattr(settings, "postgres_user", "migration_owner")
    with pytest.raises(RuntimeError, match="restricted"):
        create_app()
