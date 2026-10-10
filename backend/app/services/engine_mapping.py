"""Database rows to the engine's domain types.

The engine validates its types on construction, so building one is how a
service checks a row against the engine's rules (see ``validated``): the two
cannot drift apart. Plan generation (2D) feeds the engine through the same
functions.
"""

from collections.abc import Callable

import nextpay_engine as engine
from app import models
from app.core.errors import InvalidInputError
from app.models import PayFrequency


def validated[R](row: R, to_engine: Callable[[R], object]) -> R:
    """``row`` if the engine accepts it; ``InvalidInputError`` otherwise."""
    try:
        to_engine(row)
    except (TypeError, ValueError) as error:
        raise InvalidInputError() from error
    return row


def to_engine_bill(row: models.Bill) -> engine.Bill:
    recurrence: engine.BillRecurrence
    if row.repeat_every_months is None:
        recurrence = engine.OneTime(row.first_due_date)
    else:
        recurrence = engine.EveryNMonths(row.first_due_date, row.repeat_every_months)
    return engine.Bill(
        id=str(row.id),
        name=row.name,
        amount=engine.Money(row.amount_cents),
        recurrence=recurrence,
        priority=row.priority,
    )


def to_engine_essential(row: models.EssentialExpense) -> engine.EssentialExpense:
    return engine.EssentialExpense(
        id=str(row.id),
        name=row.name,
        amount_per_period=engine.Money(row.amount_per_period_cents),
    )


def to_engine_debt(row: models.Debt) -> engine.Debt:
    return engine.Debt(
        id=str(row.id),
        name=row.name,
        balance=engine.Money(row.balance_cents),
        apr_bps=row.apr_bps,
        minimum_payment=engine.Money(row.minimum_payment_cents),
        due_day=row.due_day,
    )


def to_engine_schedule(row: models.IncomeSource) -> engine.PaySchedule:
    """The schedule ``row`` stores. Raises ``ValueError`` unless the row carries
    exactly its frequency's parameters, as the table's CHECK also demands."""
    frequency = row.pay_frequency
    anchor, first, second = row.anchor_date, row.day_of_month, row.second_day_of_month
    if frequency is PayFrequency.WEEKLY and anchor and first is None and second is None:
        return engine.Weekly(anchor)
    if frequency is PayFrequency.BIWEEKLY and anchor and first is None and second is None:
        return engine.Biweekly(anchor)
    if (
        frequency is PayFrequency.SEMI_MONTHLY
        and anchor is None
        and first is not None
        and second is not None
    ):
        return engine.SemiMonthly(first, second)
    if (
        frequency is PayFrequency.MONTHLY
        and anchor is None
        and first is not None
        and second is None
    ):
        return engine.Monthly(first)
    raise ValueError(f"a {frequency} schedule was given the wrong parameters")


def to_engine_income_source(row: models.IncomeSource) -> engine.IncomeSource:
    return engine.IncomeSource(
        id=str(row.id),
        name=row.name,
        schedule=to_engine_schedule(row),
        expected_amount=engine.Money(row.expected_amount_cents),
    )


def to_engine_goal(row: models.Goal) -> engine.Goal:
    return engine.Goal(
        id=str(row.id),
        name=row.name,
        kind=row.kind,
        target=engine.Money(row.target_cents),
        current=engine.Money(row.current_cents),
        priority=row.priority,
        deadline=row.deadline,
    )


def to_engine_balance(row: models.BalanceSnapshot) -> engine.Money:
    """``FinancialState.available_balance`` as of this snapshot (signed)."""
    return engine.Money(row.amount_cents)
