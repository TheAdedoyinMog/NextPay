"""Typed application settings, read from environment variables (ADR 0007).

Every variable is prefixed ``NEXTPAY_``. For local development they can also come from
``.env`` at the repository root, wherever the process starts; see ``.env.example``.
Real environment variables win over the file. Deployments set variables and have no file.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PREFIX = "NEXTPAY_"

# backend/app/core/config.py -> the repository root. A missing file is simply skipped.
ENV_FILE: Path | None = Path(__file__).resolve().parents[3] / ".env"


class SettingsError(RuntimeError):
    """Required settings are missing or invalid. The message says which and how to fix it."""


class DatabaseSettings(BaseSettings):
    """What anything touching the database needs, migrations included: no secrets."""

    model_config = SettingsConfigDict(env_prefix=_ENV_PREFIX, extra="ignore")

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
    # The audience Apple's identity tokens must carry: the iOS app's bundle ID (ADR 0019).
    apple_bundle_id: str = Field(default="com.theadedoyinmog.nextpay", min_length=1)


def _load[S: DatabaseSettings](settings_class: type[S]) -> S:
    try:
        return settings_class(_env_file=ENV_FILE)  # type: ignore[call-arg]
    except ValidationError as error:
        raise SettingsError(_explain(error)) from None


def _explain(error: ValidationError) -> str:
    # Names and reasons only: a rejected value may be a secret, so it is never echoed.
    problems = [
        f"  {_ENV_PREFIX}{'.'.join(str(part) for part in e['loc']).upper()}: {e['msg']}"
        for e in error.errors()
    ]
    return "\n".join(
        [
            "NextPay settings are missing or invalid:",
            *problems,
            f"Set them as environment variables, or in {ENV_FILE or '.env'}.",
            "For local development, copy .env.example to .env at the repository root",
            "(PowerShell: Copy-Item .env.example .env).",
        ]
    )


@lru_cache
def get_database_settings() -> DatabaseSettings:
    """The database settings, read once. Raises ``SettingsError`` if any are missing."""
    return _load(DatabaseSettings)


@lru_cache
def get_settings() -> Settings:
    """The API's settings, read once. Raises ``SettingsError`` if any are missing."""
    return _load(Settings)
