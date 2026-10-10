"""In-memory fakes for unit-testing services without a database.

They implement the same Protocols the services declare, and behave like the
real repositories where it matters (a taken email raises EmailUnavailableError).
"""

import uuid
from datetime import UTC, datetime, timedelta

import argon2
import pytest

from app.core.errors import EmailUnavailableError
from app.core.security import AccessTokenCodec, PasswordHasher
from app.models import RefreshToken, User
from app.services.auth import AuthService

SECRET = "unit-test-secret-" + "x" * 32
START = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class FakeUsers:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, User] = {}

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.by_id.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return next((user for user in self.by_id.values() if user.email == email), None)

    def add(self, user: User) -> User:
        if self.get_by_email(user.email) is not None:
            raise EmailUnavailableError()
        user.id = user.id or uuid.uuid4()
        self.by_id[user.id] = user
        return user


class FakeRefreshTokens:
    def __init__(self) -> None:
        self.all: list[RefreshToken] = []

    def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        return next((t for t in self.all if t.token_hash == token_hash), None)

    def add(self, token: RefreshToken) -> RefreshToken:
        self.all.append(token)
        return token

    def revoke_family(self, user_id: uuid.UUID, family_id: uuid.UUID, at: datetime) -> int:
        live = [
            t
            for t in self.all
            if t.user_id == user_id and t.family_id == family_id and t.revoked_at is None
        ]
        for token in live:
            token.revoked_at = at
        return len(live)


class FakeTransaction:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def cheap_hasher() -> PasswordHasher:
    """Argon2id with minimal cost: correct, but fast enough for unit tests."""
    return PasswordHasher(argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def users() -> FakeUsers:
    return FakeUsers()


@pytest.fixture
def refresh_tokens() -> FakeRefreshTokens:
    return FakeRefreshTokens()


@pytest.fixture
def transaction() -> FakeTransaction:
    return FakeTransaction()


@pytest.fixture
def hasher() -> PasswordHasher:
    return cheap_hasher()


@pytest.fixture
def codec() -> AccessTokenCodec:
    return AccessTokenCodec(SECRET, timedelta(minutes=15))


@pytest.fixture
def service(
    users: FakeUsers,
    refresh_tokens: FakeRefreshTokens,
    transaction: FakeTransaction,
    hasher: PasswordHasher,
    codec: AccessTokenCodec,
    clock: FakeClock,
) -> AuthService:
    return AuthService(
        users=users,
        refresh_tokens=refresh_tokens,
        transaction=transaction,
        hasher=hasher,
        access_tokens=codec,
        refresh_token_ttl=timedelta(days=30),
        clock=clock,
    )
