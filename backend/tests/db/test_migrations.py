"""The migrations build exactly the schema the models describe."""

from collections.abc import Callable

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import URL, Engine, create_engine, inspect, text

import app.models  # noqa: F401  # registers every table
from app.db.base import Base

type Catalog = dict[str, list[tuple[object, ...]]]

# Everything PostgreSQL knows about the schema, as comparable rows. Alembic's
# autogenerate does not compare CHECK constraints, partial-index predicates, or
# ON DELETE actions, so the catalog comparison covers what it misses.
_CATALOG_QUERIES = {
    "columns": """
        SELECT table_name, ordinal_position, column_name, data_type,
               character_maximum_length, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name <> 'alembic_version'
        ORDER BY table_name, ordinal_position
    """,
    "constraints": """
        SELECT conrelid::regclass::text AS table_name, conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE connamespace = 'public'::regnamespace
          AND conrelid::regclass::text <> 'alembic_version'
        ORDER BY table_name, conname
    """,
    "indexes": """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename <> 'alembic_version'
        ORDER BY tablename, indexname
    """,
}


def catalog(engine: Engine) -> Catalog:
    with engine.connect() as connection:
        return {
            name: [tuple(row) for row in connection.execute(text(query))]
            for name, query in _CATALOG_QUERIES.items()
        }


def test_migrations_create_every_model_table(migrated_engine: Engine) -> None:
    tables = set(inspect(migrated_engine).get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)


def test_autogenerate_finds_no_difference_from_the_models(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


def test_catalog_matches_a_schema_built_from_the_models(
    migrated_engine: Engine, scratch_url: URL
) -> None:
    from_models = create_engine(scratch_url)
    Base.metadata.create_all(from_models)
    try:
        expected = catalog(from_models)
    finally:
        from_models.dispose()
    actual = catalog(migrated_engine)
    for part in _CATALOG_QUERIES:
        assert actual[part] == expected[part], part


def test_downgrade_removes_everything_and_upgrade_restores_it(
    migrated_engine: Engine, scratch_url: URL, alembic_config_for: Callable[[URL], Config]
) -> None:
    config = alembic_config_for(scratch_url)
    engine = create_engine(scratch_url)
    try:
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
        assert catalog(engine) == catalog(migrated_engine)
    finally:
        engine.dispose()
