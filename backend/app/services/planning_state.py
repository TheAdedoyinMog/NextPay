"""Loading everything the planner needs to know about one user (ADR 0011).

One place reads a user's rows and turns them into the engine's
``FinancialState``, so generating a plan and checking whether a plan is still
up to date always see the user the same way.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import nextpay_engine as engine
from app.models import (
    BalanceSnapshot,
    Bill,
    Debt,
    EssentialExpense,
    Goal,
    IncomeSource,
    Reserve,
    User,
)
from app.services.engine_mapping import to_engine_state


class Listing[M](Protocol):
    """A store that can list one user's rows. For income sources: the active ones."""

    def list_for(self, user_id: uuid.UUID) -> Sequence[M]: ...


class LatestBalances(Protocol):
    def latest(self, user_id: uuid.UUID, limit: int) -> Sequence[BalanceSnapshot]: ...


@dataclass(frozen=True, slots=True)
class PlanningInputs:
    state: engine.FinancialState
    # The snapshot ``state.available_balance`` came from; None if the user has none ($0).
    balance: BalanceSnapshot | None


class PlanningStateLoader:
    def __init__(
        self,
        *,
        income_sources: Listing[IncomeSource],
        bills: Listing[Bill],
        essentials: Listing[EssentialExpense],
        debts: Listing[Debt],
        goals: Listing[Goal],
        reserves: Listing[Reserve],
        balances: LatestBalances,
    ) -> None:
        self._income_sources = income_sources
        self._bills = bills
        self._essentials = essentials
        self._debts = debts
        self._goals = goals
        self._reserves = reserves
        self._balances = balances

    def load(self, user: User) -> PlanningInputs:
        """``user``'s financial state as it stands now."""
        latest = self._balances.latest(user.id, 1)
        balance = latest[0] if latest else None
        state = to_engine_state(
            user=user,
            balance=balance,
            income_sources=self._income_sources.list_for(user.id),
            bills=self._bills.list_for(user.id),
            essentials=self._essentials.list_for(user.id),
            debts=self._debts.list_for(user.id),
            goals=self._goals.list_for(user.id),
            reserves=self._reserves.list_for(user.id),
        )
        return PlanningInputs(state, balance)
