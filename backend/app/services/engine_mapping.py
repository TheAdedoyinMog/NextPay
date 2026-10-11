"""Database rows to the engine's domain types.

The engine validates its types on construction, so building one is how a
service checks a row against the engine's rules (see ``validated``): the two
cannot drift apart. Plan generation (2D) feeds the engine through the same
functions.
"""

from collections.abc import Callable, Iterable

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


def to_engine_reserve(row: models.Reserve) -> engine.Reserve:
    target_id = {
        engine.ReserveKind.BILL: row.bill_id,
        engine.ReserveKind.GOAL: row.goal_id,
        engine.ReserveKind.DEBT: row.debt_id,
    }[row.kind]
    return engine.Reserve(row.kind, str(target_id), engine.Money(row.amount_cents))


def to_engine_paycheck(row: models.Paycheck) -> engine.Paycheck:
    actual = row.actual_amount_cents
    return engine.Paycheck(
        source_id=str(row.income_source_id),
        pay_date=row.pay_date,
        expected_amount=engine.Money(row.expected_amount_cents),
        actual_amount=None if actual is None else engine.Money(actual),
    )


def to_engine_state(
    *,
    user: models.User,
    balance: models.BalanceSnapshot | None,
    income_sources: Iterable[models.IncomeSource],
    bills: Iterable[models.Bill],
    essentials: Iterable[models.EssentialExpense],
    debts: Iterable[models.Debt],
    goals: Iterable[models.Goal],
    reserves: Iterable[models.Reserve],
) -> engine.FinancialState:
    """Everything the planner knows about a user, from their rows.

    ``balance`` is their latest snapshot; with none, they start from $0.
    ``income_sources`` must be the active ones: an archived source pays nothing.
    A reserve of $0 is left out, since the planner treats it as no reserve.
    """
    return engine.FinancialState(
        available_balance=engine.Money.zero() if balance is None else to_engine_balance(balance),
        income_sources=tuple(to_engine_income_source(row) for row in income_sources),
        bills=tuple(to_engine_bill(row) for row in bills),
        essentials=tuple(to_engine_essential(row) for row in essentials),
        debts=tuple(to_engine_debt(row) for row in debts),
        goals=tuple(to_engine_goal(row) for row in goals),
        reserves=tuple(to_engine_reserve(row) for row in reserves if row.amount_cents != 0),
        no_deadline_goal_share_bps=user.no_deadline_goal_share_bps,
    )
