"""Fixtures for tests that need a real PostgreSQL.

They run against ``NEXTPAY_TEST_DATABASE_URL`` (see .env.example) and skip when
it is unset; when it is set but the server is unreachable, they fail. The
database it names is dropped and recreated, so never point it at real data.
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Connection, Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

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
