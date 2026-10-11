"""Recording payments: paying a bill or debt draws its reserve down (ADR 0003, ADR 0011).

A payment is the money leaving, so what was set aside for it is no longer held.
Paying more than was reserved empties the reserve and stops there. A debt
payment also lowers what is owed. Balances are not touched: a balance is what
the user says they have, when they say it.

Known limitation (ADR 0011): the planner does not know which occurrence of a
bill is paid. A bill paid before the last paycheck ahead of its due date is
reserved for again by that paycheck's plan; the extra then covers the next
occurrence, so nothing is underfunded, but that plan's Safe to Spend is lower
than it needs to be.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.core.clock import Clock, local_date
from app.core.errors import InvalidInputError, NotFoundError
from app.models import Bill, BillPayment, Debt, DebtPayment, User
from app.services.engine_mapping import to_engine_bill
from app.services.protocols import Transaction, UserLock
from app.services.reserves import ReserveStore, draw_down_reserve
from nextpay_engine import ReserveKind


class BillLookup(Protocol):
    def get(self, user_id: uuid.UUID, row_id: uuid.UUID) -> Bill | None: ...


class BillPaymentStore(Protocol):
    def add(self, row: BillPayment) -> BillPayment: ...
    def list_for_bill(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> Sequence[BillPayment]: ...


@dataclass(frozen=True, slots=True)
class BillPaymentInput:
    """A payment toward a bill. Everything left out takes the obvious value, so
    "mark as paid" needs no details at all."""

    # None: the bill's full amount.
    amount_cents: int | None = None
    # None: today, in the user's time zone.
    paid_on: date | None = None
    # Which occurrence this pays. None: the bill's due date closest to ``paid_on``.
    due_date: date | None = None


class DebtLookup(Protocol):
    def get(self, user_id: uuid.UUID, row_id: uuid.UUID) -> Debt | None: ...


class DebtPaymentStore(Protocol):
    def add(self, row: DebtPayment) -> DebtPayment: ...
    def list_for_debt(self, user_id: uuid.UUID, debt_id: uuid.UUID) -> Sequence[DebtPayment]: ...


@dataclass(frozen=True, slots=True)
class DebtPaymentInput:
    """A payment toward a debt. Left out, each field takes the obvious value."""

    # None: the minimum payment, or the whole balance if that is less.
    amount_cents: int | None = None
    # None: today, in the user's time zone.
    paid_on: date | None = None


def closest_due_date(bill: Bill, day: date) -> date:
    """The due date of ``bill`` nearest to ``day``; the earlier one when two are as near.

    People pay a few days early or a few days late, so the nearest occurrence is
    the one a payment is for.
    """
    recurrence = to_engine_bill(bill).recurrence
    before = recurrence.due_dates_between(date.min, day)
    after = recurrence.next_due_after(day)
    candidates = [*before[-1:], *([] if after is None else [after])]
    return min(candidates, key=lambda due: (abs((due - day).days), due))


def is_due_date(bill: Bill, day: date) -> bool:
    return to_engine_bill(bill).recurrence.due_dates_between(day, day) == (day,)


def _require_amount(amount_cents: int) -> None:
    if type(amount_cents) is not int or amount_cents <= 0:
        raise InvalidInputError("A payment must be more than $0.")


class PaymentService:
    def __init__(
        self,
        *,
        users: UserLock,
        bills: BillLookup,
        bill_payments: BillPaymentStore,
        debts: DebtLookup,
        debt_payments: DebtPaymentStore,
        reserves: ReserveStore,
        transaction: Transaction,
        clock: Clock,
    ) -> None:
        self._users = users
        self._bills = bills
        self._bill_payments = bill_payments
        self._debts = debts
        self._debt_payments = debt_payments
        self._reserves = reserves
        self._transaction = transaction
        self._clock = clock

    def pay_bill(self, user: User, bill_id: uuid.UUID, data: BillPaymentInput) -> BillPayment:
        """Record a payment toward a bill and draw its reserve down by the amount.

        Raises ``NotFoundError``, or ``InvalidInputError`` for an amount that is not
        positive or a ``due_date`` that is not one of the bill's due dates.
        """
        self._users.lock(user.id)
        bill = self._bill(user.id, bill_id)
        amount_cents = bill.amount_cents if data.amount_cents is None else data.amount_cents
        _require_amount(amount_cents)
        paid_on = data.paid_on or local_date(self._clock(), user.timezone)
        if data.due_date is None:
            due_date = closest_due_date(bill, paid_on)
        elif is_due_date(bill, data.due_date):
            due_date = data.due_date
        else:
            raise InvalidInputError(
                f"{data.due_date.isoformat()} is not a due date of {bill.name}."
            )

        payment = self._bill_payments.add(
            BillPayment(
                id=uuid.uuid4(),
                user_id=user.id,
                bill_id=bill.id,
                due_date=due_date,
                paid_on=paid_on,
                amount_cents=amount_cents,
            )
        )
        draw_down_reserve(self._reserves, user.id, ReserveKind.BILL, bill.id, amount_cents)
        self._transaction.commit()
        return payment

    def list_bill_payments(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> Sequence[BillPayment]:
        """A bill's payments, newest first. Raises ``NotFoundError``."""
        return self._bill_payments.list_for_bill(user_id, self._bill(user_id, bill_id).id)

    def pay_debt(self, user: User, debt_id: uuid.UUID, data: DebtPaymentInput) -> DebtPayment:
        """Record a payment toward a debt: its reserve and its balance both go down.

        Without this a debt would be funded once and never again: the planner asks
        for the minimum less what is already reserved. Paying more than is owed
        leaves the balance at $0. Raises ``NotFoundError``, or ``InvalidInputError``
        for an amount that is not positive (including the default, when nothing
        is owed).
        """
        self._users.lock(user.id)
        debt = self._debt(user.id, debt_id)
        if data.amount_cents is None:
            amount_cents = min(debt.minimum_payment_cents, debt.balance_cents)
        else:
            amount_cents = data.amount_cents
        _require_amount(amount_cents)

        payment = self._debt_payments.add(
            DebtPayment(
                id=uuid.uuid4(),
                user_id=user.id,
                debt_id=debt.id,
                paid_on=data.paid_on or local_date(self._clock(), user.timezone),
                amount_cents=amount_cents,
            )
        )
        debt.balance_cents = max(debt.balance_cents - amount_cents, 0)
        draw_down_reserve(self._reserves, user.id, ReserveKind.DEBT, debt.id, amount_cents)
        self._transaction.commit()
        return payment

    def list_debt_payments(self, user_id: uuid.UUID, debt_id: uuid.UUID) -> Sequence[DebtPayment]:
        """A debt's payments, newest first. Raises ``NotFoundError``."""
        return self._debt_payments.list_for_debt(user_id, self._debt(user_id, debt_id).id)

    def _bill(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> Bill:
        bill = self._bills.get(user_id, bill_id)
        if bill is None:
            raise NotFoundError()
        return bill

    def _debt(self, user_id: uuid.UUID, debt_id: uuid.UUID) -> Debt:
        debt = self._debts.get(user_id, debt_id)
        if debt is None:
            raise NotFoundError()
        return debt
