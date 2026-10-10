"""EssentialExpenseService rules, with in-memory fakes (see conftest.py)."""

import uuid
from dataclasses import replace
from typing import Any

import pytest

from app.core.errors import InvalidInputError, NotFoundError
from app.services.essential_expenses import EssentialExpenseInput, EssentialExpenseService

ADA = uuid.uuid4()
BOB = uuid.uuid4()
GROCERIES = EssentialExpenseInput(name="Groceries", amount_per_period_cents=20_000)

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


def test_create_stores_the_expense_for_its_user(
    essential_service: EssentialExpenseService, essentials: Fake, transaction: Fake
) -> None:
    groceries = essential_service.create(ADA, GROCERIES)

    assert essentials.rows == {groceries.id: groceries}
    assert (groceries.user_id, groceries.name) == (ADA, "Groceries")
    assert groceries.amount_per_period_cents == 20_000
    assert transaction.commits == 1


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"name": "  "},
        {"amount_per_period_cents": 0},
        {"amount_per_period_cents": -5},
        {"amount_per_period_cents": True},
    ],
)
def test_create_rejects_what_the_engine_would_reject(
    essential_service: EssentialExpenseService,
    essentials: Fake,
    transaction: Fake,
    change: dict[str, Any],
) -> None:
    with pytest.raises(InvalidInputError):
        essential_service.create(ADA, replace(GROCERIES, **change))
    assert essentials.rows == {}
    assert transaction.commits == 0


def test_list_and_get_show_only_the_users_own(essential_service: EssentialExpenseService) -> None:
    groceries = essential_service.create(ADA, GROCERIES)
    essential_service.create(BOB, replace(GROCERIES, name="Bob's gas"))

    assert list(essential_service.list_for(ADA)) == [groceries]
    assert essential_service.get(ADA, groceries.id) is groceries
    with pytest.raises(NotFoundError):
        essential_service.get(BOB, groceries.id)
    with pytest.raises(NotFoundError):
        essential_service.get(ADA, uuid.uuid4())


def test_update_replaces_every_field(
    essential_service: EssentialExpenseService, transaction: Fake
) -> None:
    groceries = essential_service.create(ADA, GROCERIES)
    updated = essential_service.update(ADA, groceries.id, EssentialExpenseInput("Gas", 6_000))
    assert updated is groceries
    assert (groceries.name, groceries.amount_per_period_cents) == ("Gas", 6_000)
    assert transaction.commits == 2


def test_a_rejected_update_leaves_the_expense_untouched(
    essential_service: EssentialExpenseService, transaction: Fake
) -> None:
    groceries = essential_service.create(ADA, GROCERIES)
    with pytest.raises(InvalidInputError):
        essential_service.update(ADA, groceries.id, EssentialExpenseInput("Changed", 0))
    assert (groceries.name, groceries.amount_per_period_cents) == ("Groceries", 20_000)
    assert transaction.commits == 1


def test_update_and_delete_treat_another_users_expense_as_missing(
    essential_service: EssentialExpenseService, essentials: Fake, transaction: Fake
) -> None:
    groceries = essential_service.create(ADA, GROCERIES)
    with pytest.raises(NotFoundError):
        essential_service.update(BOB, groceries.id, EssentialExpenseInput("Mine now", 1))
    with pytest.raises(NotFoundError):
        essential_service.delete(BOB, groceries.id)
    assert essentials.rows == {groceries.id: groceries}
    assert groceries.name == "Groceries"
    assert transaction.commits == 1


def test_delete_removes_the_expense(
    essential_service: EssentialExpenseService, essentials: Fake, transaction: Fake
) -> None:
    groceries = essential_service.create(ADA, GROCERIES)
    essential_service.delete(ADA, groceries.id)
    assert essentials.rows == {}
    assert transaction.commits == 2
