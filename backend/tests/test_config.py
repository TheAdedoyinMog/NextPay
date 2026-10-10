import pytest
from pydantic import ValidationError

from app.core.config import DatabaseSettings, Settings, get_settings

SECRET = "s" * 32


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
