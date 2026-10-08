import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_read_the_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXTPAY_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/nextpay")
    monkeypatch.setenv("NEXTPAY_SQL_ECHO", "true")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert str(settings.database_url) == "postgresql+psycopg://u:p@db:5432/nextpay"
    assert settings.sql_echo is True


def test_settings_require_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXTPAY_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)  # type: ignore[call-arg]
