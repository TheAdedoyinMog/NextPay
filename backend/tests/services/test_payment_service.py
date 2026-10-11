"""PaymentService rules, with in-memory fakes (see conftest.py).

The fake clock is at noon UTC on Wednesday, Oct 7, 2026.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.core.errors import InvalidInputError, NotFoundError
from app.models import Bill, Debt, Reserve, User
from app.services.payments import (
    BillPaymentInput,
    DebtPaymentInput,
    PaymentService,
    closest_due_date,
)
from nextpay_engine import ReserveKind

ADA = User(id=uuid.uuid4(), email="ada@example.com", timezone="UTC")
BOB = User(id=uuid.uuid4(), email="bob@example.com", timezone="UTC")

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


def add_bill(bills: Fake, user: User = ADA, **fields: Any) -> Bill:
    """$800 rent, due on the 20th of every month from Oct 20, 2026."""
    defaults: dict[str, Any] = {
        "name": "Rent",
        "amount_cents": 80_000,
        "priority": 1,
        "first_due_date": date(2026, 10, 20),
        "repeat_every_months": 1,
    }
    bill: Bill = bills.add(Bill(id=uuid.uuid4(), user_id=user.id, **{**defaults, **fields}))
    return bill


def set_aside(reserves: Fake, bill: Bill, cents: int) -> Reserve:
    reserve: Reserve = reserves.add(
        Reserve(
            id=uuid.uuid4(),
            user_id=bill.user_id,
            kind=ReserveKind.BILL,
            bill_id=bill.id,
            amount_cents=cents,
        )
    )
    return reserve


# --- paying a bill -------------------------------------------------------------


def test_marking_a_bill_paid_needs_no_details(
    payment_service: PaymentService,
    bills: Fake,
    bill_payments: Fake,
    reserves: Fake,
    user_lock: Fake,
    transaction: Fake,
) -> None:
    rent = add_bill(bills)
    reserve = set_aside(reserves, rent, 80_000)

    payment = payment_service.pay_bill(ADA, rent.id, BillPaymentInput())

    assert bill_payments.rows == {payment.id: payment}
    assert (payment.user_id, payment.bill_id) == (ADA.id, rent.id)
    # In full, today, for the occurrence nearest today.
    assert (payment.amount_cents, payment.paid_on) == (80_000, date(2026, 10, 7))
    assert payment.due_date == date(2026, 10, 20)
    assert reserve.amount_cents == 0
    assert rent.amount_cents == 80_000
    assert user_lock.locked == [ADA.id]
    assert transaction.commits == 1


@pytest.mark.parametrize(
    ("reserved", "paid", "left"),
    [
        (80_000, 80_000, 0),
        (80_000, 30_000, 50_000),  # a part payment
        (40_000, 80_000, 0),  # paid in full with only half set aside
        (95_000, 80_000, 15_000),  # more than the bill was set aside
    ],
)
def test_the_reserve_goes_down_by_what_was_paid_but_not_below_zero(
    payment_service: PaymentService,
    bills: Fake,
    reserves: Fake,
    reserved: int,
    paid: int,
    left: int,
) -> None:
    rent = add_bill(bills)
    reserve = set_aside(reserves, rent, reserved)

    payment = payment_service.pay_bill(ADA, rent.id, BillPaymentInput(amount_cents=paid))

    assert payment.amount_cents == paid
    assert reserve.amount_cents == left


def test_paying_a_bill_with_nothing_set_aside_just_records_the_payment(
    payment_service: PaymentService, bills: Fake, bill_payments: Fake, reserves: Fake
) -> None:
    rent = add_bill(bills)
    payment_service.pay_bill(ADA, rent.id, BillPaymentInput())
    assert len(bill_payments.rows) == 1
    assert reserves.rows == {}


def test_only_the_paid_bills_reserve_is_drawn_down(
    payment_service: PaymentService, bills: Fake, reserves: Fake
) -> None:
    rent, phone = add_bill(bills), add_bill(bills, name="Phone", amount_cents=6_000)
    bobs = add_bill(bills, BOB)
    untouched = [set_aside(reserves, phone, 6_000), set_aside(reserves, bobs, 80_000)]
    paid = set_aside(reserves, rent, 80_000)

    payment_service.pay_bill(ADA, rent.id, BillPaymentInput())

    assert paid.amount_cents == 0
    assert [reserve.amount_cents for reserve in untouched] == [6_000, 80_000]


def test_today_is_the_users_own_date(
    payment_service: PaymentService, bills: Fake, clock: Fake
) -> None:
    rent = add_bill(bills)
    clock.now = datetime(2026, 10, 21, 2, 0, tzinfo=UTC)  # still Oct 20 in Los Angeles
    westerner = User(id=ADA.id, email=ADA.email, timezone="America/Los_Angeles")

    assert payment_service.pay_bill(ADA, rent.id, BillPaymentInput()).paid_on == date(2026, 10, 21)
    assert payment_service.pay_bill(westerner, rent.id, BillPaymentInput()).paid_on == date(
        2026, 10, 20
    )


# --- which occurrence a payment is for -----------------------------------------


@pytest.mark.parametrize(
    ("paid_on", "due"),
    [
        (date(2026, 10, 20), date(2026, 10, 20)),  # on the day
        (date(2026, 10, 15), date(2026, 10, 20)),  # early
        (date(2026, 10, 24), date(2026, 10, 20)),  # late
        (date(2026, 11, 4), date(2026, 10, 20)),  # 15 days late, 16 days early: the earlier
        (date(2026, 11, 5), date(2026, 11, 20)),  # now closer to November's
        (date(2026, 11, 19), date(2026, 11, 20)),
        (date(2026, 9, 1), date(2026, 10, 20)),  # before the first one: there is only it
        (date(2027, 2, 27), date(2027, 2, 20)),
    ],
)
def test_a_payment_is_for_the_due_date_closest_to_the_day_it_was_paid(
    payment_service: PaymentService, bills: Fake, paid_on: date, due: date
) -> None:
    rent = add_bill(bills)
    payment = payment_service.pay_bill(ADA, rent.id, BillPaymentInput(paid_on=paid_on))
    assert (payment.paid_on, payment.due_date) == (paid_on, due)


def test_two_due_dates_equally_near_means_the_earlier_one(bills: Fake) -> None:
    due_on_the_first = add_bill(bills, first_due_date=date(2026, 10, 1), repeat_every_months=1)
    # Oct 1 and Nov 1: Oct 16 is 15 days after one and 16 before the other; with a
    # 30-day gap (Nov 1 to Dec 1), Nov 16 is exactly 15 days from both.
    assert closest_due_date(due_on_the_first, date(2026, 10, 16)) == date(2026, 10, 1)
    assert closest_due_date(due_on_the_first, date(2026, 11, 16)) == date(2026, 11, 1)
    assert closest_due_date(due_on_the_first, date(2026, 11, 17)) == date(2026, 12, 1)


@pytest.mark.parametrize("paid_on", [date(2026, 9, 1), date(2026, 12, 1), date(2027, 6, 30)])
def test_a_one_time_bill_has_only_one_due_date(
    payment_service: PaymentService, bills: Fake, paid_on: date
) -> None:
    registration = add_bill(
        bills, name="Car registration", first_due_date=date(2026, 12, 1), repeat_every_months=None
    )
    payment = payment_service.pay_bill(ADA, registration.id, BillPaymentInput(paid_on=paid_on))
    assert payment.due_date == date(2026, 12, 1)


def test_a_bill_due_on_the_31st_is_matched_to_the_months_last_day(
    payment_service: PaymentService, bills: Fake
) -> None:
    bill = add_bill(bills, first_due_date=date(2027, 1, 31))
    payment = payment_service.pay_bill(ADA, bill.id, BillPaymentInput(paid_on=date(2027, 2, 26)))
    assert payment.due_date == date(2027, 2, 28)


def test_the_occurrence_can_be_named(payment_service: PaymentService, bills: Fake) -> None:
    rent = add_bill(bills)
    # Catching up in December on the rent that was due in October.
    late = BillPaymentInput(paid_on=date(2026, 12, 2), due_date=date(2026, 10, 20))
    assert payment_service.pay_bill(ADA, rent.id, late).due_date == date(2026, 10, 20)


@pytest.mark.parametrize("due_date", [date(2026, 10, 21), date(2026, 9, 20), date(2026, 11, 1)])
def test_a_named_occurrence_must_be_one_of_the_bills_due_dates(
    payment_service: PaymentService,
    bills: Fake,
    bill_payments: Fake,
    reserves: Fake,
    transaction: Fake,
    due_date: date,
) -> None:
    rent = add_bill(bills)
    reserve = set_aside(reserves, rent, 80_000)

    with pytest.raises(InvalidInputError, match="is not a due date of Rent"):
        payment_service.pay_bill(ADA, rent.id, BillPaymentInput(due_date=due_date))

    assert bill_payments.rows == {}
    assert reserve.amount_cents == 80_000
    assert transaction.commits == 0


@pytest.mark.parametrize("amount", [0, -1, True, 800.0])
def test_a_payment_must_be_a_positive_whole_number_of_cents(
    payment_service: PaymentService, bills: Fake, bill_payments: Fake, reserves: Fake, amount: Any
) -> None:
    rent = add_bill(bills)
    reserve = set_aside(reserves, rent, 80_000)

    with pytest.raises(InvalidInputError, match="more than"):
        payment_service.pay_bill(ADA, rent.id, BillPaymentInput(amount_cents=amount))

    assert bill_payments.rows == {}
    assert reserve.amount_cents == 80_000


# --- paying a debt -------------------------------------------------------------


def add_debt(debts: Fake, user: User = ADA, **fields: Any) -> Debt:
    """A $9,000 car loan with a $150 minimum."""
    defaults: dict[str, Any] = {
        "name": "Car loan",
        "balance_cents": 900_000,
        "apr_bps": 699,
        "minimum_payment_cents": 15_000,
        "due_day": 20,
    }
    debt: Debt = debts.add(Debt(id=uuid.uuid4(), user_id=user.id, **{**defaults, **fields}))
    return debt


def set_aside_for_debt(reserves: Fake, debt: Debt, cents: int) -> Reserve:
    reserve: Reserve = reserves.add(
        Reserve(
            id=uuid.uuid4(),
            user_id=debt.user_id,
            kind=ReserveKind.DEBT,
            debt_id=debt.id,
            amount_cents=cents,
        )
    )
    return reserve


def test_recording_the_minimum_needs_no_details(
    payment_service: PaymentService,
    debts: Fake,
    debt_payments: Fake,
    reserves: Fake,
    user_lock: Fake,
    transaction: Fake,
) -> None:
    loan = add_debt(debts)
    reserve = set_aside_for_debt(reserves, loan, 15_000)

    payment = payment_service.pay_debt(ADA, loan.id, DebtPaymentInput())

    assert debt_payments.rows == {payment.id: payment}
    assert (payment.user_id, payment.debt_id) == (ADA.id, loan.id)
    assert (payment.amount_cents, payment.paid_on) == (15_000, date(2026, 10, 7))
    # Both what is owed and what was set aside for it go down.
    assert loan.balance_cents == 885_000
    assert reserve.amount_cents == 0
    assert user_lock.locked == [ADA.id]
    assert transaction.commits == 1


@pytest.mark.parametrize(
    ("reserved", "paid", "balance_left", "reserve_left"),
    [
        (15_000, 15_000, 885_000, 0),
        (15_000, 50_000, 850_000, 0),  # extra toward the principal
        (15_000, 10_000, 890_000, 5_000),  # less than the minimum
        (7_500, 15_000, 885_000, 0),  # only half was set aside
        (15_000, 950_000, 0, 0),  # more than is owed: the balance stops at $0
    ],
)
def test_the_balance_and_the_reserve_both_go_down_but_not_below_zero(
    payment_service: PaymentService,
    debts: Fake,
    reserves: Fake,
    reserved: int,
    paid: int,
    balance_left: int,
    reserve_left: int,
) -> None:
    loan = add_debt(debts)
    reserve = set_aside_for_debt(reserves, loan, reserved)

    payment_service.pay_debt(ADA, loan.id, DebtPaymentInput(amount_cents=paid))

    assert (loan.balance_cents, reserve.amount_cents) == (balance_left, reserve_left)


def test_the_last_payment_defaults_to_what_is_left(
    payment_service: PaymentService, debts: Fake
) -> None:
    loan = add_debt(debts, balance_cents=4_000)
    payment = payment_service.pay_debt(ADA, loan.id, DebtPaymentInput())
    assert (payment.amount_cents, loan.balance_cents) == (4_000, 0)


@pytest.mark.parametrize("fields", [{"balance_cents": 0}, {"minimum_payment_cents": 0}])
def test_with_nothing_owed_or_no_minimum_the_amount_must_be_given(
    payment_service: PaymentService, debts: Fake, debt_payments: Fake, fields: dict[str, int]
) -> None:
    loan = add_debt(debts, **fields)
    with pytest.raises(InvalidInputError, match="more than"):
        payment_service.pay_debt(ADA, loan.id, DebtPaymentInput())
    assert debt_payments.rows == {}

    payment_service.pay_debt(ADA, loan.id, DebtPaymentInput(amount_cents=2_500))
    assert len(debt_payments.rows) == 1


@pytest.mark.parametrize("amount", [0, -1, True])
def test_a_debt_payment_must_be_positive(
    payment_service: PaymentService,
    debts: Fake,
    debt_payments: Fake,
    reserves: Fake,
    transaction: Fake,
    amount: Any,
) -> None:
    loan = add_debt(debts)
    reserve = set_aside_for_debt(reserves, loan, 15_000)

    with pytest.raises(InvalidInputError):
        payment_service.pay_debt(ADA, loan.id, DebtPaymentInput(amount_cents=amount))

    assert debt_payments.rows == {}
    assert (loan.balance_cents, reserve.amount_cents) == (900_000, 15_000)
    assert transaction.commits == 0


def test_a_debt_payment_can_be_dated_and_only_touches_its_own_debt(
    payment_service: PaymentService, debts: Fake, reserves: Fake
) -> None:
    loan, card = add_debt(debts), add_debt(debts, name="Visa", balance_cents=120_000)
    card_reserve = set_aside_for_debt(reserves, card, 3_500)

    payment = payment_service.pay_debt(ADA, loan.id, DebtPaymentInput(paid_on=date(2026, 9, 19)))

    assert payment.paid_on == date(2026, 9, 19)
    assert (card.balance_cents, card_reserve.amount_cents) == (120_000, 3_500)


def test_debt_payments_are_listed_newest_first_for_one_debt(
    payment_service: PaymentService, debts: Fake
) -> None:
    loan, card = add_debt(debts), add_debt(debts, name="Visa")
    september = payment_service.pay_debt(ADA, loan.id, DebtPaymentInput(paid_on=date(2026, 9, 20)))
    payment_service.pay_debt(ADA, card.id, DebtPaymentInput(paid_on=date(2026, 10, 1)))
    october = payment_service.pay_debt(ADA, loan.id, DebtPaymentInput(paid_on=date(2026, 10, 20)))

    assert list(payment_service.list_debt_payments(ADA.id, loan.id)) == [october, september]


def test_another_users_debt_is_missing_for_paying_and_listing(
    payment_service: PaymentService,
    debts: Fake,
    debt_payments: Fake,
    reserves: Fake,
    transaction: Fake,
) -> None:
    loan = add_debt(debts)
    reserve = set_aside_for_debt(reserves, loan, 15_000)

    for debt_id in (loan.id, uuid.uuid4()):
        with pytest.raises(NotFoundError):
            payment_service.pay_debt(BOB, debt_id, DebtPaymentInput())
        with pytest.raises(NotFoundError):
            payment_service.list_debt_payments(BOB.id, debt_id)

    assert debt_payments.rows == {}
    assert (loan.balance_cents, reserve.amount_cents) == (900_000, 15_000)
    assert transaction.commits == 0


# --- listing, and other users' bills -------------------------------------------


def test_payments_are_listed_newest_first_for_one_bill(
    payment_service: PaymentService, bills: Fake
) -> None:
    rent, phone = add_bill(bills), add_bill(bills, name="Phone", amount_cents=6_000)
    october = payment_service.pay_bill(ADA, rent.id, BillPaymentInput(paid_on=date(2026, 10, 19)))
    payment_service.pay_bill(ADA, phone.id, BillPaymentInput(paid_on=date(2026, 10, 25)))
    november = payment_service.pay_bill(ADA, rent.id, BillPaymentInput(paid_on=date(2026, 11, 20)))

    assert list(payment_service.list_bill_payments(ADA.id, rent.id)) == [november, october]


def test_another_users_bill_is_missing_for_paying_and_listing(
    payment_service: PaymentService,
    bills: Fake,
    bill_payments: Fake,
    reserves: Fake,
    transaction: Fake,
) -> None:
    rent = add_bill(bills)
    reserve = set_aside(reserves, rent, 80_000)

    for bill_id in (rent.id, uuid.uuid4()):
        with pytest.raises(NotFoundError):
            payment_service.pay_bill(BOB, bill_id, BillPaymentInput())
        with pytest.raises(NotFoundError):
            payment_service.list_bill_payments(BOB.id, bill_id)

    assert bill_payments.rows == {}
    assert reserve.amount_cents == 80_000
    assert transaction.commits == 0
