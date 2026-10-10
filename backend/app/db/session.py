"""Database engine and sessions.

The engine is created on first use, not at import, so importing the app never
needs a database or settings.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_database_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_database_settings()
    return create_engine(str(settings.database_url), echo=settings.sql_echo, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """One session per request, for FastAPI ``Depends``. The caller commits."""
    with get_sessionmaker()() as session:
        yield session
