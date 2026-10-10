"""BillService rules, with in-memory fakes (see conftest.py): no database needed."""

import uuid
from dataclasses import replace
from datetime import date
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import nextpay_engine as engine
from app.core.errors import InvalidInputError, NotFoundError
from app.services.bills import BillInput, BillService
from app.services.engine_mapping import to_engine_bill

ADA = uuid.uuid4()
BOB = uuid.uuid4()
RENT = BillInput(
    name="Rent",
    amount_cents=80_000,
    priority=1,
    first_due_date=date(2026, 10, 20),
    repeat_every_months=1,
)

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


# --- create --------------------------------------------------------------------


def test_create_stores_the_bill_for_its_user(
    bill_service: BillService, bills: Fake, transaction: Fake
) -> None:
    bill = bill_service.create(ADA, RENT)

    assert bills.rows == {bill.id: bill}
    assert bill.user_id == ADA
    assert (bill.name, bill.amount_cents, bill.priority) == ("Rent", 80_000, 1)
    assert (bill.first_due_date, bill.repeat_every_months) == (date(2026, 10, 20), 1)
    assert transaction.commits == 1


def test_a_one_time_bill_has_no_repeat(bill_service: BillService) -> None:
    bill = bill_service.create(ADA, replace(RENT, repeat_every_months=None))
    assert to_engine_bill(bill).recurrence == engine.OneTime(date(2026, 10, 20))


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"name": "   "},
        {"amount_cents": 0},
        {"amount_cents": -1},
        {"amount_cents": True},  # a bool is not an amount
        {"priority": 0},
        {"priority": True},
        {"repeat_every_months": 0},
        {"repeat_every_months": -3},
    ],
)
def test_create_rejects_what_the_engine_would_reject(
    bill_service: BillService, bills: Fake, transaction: Fake, change: dict[str, Any]
) -> None:
    with pytest.raises(InvalidInputError):
        bill_service.create(ADA, replace(RENT, **change))
    assert bills.rows == {}
    assert transaction.commits == 0


@given(
    name=st.text(max_size=20),
    amount_cents=st.integers(-10, 10**12),
    priority=st.integers(-2, 50),
    first_due_date=st.dates(),
    repeat_every_months=st.none() | st.integers(-2, 240),
)
# The fakes only accumulate rows between examples, which this test never reads.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_whatever_the_service_accepts_the_engine_accepts(
    bill_service: BillService,
    name: str,
    amount_cents: int,
    priority: int,
    first_due_date: date,
    repeat_every_months: int | None,
) -> None:
    data = BillInput(name, amount_cents, priority, first_due_date, repeat_every_months)
    try:
        bill = bill_service.create(ADA, data)
    except InvalidInputError:
        return
    planned = to_engine_bill(bill)  # must not raise
    assert planned.amount == engine.Money(amount_cents)
    assert planned.priority == priority


# --- list and get --------------------------------------------------------------


def test_list_shows_only_the_users_own_bills(bill_service: BillService) -> None:
    rent = bill_service.create(ADA, RENT)
    bill_service.create(BOB, replace(RENT, name="Bob's rent"))
    assert list(bill_service.list_for(ADA)) == [rent]
    assert list(bill_service.list_for(uuid.uuid4())) == []


def test_get_returns_the_users_own_bill(bill_service: BillService) -> None:
    rent = bill_service.create(ADA, RENT)
    assert bill_service.get(ADA, rent.id) is rent


def test_get_treats_another_users_bill_as_missing(bill_service: BillService) -> None:
    rent = bill_service.create(ADA, RENT)
    with pytest.raises(NotFoundError):
        bill_service.get(BOB, rent.id)
    with pytest.raises(NotFoundError):
        bill_service.get(ADA, uuid.uuid4())


# --- update --------------------------------------------------------------------


def test_update_replaces_every_field(bill_service: BillService, transaction: Fake) -> None:
    rent = bill_service.create(ADA, RENT)
    new = BillInput("Car insurance", 45_000, 2, date(2027, 1, 15), None)

    updated = bill_service.update(ADA, rent.id, new)

    assert updated is rent
    assert (rent.name, rent.amount_cents, rent.priority) == ("Car insurance", 45_000, 2)
    assert (rent.first_due_date, rent.repeat_every_months) == (date(2027, 1, 15), None)
    assert rent.user_id == ADA
    assert transaction.commits == 2


def test_a_rejected_update_leaves_the_bill_untouched(
    bill_service: BillService, transaction: Fake
) -> None:
    rent = bill_service.create(ADA, RENT)
    with pytest.raises(InvalidInputError):
        bill_service.update(ADA, rent.id, replace(RENT, name="Changed", amount_cents=0))
    assert (rent.name, rent.amount_cents) == ("Rent", 80_000)
    assert transaction.commits == 1


def test_update_treats_another_users_bill_as_missing(
    bill_service: BillService, transaction: Fake
) -> None:
    rent = bill_service.create(ADA, RENT)
    with pytest.raises(NotFoundError):
        bill_service.update(BOB, rent.id, replace(RENT, name="Mine now"))
    assert rent.name == "Rent" and rent.user_id == ADA
    assert transaction.commits == 1


# --- delete --------------------------------------------------------------------


def test_delete_removes_the_bill(bill_service: BillService, bills: Fake, transaction: Fake) -> None:
    rent = bill_service.create(ADA, RENT)
    bill_service.delete(ADA, rent.id)
    assert bills.rows == {}
    assert transaction.commits == 2


def test_delete_treats_another_users_bill_as_missing(
    bill_service: BillService, bills: Fake, transaction: Fake
) -> None:
    rent = bill_service.create(ADA, RENT)
    with pytest.raises(NotFoundError):
        bill_service.delete(BOB, rent.id)
    with pytest.raises(NotFoundError):
        bill_service.delete(ADA, uuid.uuid4())
    assert bills.rows == {rent.id: rent}
    assert transaction.commits == 1
