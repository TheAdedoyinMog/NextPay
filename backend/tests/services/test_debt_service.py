"""DebtService rules, with in-memory fakes (see conftest.py)."""

import uuid
from dataclasses import replace
from typing import Any

import pytest

from app.core.errors import InvalidInputError, NotFoundError
from app.services.debts import DebtInput, DebtService

ADA = uuid.uuid4()
BOB = uuid.uuid4()
CAR_LOAN = DebtInput(
    name="Car loan", balance_cents=900_000, apr_bps=699, minimum_payment_cents=15_000, due_day=20
)

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


def test_create_stores_the_debt_for_its_user(
    debt_service: DebtService, debts: Fake, transaction: Fake
) -> None:
    loan = debt_service.create(ADA, CAR_LOAN)

    assert debts.rows == {loan.id: loan}
    assert (loan.user_id, loan.name) == (ADA, "Car loan")
    assert (loan.balance_cents, loan.apr_bps) == (900_000, 699)
    assert (loan.minimum_payment_cents, loan.due_day) == (15_000, 20)
    assert transaction.commits == 1


def test_a_paid_off_interest_free_debt_is_valid(debt_service: DebtService) -> None:
    paid = replace(CAR_LOAN, balance_cents=0, apr_bps=0, minimum_payment_cents=0, due_day=31)
    assert debt_service.create(ADA, paid).balance_cents == 0


@pytest.mark.parametrize(
    "change",
    [
        {"name": " "},
        {"balance_cents": -1},
        {"balance_cents": True},
        {"apr_bps": -1},
        {"apr_bps": True},
        {"minimum_payment_cents": -1},
        {"due_day": 0},
        {"due_day": 32},
        {"due_day": True},
    ],
)
def test_create_rejects_what_the_engine_would_reject(
    debt_service: DebtService, debts: Fake, transaction: Fake, change: dict[str, Any]
) -> None:
    with pytest.raises(InvalidInputError):
        debt_service.create(ADA, replace(CAR_LOAN, **change))
    assert debts.rows == {}
    assert transaction.commits == 0


def test_list_and_get_show_only_the_users_own(debt_service: DebtService) -> None:
    loan = debt_service.create(ADA, CAR_LOAN)
    debt_service.create(BOB, replace(CAR_LOAN, name="Bob's card"))

    assert list(debt_service.list_for(ADA)) == [loan]
    assert debt_service.get(ADA, loan.id) is loan
    with pytest.raises(NotFoundError):
        debt_service.get(BOB, loan.id)
    with pytest.raises(NotFoundError):
        debt_service.get(ADA, uuid.uuid4())


def test_update_replaces_every_field(debt_service: DebtService, transaction: Fake) -> None:
    loan = debt_service.create(ADA, CAR_LOAN)
    updated = debt_service.update(ADA, loan.id, DebtInput("Visa", 120_000, 2499, 3_500, 5))
    assert updated is loan
    assert (loan.name, loan.balance_cents, loan.apr_bps) == ("Visa", 120_000, 2499)
    assert (loan.minimum_payment_cents, loan.due_day) == (3_500, 5)
    assert transaction.commits == 2


def test_a_rejected_update_leaves_the_debt_untouched(
    debt_service: DebtService, transaction: Fake
) -> None:
    loan = debt_service.create(ADA, CAR_LOAN)
    with pytest.raises(InvalidInputError):
        debt_service.update(ADA, loan.id, replace(CAR_LOAN, name="Changed", due_day=40))
    assert (loan.name, loan.due_day) == ("Car loan", 20)
    assert transaction.commits == 1


def test_update_and_delete_treat_another_users_debt_as_missing(
    debt_service: DebtService, debts: Fake, transaction: Fake
) -> None:
    loan = debt_service.create(ADA, CAR_LOAN)
    with pytest.raises(NotFoundError):
        debt_service.update(BOB, loan.id, replace(CAR_LOAN, name="Mine now"))
    with pytest.raises(NotFoundError):
        debt_service.delete(BOB, loan.id)
    assert debts.rows == {loan.id: loan}
    assert loan.name == "Car loan"
    assert transaction.commits == 1


def test_delete_removes_the_debt(debt_service: DebtService, debts: Fake, transaction: Fake) -> None:
    loan = debt_service.create(ADA, CAR_LOAN)
    debt_service.delete(ADA, loan.id)
    assert debts.rows == {}
    assert transaction.commits == 2
