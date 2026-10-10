"""An API client wired to the rollback test database, a cheap hasher, and a fake clock."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import argon2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import URL
from sqlalchemy.orm import Session

from app.api.deps import get_clock, get_password_hasher
from app.core.config import Settings, get_settings
from app.core.security import PasswordHasher
from app.db.session import get_session
from app.main import app

API_SECRET = "api-test-secret-" + "x" * 32


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(db_session: Session, test_database_url: URL, clock: FakeClock) -> Iterator[TestClient]:
    def session_per_request() -> Iterator[Session]:
        # Like the real get_session closing its session: whatever the service did
        # not commit is discarded when the request ends.
        try:
            yield db_session
        finally:
            db_session.rollback()

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url=test_database_url.render_as_string(hide_password=False),
        jwt_secret=API_SECRET,
    )
    hasher = PasswordHasher(argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))
    app.dependency_overrides.update(
        {
            get_session: session_per_request,
            get_settings: lambda: settings,
            get_password_hasher: lambda: hasher,
            get_clock: lambda: clock,
        }
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
