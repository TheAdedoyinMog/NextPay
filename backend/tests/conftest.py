"""Fixtures for tests that need a real PostgreSQL, and Apple's keys mocked for Sign in
with Apple.

The database fixtures run against ``NEXTPAY_TEST_DATABASE_URL`` (see .env.example) and skip when
it is unset; when it is set but the server is unreachable, they fail. The
database it names is dropped and recreated, so never point it at real data.
"""

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import URL, Connection, Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from app.core.apple import APPLE_ISSUER, hash_nonce
from app.core.errors import AppleTokenSignatureError, AppleUnavailableError

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture(scope="session")
def test_database_url() -> URL:
    url = os.environ.get("NEXTPAY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NEXTPAY_TEST_DATABASE_URL is not set; see .env.example")
    return make_url(url)


def recreate_database(url: URL) -> None:
    """Drop ``url``'s database if it exists and create it empty."""
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


def drop_database(url: URL) -> None:
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
    admin.dispose()


def alembic_config(url: URL) -> Config:
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    config.attributes["configure_logger"] = False  # leave pytest's logging alone
    return config


@pytest.fixture(scope="session")
def alembic_config_for() -> Callable[[URL], Config]:
    return alembic_config


@pytest.fixture
def scratch_url(test_database_url: URL) -> Iterator[URL]:
    """A second, empty database next to the test database, dropped afterwards."""
    url = test_database_url.set(database=f"{test_database_url.database}_scratch")
    recreate_database(url)
    yield url
    drop_database(url)


@pytest.fixture(scope="session")
def migrated_engine(test_database_url: URL) -> Iterator[Engine]:
    """The test database, freshly migrated to head."""
    recreate_database(test_database_url)
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_connection(migrated_engine: Engine) -> Iterator[Connection]:
    """A connection inside a transaction that is rolled back after the test."""
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def db_session(db_connection: Connection) -> Iterator[Session]:
    """A session whose commits and rollbacks stay inside the test's transaction."""
    with Session(bind=db_connection, join_transaction_mode="create_savepoint") as session:
        yield session


# --- Sign in with Apple (ADR 0019): Apple's keys, mocked ---------------------------------

APPLE_BUNDLE_ID = "com.theadedoyinmog.nextpay"  # the Settings default
APPLE_KID = "test-key-1"
# Both unit and API tests run their fake clocks from this instant.
APPLE_NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
APPLE_NONCE = "a" * 64  # the raw nonce the app sends us; Apple is given its hash


class FakeAppleKeys:
    """Stands in for Apple's published keys: one RSA key under ``APPLE_KID``."""

    def __init__(self, public_key: Any) -> None:
        self.keys: dict[str, Any] = {APPLE_KID: public_key}
        self.unavailable = False

    def signing_key(self, kid: str) -> Any:
        if self.unavailable:
            raise AppleUnavailableError()
        if kid not in self.keys:
            raise AppleTokenSignatureError()
        return self.keys[kid]


@pytest.fixture(scope="session")
def apple_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def other_private_key() -> rsa.RSAPrivateKey:
    """A key Apple never published: what a forger would sign with."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def apple_keys(apple_private_key: rsa.RSAPrivateKey) -> FakeAppleKeys:
    return FakeAppleKeys(apple_private_key.public_key())


@pytest.fixture
def apple_token(apple_private_key: rsa.RSAPrivateKey) -> Callable[..., str]:
    """Makes identity tokens the way Apple does. Keyword arguments replace claims; a claim
    set to ``None`` is left out. ``key``, ``kid`` and ``algorithm`` change the signing."""

    def make(
        *,
        key: Any = None,
        kid: str = APPLE_KID,
        algorithm: str = "RS256",
        **overrides: Any,
    ) -> str:
        claims: dict[str, Any] = {
            "iss": APPLE_ISSUER,
            "aud": APPLE_BUNDLE_ID,
            "iat": int(APPLE_NOW.timestamp()),
            "exp": int((APPLE_NOW + timedelta(minutes=10)).timestamp()),
            "sub": "001234.abcdef0123456789.1234",
            "nonce": hash_nonce(APPLE_NONCE),
            "email": "x7k2p9@privaterelay.appleid.com",
            "email_verified": "true",
            "is_private_email": "true",
            "auth_time": int(APPLE_NOW.timestamp()),
        }
        claims.update(overrides)
        claims = {name: value for name, value in claims.items() if value is not None}
        return jwt.encode(
            claims, key or apple_private_key, algorithm=algorithm, headers={"kid": kid}
        )

    return make
