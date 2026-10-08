"""FinancialState: everything the planner knows about a user's money at one moment."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from nextpay_engine.domain import (
    Bill,
    Debt,
    EssentialExpense,
    Goal,
    GoalKind,
    IncomeSource,
    Reserve,
    ReserveKind,
)
from nextpay_engine.money import Money


@dataclass(frozen=True, slots=True)
class FinancialState:
    """An immutable snapshot of a user's financial setup.

    ``available_balance`` is the money on hand before the paycheck being planned
    ($0 if none was entered; negative if overdrawn). Reserves are money already
    set aside inside that balance (ADR 0003). ``Goal.current`` is progress toward
    a goal; the backend keeps it in step with the goal's reserve on commit.

    ``no_deadline_goal_share_bps`` is the share of what is left after every other
    allocation that goes to goals with no deadline (or a passed one), in basis
    points: the default 2000 is 20%.
    """

    available_balance: Money
    income_sources: tuple[IncomeSource, ...] = ()
    bills: tuple[Bill, ...] = ()
    essentials: tuple[EssentialExpense, ...] = ()
    debts: tuple[Debt, ...] = ()
    goals: tuple[Goal, ...] = ()
    reserves: tuple[Reserve, ...] = ()
    no_deadline_goal_share_bps: int = 2000

    def __post_init__(self) -> None:
        if not isinstance(self.available_balance, Money):
            raise TypeError(
                f"available_balance must be Money, got {type(self.available_balance).__name__}"
            )
        for name in ("income_sources", "bills", "essentials", "debts", "goals", "reserves"):
            if type(getattr(self, name)) is not tuple:
                raise TypeError(f"{name} must be a tuple")
        share = self.no_deadline_goal_share_bps
        if type(share) is not int or not 0 <= share <= 10_000:
            raise ValueError(f"no_deadline_goal_share_bps must be an int 0-10000, got {share!r}")
        _require_unique_ids("income source", (source.id for source in self.income_sources))
        _require_unique_ids("bill", (bill.id for bill in self.bills))
        _require_unique_ids("essential expense", (item.id for item in self.essentials))
        _require_unique_ids("debt", (debt.id for debt in self.debts))
        _require_unique_ids("goal", (goal.id for goal in self.goals))
        if sum(goal.kind is GoalKind.EMERGENCY for goal in self.goals) > 1:
            raise ValueError("there can be at most one emergency goal")
        targets = {
            ReserveKind.BILL: {bill.id for bill in self.bills},
            ReserveKind.GOAL: {goal.id for goal in self.goals},
            ReserveKind.DEBT: {debt.id for debt in self.debts},
        }
        for reserve in self.reserves:
            if reserve.target_id not in targets[reserve.kind]:
                raise ValueError(
                    f"reserve points at unknown {reserve.kind.value} {reserve.target_id!r}"
                )

    @property
    def emergency_goal(self) -> Goal | None:
        return next((goal for goal in self.goals if goal.kind is GoalKind.EMERGENCY), None)

    def income_source(self, source_id: str) -> IncomeSource:
        """The income source with ``source_id``; ``ValueError`` if there is none."""
        for source in self.income_sources:
            if source.id == source_id:
                return source
        raise ValueError(f"unknown income source {source_id!r}")

    def reserved_for(self, kind: ReserveKind, target_id: str) -> Money:
        """Total already set aside for one bill, goal, or debt."""
        return sum(
            (r.amount for r in self.reserves if r.kind is kind and r.target_id == target_id),
            Money.zero(),
        )

    def total_reserved(self) -> Money:
        return sum((reserve.amount for reserve in self.reserves), Money.zero())


def _require_unique_ids(what: str, ids: Iterable[str]) -> None:
    duplicates = sorted(item for item, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"{what} ids must be unique, duplicated: {duplicates}")
