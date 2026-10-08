"""The engine's core domain objects: income, bills, expenses, debts, goals, reserves.

Every type is a frozen dataclass that validates itself on construction, so an
invalid object can never reach the planner. Rules that need "today" (such as a
goal deadline already passed) or the whole collection (such as one emergency
goal) are checked at planning time, not here.

Ids are opaque strings chosen by the caller; the engine only compares them.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from nextpay_engine.dates import (
    add_months,
    clamped_date,
    months_spanning,
    require_date,
    require_day_of_month,
    require_range,
)
from nextpay_engine.money import Money
from nextpay_engine.pay_schedules import PaySchedule
from nextpay_engine.recurrence import BillRecurrence


class GoalKind(StrEnum):
    EMERGENCY = "emergency"
    SAVINGS = "savings"
    PURCHASE = "purchase"  # "I want this" items are goals (ADR 0004)


class ReserveKind(StrEnum):
    BILL = "bill"
    GOAL = "goal"
    DEBT = "debt"


@dataclass(frozen=True, slots=True)
class IncomeSource:
    """A job or other regular income, paid on ``schedule`` (ADR 0005)."""

    id: str
    name: str
    schedule: PaySchedule
    expected_amount: Money

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.name, "name")
        _require_money(self.expected_amount, "expected_amount", positive=True)

    def paychecks_between(self, start: date, end: date) -> tuple["Paycheck", ...]:
        """Expected paychecks from ``start`` to ``end`` inclusive, by pay date."""
        return tuple(
            Paycheck(source_id=self.id, pay_date=day, expected_amount=self.expected_amount)
            for day in self.schedule.dates_between(start, end)
        )


@dataclass(frozen=True, slots=True)
class Paycheck:
    """One paycheck: expected up front; the actual amount is recorded when paid."""

    source_id: str
    pay_date: date
    expected_amount: Money
    actual_amount: Money | None = None

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        require_date(self.pay_date, "pay_date")
        _require_money(self.expected_amount, "expected_amount", positive=True)
        if self.actual_amount is not None:
            # $0 is a real outcome, for example unpaid leave.
            _require_money(self.actual_amount, "actual_amount", non_negative=True)

    @property
    def amount(self) -> Money:
        """The amount to plan with: the actual amount once recorded, else the expected."""
        return self.expected_amount if self.actual_amount is None else self.actual_amount


@dataclass(frozen=True, slots=True)
class Bill:
    """A bill due on the dates given by ``recurrence``. Priority 1 is the most important."""

    id: str
    name: str
    amount: Money
    recurrence: BillRecurrence
    priority: int

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.name, "name")
        _require_money(self.amount, "amount", positive=True)
        _require_priority(self.priority)

    def due_dates_between(self, start: date, end: date) -> tuple[date, ...]:
        return self.recurrence.due_dates_between(start, end)

    def next_due_after(self, day: date) -> date | None:
        return self.recurrence.next_due_after(day)


@dataclass(frozen=True, slots=True)
class EssentialExpense:
    """A spending need funded every pay period, such as groceries or gas."""

    id: str
    name: str
    amount_per_period: Money

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.name, "name")
        _require_money(self.amount_per_period, "amount_per_period", positive=True)


@dataclass(frozen=True, slots=True)
class Debt:
    """A debt with a monthly minimum payment due on ``due_day``.

    ``apr_bps`` is the annual rate in basis points (24.99% is 2499), keeping the
    engine free of floats. A ``due_day`` past the end of a month means its last day.
    """

    id: str
    name: str
    balance: Money
    apr_bps: int
    minimum_payment: Money
    due_day: int

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.name, "name")
        _require_money(self.balance, "balance", non_negative=True)
        if type(self.apr_bps) is not int or self.apr_bps < 0:
            raise ValueError(f"apr_bps must be an int >= 0, got {self.apr_bps!r}")
        _require_money(self.minimum_payment, "minimum_payment", non_negative=True)
        require_day_of_month(self.due_day, "due_day")

    def due_dates_between(self, start: date, end: date) -> tuple[date, ...]:
        """Minimum-payment due dates from ``start`` to ``end`` inclusive."""
        require_range(start, end)
        due_dates = (
            clamped_date(year, month, self.due_day) for year, month in months_spanning(start, end)
        )
        return tuple(day for day in due_dates if start <= day <= end)

    def next_due_after(self, day: date) -> date:
        """The first minimum-payment due date strictly after ``day``."""
        require_date(day, "day")
        due = clamped_date(day.year, day.month, self.due_day)
        if due > day:
            return due
        year, month = add_months(day.year, day.month, 1)
        return clamped_date(year, month, self.due_day)


@dataclass(frozen=True, slots=True)
class Goal:
    """Something to save for. ``current`` may exceed ``target`` once it is reached."""

    id: str
    name: str
    kind: GoalKind
    target: Money
    current: Money
    priority: int
    deadline: date | None = None

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.name, "name")
        if type(self.kind) is not GoalKind:
            raise TypeError(f"kind must be a GoalKind, got {self.kind!r}")
        _require_money(self.target, "target", positive=True)
        _require_money(self.current, "current", non_negative=True)
        _require_priority(self.priority)
        if self.deadline is not None:
            require_date(self.deadline, "deadline")


@dataclass(frozen=True, slots=True)
class Reserve:
    """Money already set aside for a bill, goal, or debt (ADR 0003)."""

    kind: ReserveKind
    target_id: str
    amount: Money

    def __post_init__(self) -> None:
        if type(self.kind) is not ReserveKind:
            raise TypeError(f"kind must be a ReserveKind, got {self.kind!r}")
        _require_text(self.target_id, "target_id")
        _require_money(self.amount, "amount", non_negative=True)


def paycheck_timeline(
    sources: Iterable[IncomeSource], start: date, end: date
) -> tuple[Paycheck, ...]:
    """Every source's paychecks from ``start`` to ``end`` on one shared timeline.

    Sorted by pay date, then source id, so two jobs paying on the same day always
    come out in the same order.
    """
    require_range(start, end)
    sources = tuple(sources)
    ids = [source.id for source in sources]
    if len(set(ids)) != len(ids):
        raise ValueError(f"income source ids must be unique, got {ids}")
    paychecks = (
        paycheck for source in sources for paycheck in source.paychecks_between(start, end)
    )
    return tuple(sorted(paychecks, key=lambda paycheck: (paycheck.pay_date, paycheck.source_id)))


def _require_text(value: str, name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{name} must be a str, got {type(value).__name__}")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")


def _require_money(
    value: Money, name: str, *, positive: bool = False, non_negative: bool = False
) -> None:
    if not isinstance(value, Money):
        raise TypeError(f"{name} must be Money, got {type(value).__name__}")
    if positive and not value.is_positive():
        raise ValueError(f"{name} must be positive, got {value}")
    if non_negative and value.is_negative():
        raise ValueError(f"{name} must not be negative, got {value}")


def _require_priority(priority: int) -> None:
    if type(priority) is not int or priority < 1:
        raise ValueError(f"priority must be an int >= 1, got {priority!r}")
