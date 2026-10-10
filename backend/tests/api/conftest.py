"""An API client wired to the rollback test database, a cheap hasher, and a fake clock.

Also ``RESOURCES``: every user-owned resource, for the tests that must hold for
all of them (test_isolation.py, test_resource_contract.py). A new resource joins
those tests by adding one entry.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

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


@dataclass(frozen=True)
class Resource:
    """One user-owned resource, as the tests that run for every resource need it."""

    path: str
    body: dict[str, Any]  # a valid body for POST
    # A different valid body, for PUT. None for an append-only resource, which has
    # no GET by id, PUT, or DELETE.
    replacement: dict[str, Any] | None


RESOURCES = (
    Resource(
        "/income-sources",
        body={
            "name": "Day job",
            "expected_amount_cents": 150_000,
            "schedule": {"type": "biweekly", "anchor_date": "2026-10-02"},
        },
        replacement={
            "name": "Taken over",
            "expected_amount_cents": 1,
            "schedule": {"type": "monthly", "day_of_month": 15},
        },
    ),
    Resource(
        "/bills",
        body={
            "name": "Rent",
            "amount_cents": 80_000,
            "priority": 1,
            "first_due_date": "2026-10-20",
            "repeat_every_months": 1,
        },
        replacement={
            "name": "Taken over",
            "amount_cents": 1,
            "priority": 9,
            "first_due_date": "2030-01-01",
            "repeat_every_months": None,
        },
    ),
    Resource(
        "/essential-expenses",
        body={"name": "Groceries", "amount_per_period_cents": 20_000},
        replacement={"name": "Taken over", "amount_per_period_cents": 1},
    ),
    Resource(
        "/debts",
        body={
            "name": "Car loan",
            "balance_cents": 900_000,
            "apr_bps": 699,
            "minimum_payment_cents": 15_000,
            "due_day": 20,
        },
        replacement={
            "name": "Taken over",
            "balance_cents": 0,
            "apr_bps": 0,
            "minimum_payment_cents": 0,
            "due_day": 1,
        },
    ),
    Resource(
        "/goals",
        body={
            "name": "Camera",
            "kind": "purchase",
            "target_cents": 200_000,
            "current_cents": 0,
            "priority": 2,
            "deadline": "2027-12-01",
        },
        replacement={
            "name": "Taken over",
            "kind": "savings",
            "target_cents": 1,
            "current_cents": 1,
            "priority": 9,
            "deadline": None,
        },
    ),
    Resource("/balance-snapshots", body={"amount_cents": 123_456}, replacement=None),
)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """A test taking ``resource`` runs once per resource; one taking ``item_resource``
    runs once per resource that has GET by id, PUT, and DELETE."""
    if "resource" in metafunc.fixturenames:
        metafunc.parametrize("resource", RESOURCES, ids=lambda r: r.path)
    if "item_resource" in metafunc.fixturenames:
        with_items = [r for r in RESOURCES if r.replacement is not None]
        metafunc.parametrize("item_resource", with_items, ids=lambda r: r.path)


@pytest.fixture
def ada(sign_up: Callable[[str], dict[str, str]]) -> dict[str, str]:
    return sign_up("ada@example.com")


@pytest.fixture
def bob(sign_up: Callable[[str], dict[str, str]]) -> dict[str, str]:
    return sign_up("bob@example.com")


@pytest.fixture
def sign_up(client: TestClient) -> Callable[[str], dict[str, str]]:
    """Register an account by email; returns the headers that sign its requests."""

    def sign_up_as(email: str) -> dict[str, str]:
        response = client.post(
            "/auth/register", json={"email": email, "password": "correct horse battery"}
        )
        assert response.status_code == 201, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return sign_up_as


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
