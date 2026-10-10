"""In-memory fakes for unit-testing services without a database.

They implement the same Protocols the services declare, and behave like the
real repositories where it matters (a taken email raises EmailUnavailableError).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import argon2
import pytest

from app.core.errors import (
    EmailUnavailableError,
    EmergencyGoalExistsError,
    IncomeSourceInUseError,
)
from app.core.security import AccessTokenCodec, PasswordHasher
from app.models import RefreshToken, User
from app.services.auth import AuthService
from app.services.balances import BalanceSnapshotService
from app.services.bills import BillService
from app.services.debts import DebtService
from app.services.essential_expenses import EssentialExpenseService
from app.services.goals import GoalService
from app.services.income_sources import IncomeSourceService
from nextpay_engine import GoalKind

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


class FakeOwnedStore:
    """An in-memory OwnedStore: like the real one, it never shows a row to a non-owner."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Any] = {}

    def get(self, user_id: uuid.UUID, row_id: uuid.UUID) -> Any:
        row = self.rows.get(row_id)
        return row if row is not None and row.user_id == user_id else None

    def list_for(self, user_id: uuid.UUID) -> list[Any]:
        return [row for row in self.rows.values() if row.user_id == user_id]

    def add(self, row: Any) -> Any:
        self.rows[row.id] = row
        return row

    def delete(self, row: Any) -> None:
        del self.rows[row.id]


class FakeIncomeSources(FakeOwnedStore):
    """Refuses to delete a source listed in ``with_paychecks``, as the database would."""

    def __init__(self) -> None:
        super().__init__()
        self.with_paychecks: set[uuid.UUID] = set()

    def delete(self, row: Any) -> None:
        if row.id in self.with_paychecks:
            raise IncomeSourceInUseError()
        super().delete(row)


class FakeGoals(FakeOwnedStore):
    """Enforces one emergency goal per user, as the database's unique index does."""

    def add(self, row: Any) -> Any:
        self._check_emergency({**self.rows, row.id: row})
        return super().add(row)

    def save(self) -> None:
        self._check_emergency(self.rows)

    @staticmethod
    def _check_emergency(rows: dict[uuid.UUID, Any]) -> None:
        owners = [row.user_id for row in rows.values() if row.kind is GoalKind.EMERGENCY]
        if len(set(owners)) != len(owners):
            raise EmergencyGoalExistsError()


class FakeBalanceSnapshots:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    def add(self, row: Any) -> Any:
        self.rows.append(row)
        return row

    def latest(self, user_id: uuid.UUID, limit: int) -> list[Any]:
        own = [row for row in self.rows if row.user_id == user_id]
        return sorted(own, key=lambda row: row.as_of, reverse=True)[:limit]


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


@pytest.fixture
def bills() -> FakeOwnedStore:
    return FakeOwnedStore()


@pytest.fixture
def bill_service(bills: FakeOwnedStore, transaction: FakeTransaction) -> BillService:
    return BillService(bills=bills, transaction=transaction)


@pytest.fixture
def essentials() -> FakeOwnedStore:
    return FakeOwnedStore()


@pytest.fixture
def essential_service(
    essentials: FakeOwnedStore, transaction: FakeTransaction
) -> EssentialExpenseService:
    return EssentialExpenseService(essentials=essentials, transaction=transaction)


@pytest.fixture
def debts() -> FakeOwnedStore:
    return FakeOwnedStore()


@pytest.fixture
def debt_service(debts: FakeOwnedStore, transaction: FakeTransaction) -> DebtService:
    return DebtService(debts=debts, transaction=transaction)


@pytest.fixture
def income_sources() -> FakeIncomeSources:
    return FakeIncomeSources()


@pytest.fixture
def income_source_service(
    income_sources: FakeIncomeSources, transaction: FakeTransaction
) -> IncomeSourceService:
    return IncomeSourceService(income_sources=income_sources, transaction=transaction)


@pytest.fixture
def goals() -> FakeGoals:
    return FakeGoals()


@pytest.fixture
def goal_service(goals: FakeGoals, transaction: FakeTransaction) -> GoalService:
    return GoalService(goals=goals, transaction=transaction)


@pytest.fixture
def snapshots() -> FakeBalanceSnapshots:
    return FakeBalanceSnapshots()


@pytest.fixture
def balance_service(
    snapshots: FakeBalanceSnapshots, transaction: FakeTransaction, clock: FakeClock
) -> BalanceSnapshotService:
    return BalanceSnapshotService(snapshots=snapshots, transaction=transaction, clock=clock)
