"""Typed application settings, read from environment variables (ADR 0007).

Every variable is prefixed ``NEXTPAY_``. A ``.env`` file in the working directory
is read too, for local development; see ``.env.example`` at the repository root.
"""

from functools import lru_cache

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """What anything touching the database needs, migrations included: no secrets."""

    model_config = SettingsConfigDict(env_prefix="NEXTPAY_", env_file=".env", extra="ignore")

    # SQLAlchemy URL with the psycopg 3 driver, e.g.
    # postgresql+psycopg://nextpay:nextpay@localhost:5432/nextpay
    database_url: PostgresDsn
    # Log every SQL statement; for debugging only.
    sql_echo: bool = False


class Settings(DatabaseSettings):
    """Everything the API needs."""

    # Signs access tokens (HS256). Required everywhere, never defaulted (ADR 0009).
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_ttl_minutes: int = Field(default=15, ge=1)
    refresh_token_ttl_days: int = Field(default=30, ge=1)


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()  # type: ignore[call-arg]  # required fields come from the environment


@lru_cache
def get_settings() -> Settings:
    """The settings, read once. Fails with a clear error if a required variable is missing."""
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
