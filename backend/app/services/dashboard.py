"""The home screen's facts, worked out here so the app never picks paydays or plans itself.

Everything comes from the other services: the paycheck timeline (paydays are the
engine's), the plans stored for them, the latest balance, and the payments since
the plan that counts was committed (ADR 0003, ADR 0015, ADR 0016).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

from app.core.clock import Clock, local_date
from app.models import BalanceSnapshot, PlanStatus, User
from app.services.paychecks import PaycheckEntry, PaycheckService
from app.services.plans import PlanService

# Far enough back to find the last payday of a monthly schedule, and forward to find the next.
_LOOK_BACK = timedelta(days=62)
_LOOK_AHEAD = timedelta(days=62)


class LatestBalances(Protocol):
    def latest(self, user_id: uuid.UUID, limit: int) -> Sequence[BalanceSnapshot]: ...


class UnreservedPayments(Protocol):
    def unreserved_since(self, user_id: uuid.UUID, since: datetime) -> int: ...


@dataclass(frozen=True, slots=True)
class SafeToSpendNow:
    """The committed plan's Safe to Spend, less what payments since then paid beyond
    what was set aside for them (ADR 0016).

    A payment covered by its reserve changes nothing: the money leaves and the
    reserve falls by the same amount. Only the part beyond the reserve comes out of
    what was free. Past $0 it becomes a shortfall, as in a plan, never a negative.
    """

    entry: PaycheckEntry
    safe_to_spend_cents: int
    reserve_deficit_cents: int
    # What payments recorded since the commit paid beyond their reserves.
    paid_beyond_reserves_cents: int


@dataclass(frozen=True, slots=True)
class Dashboard:
    # Today in the user's time zone: the day a plan made now is for.
    today: date
    # The newest payday on or before today, across income sources; None before the first.
    current: PaycheckEntry | None
    # The first payday after today.
    next: PaycheckEntry | None
    # From the newest committed plan for a payday on or before today, with payments since.
    safe_to_spend: SafeToSpendNow | None
    balance: BalanceSnapshot | None
    # Ids of the draft plans above that are out of date.
    out_of_date: frozenset[uuid.UUID]


class DashboardService:
    def __init__(
        self,
        *,
        paychecks: PaycheckService,
        plans: PlanService,
        balances: LatestBalances,
        payments: Sequence[UnreservedPayments],
        clock: Clock,
    ) -> None:
        self._paychecks = paychecks
        self._plans = plans
        self._balances = balances
        self._payments = payments
        self._clock = clock

    def for_user(self, user: User) -> Dashboard:
        today = local_date(self._clock(), user.timezone)
        timeline = self._paychecks.timeline(user, today - _LOOK_BACK, today + _LOOK_AHEAD)
        past = [entry for entry in timeline if entry.pay_date <= today]
        ahead = [entry for entry in timeline if entry.pay_date > today]
        committed = [
            entry
            for entry in past
            if entry.plan is not None and entry.plan.status is PlanStatus.COMMITTED
        ]
        current = past[-1] if past else None
        next_ = ahead[0] if ahead else None
        planned = [
            (entry.plan, entry.paycheck)
            for entry in (current, next_)
            if entry is not None and entry.plan is not None and entry.paycheck is not None
        ]
        latest = self._balances.latest(user.id, 1)
        return Dashboard(
            today=today,
            current=current,
            next=next_,
            safe_to_spend=self._safe_to_spend(user, committed[-1]) if committed else None,
            balance=latest[0] if latest else None,
            out_of_date=frozenset(self._plans.out_of_date(user, planned)),
        )

    def _safe_to_spend(self, user: User, entry: PaycheckEntry) -> SafeToSpendNow:
        plan = entry.plan
        assert plan is not None and plan.committed_at is not None  # a committed plan
        beyond = sum(store.unreserved_since(user.id, plan.committed_at) for store in self._payments)
        # Signed: what is free after the plan, then after the payments beyond reserves.
        free = plan.safe_to_spend_cents - plan.reserve_deficit_cents - beyond
        return SafeToSpendNow(
            entry=entry,
            safe_to_spend_cents=max(free, 0),
            reserve_deficit_cents=max(-free, 0),
            paid_beyond_reserves_cents=beyond,
        )
