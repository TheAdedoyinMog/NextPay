from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core import config
from app.core.config import (
    DatabaseSettings,
    Settings,
    SettingsError,
    get_database_settings,
    get_settings,
)
from app.main import app

SECRET = "s" * 32
DATABASE_URL = "postgresql+psycopg://u:p@db:5432/nextpay"


@pytest.fixture(autouse=True)
def no_env_file(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A developer's real .env must not change these tests' results."""
    monkeypatch.setattr(config, "ENV_FILE", None)
    get_settings.cache_clear()
    get_database_settings.cache_clear()
    yield
    get_settings.cache_clear()
    get_database_settings.cache_clear()


def test_settings_read_the_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXTPAY_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/nextpay")
    monkeypatch.setenv("NEXTPAY_SQL_ECHO", "true")
    monkeypatch.setenv("NEXTPAY_JWT_SECRET", SECRET)
    monkeypatch.setenv("NEXTPAY_ACCESS_TOKEN_TTL_MINUTES", "5")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert str(settings.database_url) == "postgresql+psycopg://u:p@db:5432/nextpay"
    assert settings.sql_echo is True
    assert settings.jwt_secret.get_secret_value() == SECRET
    assert settings.access_token_ttl_minutes == 5
    assert settings.refresh_token_ttl_days == 30
    assert SECRET not in repr(settings)


@pytest.mark.parametrize("missing", ["NEXTPAY_DATABASE_URL", "NEXTPAY_JWT_SECRET"])
def test_settings_require_the_database_url_and_jwt_secret(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setenv("NEXTPAY_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/nextpay")
    monkeypatch.setenv("NEXTPAY_JWT_SECRET", SECRET)
    monkeypatch.delenv(missing)
    with pytest.raises(ValidationError, match=missing.removeprefix("NEXTPAY_").lower()):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_a_short_jwt_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXTPAY_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/nextpay")
    monkeypatch.setenv("NEXTPAY_JWT_SECRET", "too-short")
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_database_settings_need_no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Migrations and the engine read only these, so they run without the JWT secret."""
    monkeypatch.setenv("NEXTPAY_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/nextpay")
    monkeypatch.delenv("NEXTPAY_JWT_SECRET", raising=False)
    settings = DatabaseSettings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database_url.path == "/nextpay"


def test_get_settings_reads_the_environment_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXTPAY_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/nextpay")
    monkeypatch.setenv("NEXTPAY_JWT_SECRET", SECRET)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.jwt_secret.get_secret_value() == SECRET
        assert get_settings() is settings
    finally:
        get_settings.cache_clear()


def test_a_missing_setting_names_the_variable_and_the_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXTPAY_DATABASE_URL", raising=False)
    monkeypatch.setenv("NEXTPAY_JWT_SECRET", SECRET)
    with pytest.raises(SettingsError) as raised:
        get_settings()
    message = str(raised.value)
    assert "NEXTPAY_DATABASE_URL: Field required" in message
    assert "Copy-Item .env.example .env" in message
    assert "JWT_SECRET" not in message  # only what is actually wrong


def test_a_rejected_value_is_never_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXTPAY_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("NEXTPAY_JWT_SECRET", "short-but-secret")
    with pytest.raises(SettingsError, match="NEXTPAY_JWT_SECRET") as raised:
        get_settings()
    assert "short-but-secret" not in str(raised.value)


def test_migrations_get_the_same_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXTPAY_DATABASE_URL", raising=False)
    with pytest.raises(SettingsError, match="NEXTPAY_DATABASE_URL"):
        get_database_settings()


def test_the_env_file_is_read_and_the_environment_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join([f"NEXTPAY_DATABASE_URL={DATABASE_URL}", f"NEXTPAY_JWT_SECRET={'f' * 32}"])
    )
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("NEXTPAY_DATABASE_URL", raising=False)
    monkeypatch.setenv("NEXTPAY_JWT_SECRET", SECRET)
    settings = get_settings()
    assert str(settings.database_url) == DATABASE_URL
    assert settings.jwt_secret.get_secret_value() == SECRET


def test_the_api_refuses_to_start_without_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXTPAY_DATABASE_URL", raising=False)
    monkeypatch.setenv("NEXTPAY_JWT_SECRET", SECRET)
    with pytest.raises(SettingsError, match="NEXTPAY_DATABASE_URL"), TestClient(app):
        pass  # entering the client runs startup


def test_the_api_starts_with_valid_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXTPAY_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("NEXTPAY_JWT_SECRET", SECRET)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
