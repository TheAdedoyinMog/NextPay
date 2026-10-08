"""plan_paycheck: the priority waterfall for one paycheck (ADR 0002, ADR 0003).

The money to plan with is the available balance plus this paycheck, minus
everything already reserved. Tiers are funded in order; each asks for what its
targets need from this paycheck, and the money is handed out request by request
until it runs out. Whatever is left is Safe to Spend, never below $0.

Tiers (each a function from the plan context to its ordered requests):
  1. Bills: each bill's next due date, split across the paychecks before it.
  2. Essentials: prorated by the days until the next paycheck.
  3. Debt minimums: split across the paychecks before the due date, like bills.
  4. Emergency fund: what the emergency goal still needs.
  5. Goals: those with a deadline by priority, then deadline, each split across
     the paychecks before it (rounded up); then a share of what is left for
     goals with no deadline, or whose deadline has passed.

Every allocation carries its ``Basis``: a reason code and the facts behind the
amount, which ``explanations`` turns into English. Each goal also gets a
projected completion date at the rate this paycheck funded it.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from functools import cached_property
from itertools import groupby

from nextpay_engine.dates import require_date
from nextpay_engine.domain import Goal, GoalKind, Paycheck, ReserveKind, paycheck_timeline
from nextpay_engine.money import Money
from nextpay_engine.state import FinancialState

# Longer than any gap between two paydays of one schedule (at most 33 days: a
# 31-day month plus a 2-day weekend rollback at its start), so a
# window this wide on either side of a payday always holds the neighbouring ones.
_PAYDAY_LOOKAROUND = timedelta(days=62)

_BPS_WHOLE = 10_000  # basis points in 100%

# How far ahead a goal's completion date is projected; past this it is "not in sight".
_PROJECTION_HORIZON = timedelta(days=3653)  # ten years


class Tier(StrEnum):
    """Waterfall tiers, in funding order. Values are stable strings for storage."""

    BILL = "bill"
    ESSENTIAL = "essential"
    DEBT_MINIMUM = "debt_minimum"
    EMERGENCY_FUND = "emergency_fund"
    GOAL = "goal"


class Reason(StrEnum):
    """Why a target asked for money. Values are stable strings for storage."""

    BILL_DUE = "bill_due"
    ESSENTIAL = "essential"
    ESSENTIAL_PRORATED = "essential_prorated"  # covers only part of a pay period
    DEBT_MINIMUM = "debt_minimum"
    DEBT_PAYOFF = "debt_payoff"  # the minimum is capped at what is left on the debt
    EMERGENCY_FUND = "emergency_fund"
    GOAL_DEADLINE = "goal_deadline"
    GOAL_NO_DEADLINE = "goal_no_deadline"
    GOAL_DEADLINE_PASSED = "goal_deadline_passed"


@dataclass(frozen=True, slots=True)
class Basis:
    """The facts behind an allocation's request, for explaining it.

    Which facts are set depends on ``reason``:

    - ``total``: the bill amount, the debt minimum (or what is left on the debt),
      the essential's amount per period, or the goal's target.
    - ``set_aside``: already reserved for the bill or debt, or the goal's progress.
    - ``due``: when the bill or debt minimum is due, or the goal's deadline.
    - ``paychecks``: the paychecks the need is split across, this one included.
    - ``days_covered`` and ``days_in_period``: for essentials.
    - ``share_bps``: for goals sharing the leftover money.
    """

    reason: Reason
    name: str
    total: Money
    set_aside: Money = field(default_factory=Money.zero)
    due: date | None = None
    paychecks: int | None = None
    days_covered: int | None = None
    days_in_period: int | None = None
    share_bps: int | None = None


class GoalStatus(StrEnum):
    """Where a goal stands after a plan. Values are stable strings for storage."""

    COMPLETE = "complete"  # nothing left to save, counting this paycheck
    ON_TRACK = "on_track"  # projected to finish before its deadline
    BEHIND = "behind"  # projected to finish on or after its deadline, or not at all
    NO_DEADLINE = "no_deadline"
    DEADLINE_PASSED = "deadline_passed"  # passed, or before this paycheck could help


@dataclass(frozen=True, slots=True)
class GoalProjection:
    """When one goal would be reached if this paycheck's contribution repeated every paycheck.

    ``projected_date`` is the payday on the shared timeline that would finish the
    goal: this one if it finishes it now; None if it was already reached, gets
    nothing from this paycheck, or would take more than ten years.
    """

    goal_id: str
    name: str
    deadline: date | None
    contribution: Money
    still_needed: Money
    projected_date: date | None
    status: GoalStatus

    @property
    def suggested_deadline(self) -> date | None:
        """The date to suggest when the goal is behind or its deadline has passed."""
        if self.status in (GoalStatus.BEHIND, GoalStatus.DEADLINE_PASSED):
            return self.projected_date
        return None


@dataclass(frozen=True, slots=True)
class Allocation:
    """One line of a plan: what a target asked for from this paycheck, and what it got."""

    tier: Tier
    target_id: str
    requested: Money
    funded: Money
    basis: Basis

    @property
    def reason(self) -> Reason:
        return self.basis.reason

    @property
    def shortfall(self) -> Money:
        return self.requested - self.funded

    @property
    def is_underfunded(self) -> bool:
        return self.funded < self.requested


@dataclass(frozen=True, slots=True)
class PlanResult:
    """The plan for one paycheck.

    ``reserve_deficit`` is how far reserves exceed the money on hand (normally $0);
    when it is positive, nothing can be funded. An underfunded bill is a red alert.
    """

    paycheck: Paycheck
    as_of: date
    next_pay_date: date
    allocations: tuple[Allocation, ...]
    safe_to_spend: Money
    reserve_deficit: Money
    goal_projections: tuple[GoalProjection, ...]

    @property
    def underfunded(self) -> tuple[Allocation, ...]:
        return tuple(allocation for allocation in self.allocations if allocation.is_underfunded)


def plan_paycheck(state: FinancialState, paycheck: Paycheck, as_of: date) -> PlanResult:
    """Allocate one paycheck through the waterfall.

    ``as_of`` is "today", passed in because the engine never reads the clock. All
    period math runs from ``paycheck.pay_date``; ``as_of`` decides whether a goal's
    deadline has already passed.
    Raises ``ValueError`` if the paycheck's source is not in ``state``.
    """
    require_date(as_of, "as_of")
    state.income_source(paycheck.source_id)
    context = _Context(state, paycheck, as_of)

    pool = state.available_balance + paycheck.amount - state.total_reserved()
    remaining = max(pool, Money.zero())
    allocations: list[Allocation] = []

    def fund(requests: Iterable[_Request]) -> None:
        nonlocal remaining
        for request in requests:
            if not request.amount.is_positive():
                continue
            funded = min(request.amount, remaining)
            remaining -= funded
            allocations.append(
                Allocation(request.tier, request.target_id, request.amount, funded, request.basis)
            )

    for tier in _WATERFALL:
        fund(tier(context))
    # The leftover share depends on what every tier above left, so it is funded last.
    fund(_leftover_goal_requests(context, remaining))

    return PlanResult(
        paycheck=paycheck,
        as_of=as_of,
        next_pay_date=context.next_pay_date,
        allocations=tuple(allocations),
        safe_to_spend=remaining,
        reserve_deficit=max(-pool, Money.zero()),
        goal_projections=tuple(_project(context, goal, allocations) for goal in state.goals),
    )


@dataclass(frozen=True, slots=True)
class _Request:
    tier: Tier
    target_id: str
    amount: Money
    basis: Basis


class _Context:
    """Timeline facts about the paycheck being planned, computed once per plan."""

    def __init__(self, state: FinancialState, paycheck: Paycheck, as_of: date) -> None:
        self.state = state
        self.paycheck = paycheck
        self.as_of = as_of
        self._position = _timeline_position(paycheck)

        pay_date = paycheck.pay_date
        nearby = paycheck_timeline(state.income_sources, pay_date, pay_date + _PAYDAY_LOOKAROUND)
        self.next_pay_date = min(
            (p for p in nearby if _timeline_position(p) > self._position),
            key=_timeline_position,
        ).pay_date

        # Essentials are amounts per pay period of the primary (largest) income source.
        primary = min(state.income_sources, key=lambda s: (-s.expected_amount.cents, s.id))
        primary_paydays = primary.schedule.dates_between(
            pay_date - _PAYDAY_LOOKAROUND, pay_date + _PAYDAY_LOOKAROUND
        )
        period_start = max(day for day in primary_paydays if day <= pay_date)
        period_end = min(day for day in primary_paydays if day > pay_date)
        self.days_until_next = (self.next_pay_date - pay_date).days
        self.days_in_period = (period_end - period_start).days

    def paychecks_until(self, due: date) -> int:
        """This paycheck plus every later one on the shared timeline before ``due``.

        A paycheck that lands on the due date does not count toward it.
        """
        upcoming = paycheck_timeline(
            self.state.income_sources, self.paycheck.pay_date, due - timedelta(days=1)
        )
        return 1 + sum(1 for p in upcoming if _timeline_position(p) > self._position)

    @cached_property
    def later_paydays(self) -> tuple[date, ...]:
        """Pay dates of every later paycheck on the shared timeline, ten years ahead."""
        pay_date = self.paycheck.pay_date
        timeline = paycheck_timeline(
            self.state.income_sources, pay_date, pay_date + _PROJECTION_HORIZON
        )
        return tuple(p.pay_date for p in timeline if _timeline_position(p) > self._position)

    def is_overdue(self, goal: Goal) -> bool:
        """Whether ``goal``'s deadline has passed, or comes before this paycheck can help.

        A paycheck that lands on the deadline does not count toward it, as with bills.
        """
        deadline = goal.deadline
        return deadline is not None and (
            deadline < self.as_of or deadline <= self.paycheck.pay_date
        )


def _project(ctx: _Context, goal: Goal, allocations: list[Allocation]) -> GoalProjection:
    """Project ``goal`` forward at what it got from this plan."""
    contribution = sum(
        (
            a.funded
            for a in allocations
            if a.tier in (Tier.EMERGENCY_FUND, Tier.GOAL) and a.target_id == goal.id
        ),
        Money.zero(),
    )
    need = goal.target - goal.current
    projected: date | None = None
    if contribution.is_positive():
        paychecks = -(-need.cents // contribution.cents)  # this one included; ceiling division
        if paychecks == 1:
            projected = ctx.paycheck.pay_date
        elif paychecks - 2 < len(ctx.later_paydays):
            projected = ctx.later_paydays[paychecks - 2]

    still_needed = max(need - contribution, Money.zero())
    if not still_needed.is_positive():
        status = GoalStatus.COMPLETE
    elif goal.deadline is None:
        status = GoalStatus.NO_DEADLINE
    elif ctx.is_overdue(goal):
        status = GoalStatus.DEADLINE_PASSED
    elif projected is not None and projected < goal.deadline:
        status = GoalStatus.ON_TRACK
    else:
        status = GoalStatus.BEHIND
    return GoalProjection(
        goal.id, goal.name, goal.deadline, contribution, still_needed, projected, status
    )


def _timeline_position(paycheck: Paycheck) -> tuple[date, str]:
    """Order on the shared timeline: by date, then source id (as paycheck_timeline)."""
    return paycheck.pay_date, paycheck.source_id


# --- Tiers ------------------------------------------------------------------


def _bill_requests(ctx: _Context) -> tuple[_Request, ...]:
    """Each bill's share of its next due date, most important bill first."""
    keyed: list[tuple[tuple[int, date, str], _Request]] = []
    for bill in ctx.state.bills:
        due = bill.next_due_after(ctx.paycheck.pay_date)
        if due is None:
            continue
        reserved = ctx.state.reserved_for(ReserveKind.BILL, bill.id)
        need = bill.amount - reserved
        if not need.is_positive():
            continue
        paychecks = ctx.paychecks_until(due)
        basis = Basis(Reason.BILL_DUE, bill.name, bill.amount, reserved, due, paychecks)
        request = _Request(Tier.BILL, bill.id, need.split(paychecks)[0], basis)
        keyed.append(((bill.priority, due, bill.id), request))
    return tuple(request for _, request in sorted(keyed, key=lambda item: item[0]))


def _essential_requests(ctx: _Context) -> tuple[_Request, ...]:
    """Each essential, prorated by the days until the next paycheck (rounded up)."""
    whole_period = ctx.days_until_next >= ctx.days_in_period
    reason = Reason.ESSENTIAL if whole_period else Reason.ESSENTIAL_PRORATED
    return tuple(
        _Request(
            Tier.ESSENTIAL,
            item.id,
            item.amount_per_period.prorate(ctx.days_until_next, ctx.days_in_period),
            Basis(
                reason,
                item.name,
                item.amount_per_period,
                days_covered=ctx.days_until_next,
                days_in_period=ctx.days_in_period,
            ),
        )
        for item in sorted(ctx.state.essentials, key=lambda item: item.id)
    )


def _debt_minimum_requests(ctx: _Context) -> tuple[_Request, ...]:
    """Each debt's minimum (capped at its balance), split like a bill, soonest due first."""
    keyed: list[tuple[tuple[date, str], _Request]] = []
    for debt in ctx.state.debts:
        due = debt.next_due_after(ctx.paycheck.pay_date)
        minimum = min(debt.minimum_payment, debt.balance)
        reserved = ctx.state.reserved_for(ReserveKind.DEBT, debt.id)
        need = minimum - reserved
        if not need.is_positive():
            continue
        paychecks = ctx.paychecks_until(due)
        payoff = debt.balance < debt.minimum_payment
        reason = Reason.DEBT_PAYOFF if payoff else Reason.DEBT_MINIMUM
        basis = Basis(reason, debt.name, minimum, reserved, due, paychecks)
        request = _Request(Tier.DEBT_MINIMUM, debt.id, need.split(paychecks)[0], basis)
        keyed.append(((due, debt.id), request))
    return tuple(request for _, request in sorted(keyed, key=lambda item: item[0]))


def _emergency_fund_requests(ctx: _Context) -> tuple[_Request, ...]:
    """Whatever the emergency goal still needs; nothing if there is no emergency goal."""
    goal = ctx.state.emergency_goal
    if goal is None:
        return ()
    basis = Basis(Reason.EMERGENCY_FUND, goal.name, goal.target, goal.current)
    return (_Request(Tier.EMERGENCY_FUND, goal.id, goal.target - goal.current, basis),)


def _goal_requests(ctx: _Context) -> tuple[_Request, ...]:
    """Each goal with a deadline still ahead: what it needs over the paychecks before it.

    Rounded up, so paying the share every paycheck finishes the goal on time.
    """
    keyed: list[tuple[tuple[int, date, str], _Request]] = []
    for goal in ctx.state.goals:
        if goal.kind is GoalKind.EMERGENCY or goal.deadline is None or ctx.is_overdue(goal):
            continue
        need = goal.target - goal.current
        if not need.is_positive():
            continue
        paychecks = ctx.paychecks_until(goal.deadline)
        basis = Basis(
            Reason.GOAL_DEADLINE, goal.name, goal.target, goal.current, goal.deadline, paychecks
        )
        request = _Request(Tier.GOAL, goal.id, need.prorate(1, paychecks), basis)
        keyed.append(((goal.priority, goal.deadline, goal.id), request))
    return tuple(request for _, request in sorted(keyed, key=lambda item: item[0]))


def _leftover_goal_requests(ctx: _Context, available: Money) -> tuple[_Request, ...]:
    """Goals with no deadline, or one that has passed: a share of what is left.

    The share is ``no_deadline_goal_share_bps`` of ``available``, the money left after
    every tier above. Goals take it in priority order; goals of equal priority split
    it evenly, and none takes more than it needs, passing the rest on.
    """
    goals = sorted(
        (
            goal
            for goal in ctx.state.goals
            if goal.kind is not GoalKind.EMERGENCY
            and (goal.deadline is None or ctx.is_overdue(goal))
            and goal.current < goal.target
        ),
        key=lambda goal: (goal.priority, goal.id),
    )
    share_bps = ctx.state.no_deadline_goal_share_bps
    budget = available.prorate(share_bps, _BPS_WHOLE)
    requests: list[_Request] = []
    for _, group in groupby(goals, key=lambda goal: goal.priority):
        members = list(group)
        shares, budget = _share_evenly(
            budget, {goal.id: goal.target - goal.current for goal in members}
        )
        for goal in members:
            passed = goal.deadline is not None
            reason = Reason.GOAL_DEADLINE_PASSED if passed else Reason.GOAL_NO_DEADLINE
            basis = Basis(
                reason, goal.name, goal.target, goal.current, goal.deadline, share_bps=share_bps
            )
            requests.append(_Request(Tier.GOAL, goal.id, shares[goal.id], basis))
    return tuple(requests)


def _share_evenly(budget: Money, needs: dict[str, Money]) -> tuple[dict[str, Money], Money]:
    """Split ``budget`` evenly across ``needs``, never giving one more than it needs.

    One that needs less than its even part is filled and drops out, and the rest is
    split again among the others. Returns each share, in ``needs`` order, and what is
    left of the budget.
    """
    shares = dict.fromkeys(needs, Money.zero())
    open_ids = list(needs)
    while budget.is_positive() and open_ids:
        parts = dict(zip(open_ids, budget.split(len(open_ids)), strict=True))
        filled = [key for key in open_ids if needs[key] - shares[key] <= parts[key]]
        if not filled:
            for key in open_ids:
                shares[key] += parts[key]
            return shares, Money.zero()
        for key in filled:
            budget -= needs[key] - shares[key]
            shares[key] = needs[key]
            open_ids.remove(key)
    return shares, budget


_WATERFALL: tuple[Callable[[_Context], tuple[_Request, ...]], ...] = (
    _bill_requests,
    _essential_requests,
    _debt_minimum_requests,
    _emergency_fund_requests,
    _goal_requests,
)
