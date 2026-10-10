"""BalanceSnapshotService rules, with in-memory fakes (see conftest.py)."""

import uuid
from datetime import timedelta
from typing import Any

import pytest

from app.core.errors import InvalidInputError
from app.services.balances import BalanceSnapshotService

ADA = uuid.uuid4()
BOB = uuid.uuid4()

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


def test_create_records_the_balance_as_of_now(
    balance_service: BalanceSnapshotService, snapshots: Fake, transaction: Fake, clock: Fake
) -> None:
    snapshot = balance_service.create(ADA, 123_456)

    assert snapshots.rows == [snapshot]
    assert (snapshot.user_id, snapshot.amount_cents) == (ADA, 123_456)
    assert snapshot.as_of == clock.now
    assert transaction.commits == 1


@pytest.mark.parametrize("amount_cents", [0, -25_000])
def test_zero_and_overdrawn_balances_are_valid(
    balance_service: BalanceSnapshotService, amount_cents: int
) -> None:
    assert balance_service.create(ADA, amount_cents).amount_cents == amount_cents


@pytest.mark.parametrize("amount_cents", [True, 12.5, "100", None])
def test_create_rejects_what_is_not_whole_cents(
    balance_service: BalanceSnapshotService, snapshots: Fake, transaction: Fake, amount_cents: Any
) -> None:
    with pytest.raises(InvalidInputError):
        balance_service.create(ADA, amount_cents)
    assert snapshots.rows == []
    assert transaction.commits == 0


def test_list_is_newest_first_and_only_the_users_own(
    balance_service: BalanceSnapshotService, clock: Fake
) -> None:
    first = balance_service.create(ADA, 100)
    clock.advance(timedelta(days=1))
    balance_service.create(BOB, 999)
    clock.advance(timedelta(days=1))
    second = balance_service.create(ADA, 200)

    assert list(balance_service.list_for(ADA)) == [second, first]
    assert list(balance_service.list_for(ADA, limit=1)) == [second]
    assert list(balance_service.list_for(uuid.uuid4())) == []


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_list_rejects_a_limit_out_of_range(
    balance_service: BalanceSnapshotService, limit: int
) -> None:
    with pytest.raises(InvalidInputError, match="between 1 and 100"):
        balance_service.list_for(ADA, limit=limit)


def test_the_largest_page_is_allowed(balance_service: BalanceSnapshotService) -> None:
    assert list(balance_service.list_for(ADA, limit=100)) == []
