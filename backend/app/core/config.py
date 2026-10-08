"""Typed application settings, read from environment variables (ADR 0007).

Every variable is prefixed ``NEXTPAY_``. A ``.env`` file in the working directory
is read too, for local development; see ``.env.example`` at the repository root.
"""

from functools import lru_cache

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEXTPAY_", env_file=".env", extra="ignore")

    # SQLAlchemy URL with the psycopg 3 driver, e.g.
    # postgresql+psycopg://nextpay:nextpay@localhost:5432/nextpay
    database_url: PostgresDsn
    # Log every SQL statement; for debugging only.
    sql_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    """The settings, read once. Fails with a clear error if a required variable is missing."""
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
