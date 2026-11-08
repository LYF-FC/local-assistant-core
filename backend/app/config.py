from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BUTLER_", extra="ignore", hide_input_in_errors=True
    )

    env: Literal["development", "test", "staging", "production"] = "development"
    postgres_db: str = "butler"
    postgres_user: str = "butler"
    postgres_password: SecretStr
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    ollama_url: str = "http://host.docker.internal:11434"
    auth_origin: str = "https://localhost:8443"
    speech_enabled: bool = False
    speech_model: str = "phonon:40m-multilingual"
    speech_voice: str = "default"
    app_version: str = "0.1.0-dev"
    work_synthetic_adapter_enabled: bool = False
    work_draft_review_enabled: bool = False
    work_draft_confirmation_enabled: bool = False
    work_context_preview_enabled: bool = False
    work_synthetic_capture_enabled: bool = False
    work_note_changes_enabled: bool = False
    work_notes_interface_enabled: bool = False
    work_notes_export_enabled: bool = False
    work_synthetic_secret_directory: Path | None = None

    @field_validator("postgres_password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if len(password) < 24 or "CHANGE_ME" in password.upper():
            raise ValueError("A generated database password of at least 24 characters is required")
        return value

    @field_validator("ollama_url")
    @classmethod
    def local_runtime_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Only the approved local runtime address is supported")
        return value.rstrip("/")

    @field_validator("auth_origin")
    @classmethod
    def valid_auth_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("An exact HTTPS origin without path or credentials is required")
        # Accessing port also rejects malformed or out-of-range ports.
        _ = parsed.port
        return value

    @property
    def database_url(self) -> str:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
