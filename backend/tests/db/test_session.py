"""The app's settings and session plumbing reach the database."""

from collections.abc import Iterator

import pytest
from sqlalchemy import URL, text

from app.core.config import get_database_settings
from app.db.session import get_engine, get_session, get_sessionmaker


def _clear_caches() -> None:
    for cached in (get_database_settings, get_engine, get_sessionmaker):
        cached.cache_clear()


@pytest.fixture
def app_database(
    migrated_engine: object, test_database_url: URL, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Point the app's own settings at the test database."""
    url = test_database_url.render_as_string(hide_password=False)
    monkeypatch.setenv("NEXTPAY_DATABASE_URL", url)
    monkeypatch.delenv("NEXTPAY_JWT_SECRET", raising=False)  # the database needs no secrets
    _clear_caches()
    yield
    get_engine().dispose()
    _clear_caches()


@pytest.mark.usefixtures("app_database")
def test_get_session_connects_with_the_configured_url() -> None:
    sessions = get_session()
    session = next(sessions)
    assert session.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
    sessions.close()
