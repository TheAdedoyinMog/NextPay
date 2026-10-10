"""Alembic environment: migrates the database named by the settings.

It reads only the database settings, so migrating never needs the API's
secrets. A caller may set ``sqlalchemy.url`` on the Alembic config instead (the tests
do, to migrate a scratch database); that takes precedence.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401  # registers every table on Base.metadata
from app.core.config import get_database_settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    return url or str(get_database_settings().database_url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (``alembic upgrade head --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
