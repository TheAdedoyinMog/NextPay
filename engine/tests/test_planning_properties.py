"""Property tests: rules the waterfall must keep for any financial state."""

from dataclasses import replace
from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from nextpay_engine.domain import (
    Bill,
    Debt,
    EssentialExpense,
    Goal,
    GoalKind,
    IncomeSource,
    Paycheck,
    Payment,
    PaymentKind,
    Reserve,
    ReserveKind,
)
from nextpay_engine.explanations import explain_allocation, explain_plan, explain_projection
from nextpay_engine.money import Money
from nextpay_engine.pay_schedules import Biweekly, Monthly, PaySchedule, SemiMonthly, Weekly
from nextpay_engine.planning import GoalStatus, PlanResult, Reason, Tier, plan_paycheck
from nextpay_engine.recurrence import BillRecurrence, EveryNMonths, OneTime
from nextpay_engine.state import FinancialState

SAVINGS = (Tier.EMERGENCY_FUND, Tier.GOAL)
LEFTOVER_REASONS = (Reason.GOAL_NO_DEADLINE, Reason.GOAL_DEADLINE_PASSED)

BASE = date(2026, 10, 1)
near_dates = st.dates(min_value=BASE - timedelta(days=400), max_value=BASE + timedelta(days=400))
positive = st.builds(Money, st.integers(min_value=1, max_value=500_000))
non_negative = st.builds(Money, st.integers(min_value=0, max_value=500_000))

schedules: st.SearchStrategy[PaySchedule] = st.one_of(
    st.builds(Weekly, near_dates),
    st.builds(Biweekly, near_dates),
    st.sampled_from([SemiMonthly(1, 15), SemiMonthly(15, 31), SemiMonthly(5, 20)]),
    st.builds(Monthly, st.integers(min_value=1, max_value=31)),
)
recurrences: st.SearchStrategy[BillRecurrence] = st.one_of(
    st.builds(OneTime, near_dates),
    st.builds(EveryNMonths, near_dates, st.sampled_from([1, 1, 1, 3, 12])),
)


@st.composite
def states(draw: st.DrawFn, single_source: bool = False) -> FinancialState:
    source_count = 1 if single_source else draw(st.integers(min_value=1, max_value=3))
    sources = tuple(
        IncomeSource(f"s{i}", f"Source {i}", draw(schedules), draw(positive))
        for i in range(source_count)
    )
    bills = tuple(
        Bill(f"b{i}", f"Bill {i}", draw(positive), draw(recurrences), draw(st.integers(1, 3)))
        for i in range(draw(st.integers(min_value=0, max_value=4)))
    )
    essentials = tuple(
        EssentialExpense(f"e{i}", f"Essential {i}", draw(positive))
        for i in range(draw(st.integers(min_value=0, max_value=3)))
    )
    debts = tuple(
        Debt(
            f"d{i}",
            f"Debt {i}",
            draw(non_negative),
            draw(st.integers(min_value=0, max_value=3000)),
            draw(non_negative),
            draw(st.integers(min_value=1, max_value=31)),
        )
        for i in range(draw(st.integers(min_value=0, max_value=3)))
    )
    goals: tuple[Goal, ...] = ()
    if draw(st.booleans()):
        goals = (
            Goal("ef", "Emergency", GoalKind.EMERGENCY, draw(positive), draw(non_negative), 1),
        )
    goals += tuple(
        Goal(
            f"g{i}",
            f"Goal {i}",
            draw(st.sampled_from([GoalKind.SAVINGS, GoalKind.PURCHASE])),
            draw(positive),
            draw(non_negative),
            draw(st.integers(min_value=1, max_value=3)),
            draw(st.none() | near_dates),
        )
        for i in range(draw(st.integers(min_value=0, max_value=4)))
    )

    targets = (
        [(ReserveKind.BILL, b.id) for b in bills]
        + [(ReserveKind.DEBT, d.id) for d in debts]
        + [(ReserveKind.GOAL, g.id) for g in goals]
    )
    reserves: tuple[Reserve, ...] = ()
    if targets:
        reserves = tuple(
            Reserve(kind, target_id, draw(non_negative))
            for kind, target_id in draw(st.lists(st.sampled_from(targets), max_size=4))
        )
    balance = Money(draw(st.integers(min_value=-200_000, max_value=1_000_000)))
    share_bps = draw(st.sampled_from([0, 2000, 2000, 3333, 10_000]))
    payable: list[Bill | Debt] = [*bills, *debts]
    payments: tuple[Payment, ...] = ()
    if payable:
        payments = tuple(
            draw(payments_toward(target))
            for target in draw(st.lists(st.sampled_from(payable), max_size=6))
        )
    return FinancialState(
        balance, sources, bills, essentials, debts, goals, reserves, share_bps, payments
    )


@st.composite
def payments_toward(draw: st.DrawFn, target: Bill | Debt) -> Payment:
    """A payment toward one of ``target``'s due dates near the paydays planned, now and
    then toward a date that is not a due date (its schedule was edited since)."""
    due_dates = target.due_dates_between(BASE - timedelta(days=40), BASE + timedelta(days=200))
    due = draw(st.sampled_from(due_dates) if due_dates and draw(st.integers(0, 9)) else near_dates)
    kind = PaymentKind.BILL if isinstance(target, Bill) else PaymentKind.DEBT
    # Mostly about the size of a bill or minimum, so occurrences get exactly paid, too.
    size = target.amount if isinstance(target, Bill) else target.minimum_payment
    amount = size if size.is_positive() and draw(st.booleans()) else draw(positive)
    return Payment(kind, target.id, due, draw(near_dates), amount)


@st.composite
def plans(draw: st.DrawFn, single_source: bool = False) -> tuple[FinancialState, PlanResult]:
    state = draw(states(single_source=single_source))
    source = draw(st.sampled_from(state.income_sources))
    paydays = source.schedule.dates_between(BASE, BASE + timedelta(days=62))
    actual = draw(st.none() | non_negative)
    paycheck = Paycheck(source.id, draw(st.sampled_from(paydays)), source.expected_amount, actual)
    # Usually planned on payday; sometimes ahead of time, or re-planned a little late.
    as_of = paycheck.pay_date - timedelta(days=draw(st.sampled_from([0, 0, 0, 1, 10, -3])))
    return state, plan_paycheck(state, paycheck, as_of=as_of)


def pool(state: FinancialState, result: PlanResult) -> Money:
    return state.available_balance + result.paycheck.amount - state.total_reserved()


@given(plans())
def test_safe_to_spend_and_deficit_are_never_negative(
    case: tuple[FinancialState, PlanResult],
) -> None:
    _, result = case
    assert not result.safe_to_spend.is_negative()
    assert not result.reserve_deficit.is_negative()


@given(plans())
def test_every_allocation_is_funded_between_zero_and_its_request(
    case: tuple[FinancialState, PlanResult],
) -> None:
    _, result = case
    for allocation in result.allocations:
        assert allocation.requested.is_positive()
        assert Money.zero() <= allocation.funded <= allocation.requested


@given(plans())
def test_no_cent_is_created_or_lost(case: tuple[FinancialState, PlanResult]) -> None:
    state, result = case
    funded = sum((a.funded for a in result.allocations), Money.zero())
    assert funded + result.safe_to_spend == max(pool(state, result), Money.zero())
    assert result.reserve_deficit == max(-pool(state, result), Money.zero())


@given(plans())
def test_tiers_are_funded_in_waterfall_order(case: tuple[FinancialState, PlanResult]) -> None:
    _, result = case
    order = list(Tier)
    positions = [order.index(a.tier) for a in result.allocations]
    assert positions == sorted(positions)
    # Once the money runs out, nothing after that point is funded.
    first_short = next(
        (i for i, a in enumerate(result.allocations) if a.is_underfunded), len(result.allocations)
    )
    assert all(a.funded.is_zero() for a in result.allocations[first_short + 1 :])
    if result.underfunded:
        assert result.safe_to_spend.is_zero()


@given(plans())
def test_a_reserve_deficit_funds_nothing(case: tuple[FinancialState, PlanResult]) -> None:
    _, result = case
    if result.reserve_deficit.is_positive():
        assert result.safe_to_spend.is_zero()
        assert all(a.funded.is_zero() for a in result.allocations)


@given(plans(single_source=True))
def test_one_job_funds_each_essential_exactly(case: tuple[FinancialState, PlanResult]) -> None:
    state, result = case
    requested = {a.target_id: a.requested for a in result.allocations if a.tier is Tier.ESSENTIAL}
    assert requested == {e.id: e.amount_per_period for e in state.essentials}


@given(plans())
def test_next_pay_date_is_on_or_after_this_payday(case: tuple[FinancialState, PlanResult]) -> None:
    _, result = case
    assert result.paycheck.pay_date <= result.next_pay_date
    # Longest gap: a 31-day month plus a 2-day weekend rollback (Monthly(4): Oct 2 -> Nov 4).
    assert result.next_pay_date <= result.paycheck.pay_date + timedelta(days=33)


# --- Goals ------------------------------------------------------------------


@given(plans())
def test_no_goal_gets_more_than_it_needs(case: tuple[FinancialState, PlanResult]) -> None:
    state, result = case
    for goal in state.goals:
        got = sum(
            (a.funded for a in result.allocations if a.target_id == goal.id and a.tier in SAVINGS),
            Money.zero(),
        )
        assert got <= max(goal.target - goal.current, Money.zero())


@given(plans())
def test_leftover_share_never_exceeds_its_percentage(
    case: tuple[FinancialState, PlanResult],
) -> None:
    state, result = case
    leftover = [a for a in result.allocations if a.reason in LEFTOVER_REASONS]
    shared = sum((a.funded for a in leftover), Money.zero())
    available = shared + result.safe_to_spend  # what every tier above left
    assert shared <= available.prorate(state.no_deadline_goal_share_bps, 10_000)
    assert all(not a.is_underfunded for a in leftover)


@given(plans())
def test_every_goal_gets_one_consistent_projection(
    case: tuple[FinancialState, PlanResult],
) -> None:
    state, result = case
    assert [p.goal_id for p in result.goal_projections] == [g.id for g in state.goals]
    pay_date = result.paycheck.pay_date
    for goal, projection in zip(state.goals, result.goal_projections, strict=True):
        need = max(goal.target - goal.current, Money.zero())
        assert projection.still_needed == need - projection.contribution
        if projection.projected_date is not None:
            assert pay_date <= projection.projected_date <= pay_date + timedelta(days=3653)
            assert projection.contribution.is_positive()
        if projection.status is GoalStatus.ON_TRACK:
            assert goal.deadline is not None
            assert projection.projected_date is not None
            assert projection.projected_date < goal.deadline


@given(plans())
def test_fully_funded_goal_with_a_deadline_is_on_track(
    case: tuple[FinancialState, PlanResult],
) -> None:
    _, result = case
    funded_on_schedule = {
        a.target_id
        for a in result.allocations
        if a.reason is Reason.GOAL_DEADLINE and not a.is_underfunded
    }
    for projection in result.goal_projections:
        if projection.goal_id in funded_on_schedule:
            assert projection.status in (GoalStatus.ON_TRACK, GoalStatus.COMPLETE)


@given(plans())
def test_everything_in_a_plan_can_be_explained(case: tuple[FinancialState, PlanResult]) -> None:
    _, result = case
    for allocation in result.allocations:
        assert explain_allocation(allocation, result).endswith(".")
    for projection in result.goal_projections:
        assert explain_projection(projection, result).endswith(".")
    assert explain_plan(result).endswith(".")


# --- Paid occurrences (ADR 0018) ---------------------------------------------


def paid_toward(state: FinancialState, kind: PaymentKind, target_id: str, due: date) -> Money:
    return sum(
        (p.amount for p in state.payments_for(kind, target_id) if p.due == due), Money.zero()
    )


@given(plans())
def test_no_line_asks_for_more_than_its_occurrence_still_owes(
    case: tuple[FinancialState, PlanResult],
) -> None:
    state, result = case
    bills = {bill.id: bill for bill in state.bills}
    debts = {debt.id: debt for debt in state.debts}
    for a in result.allocations:
        due = a.basis.due
        if a.tier is Tier.BILL:
            assert due is not None
            paid = paid_toward(state, PaymentKind.BILL, a.target_id, due)
            unpaid = max(bills[a.target_id].amount - paid, Money.zero())
            reserved = state.reserved_for(ReserveKind.BILL, a.target_id)
        elif a.tier is Tier.DEBT_MINIMUM:
            assert due is not None
            debt = debts[a.target_id]
            paid = paid_toward(state, PaymentKind.DEBT, a.target_id, due)
            unpaid = min(max(debt.minimum_payment - paid, Money.zero()), debt.balance)
            reserved = state.reserved_for(ReserveKind.DEBT, a.target_id)
        else:
            continue
        assert due > result.paycheck.pay_date
        assert Money.zero() < a.requested <= unpaid - reserved


@given(plans())
def test_payments_due_on_or_before_the_payday_change_nothing(
    case: tuple[FinancialState, PlanResult],
) -> None:
    # Why the input hash leaves them out (backend plan_inputs).
    state, result = case
    later = tuple(p for p in state.payments if p.due > result.paycheck.pay_date)
    assert plan_paycheck(replace(state, payments=later), result.paycheck, result.as_of) == result


@given(plans(), st.data())
def test_paying_and_then_undoing_gives_the_same_plan_as_never_paying(
    case: tuple[FinancialState, PlanResult], data: st.DataObject
) -> None:
    """Pay as the backend does (ADR 0011, 0016): draw the reserve down, lower the debt's
    balance, record the payment. Undo as it does (ADR 0017): put back exactly what was
    taken, and leave the payment out."""
    state, result = case
    payable: list[Bill | Debt] = [*state.bills, *state.debts]
    if not payable:
        return
    payment = data.draw(payments_toward(data.draw(st.sampled_from(payable))))
    kind = ReserveKind.BILL if payment.kind is PaymentKind.BILL else ReserveKind.DEBT

    reserve = state.reserved_for(kind, payment.target_id)
    drawn = min(reserve, payment.amount)
    debts = state.debts
    reduced = Money.zero()
    if kind is ReserveKind.DEBT:
        debt = next(d for d in debts if d.id == payment.target_id)
        reduced = min(payment.amount, debt.balance)
        debts = tuple(replace(d, balance=d.balance - reduced) if d is debt else d for d in debts)
    others = tuple(r for r in state.reserves if (r.kind, r.target_id) != (kind, payment.target_id))
    paid = replace(
        state,
        debts=debts,
        reserves=(*others, Reserve(kind, payment.target_id, reserve - drawn)),
        payments=(*state.payments, payment),
    )

    undone = replace(
        paid,
        debts=tuple(
            replace(d, balance=d.balance + reduced) if d.id == payment.target_id else d
            for d in paid.debts
        )
        if kind is ReserveKind.DEBT
        else paid.debts,
        reserves=(*others, Reserve(kind, payment.target_id, reserve)),
        payments=state.payments,
    )
    assert plan_paycheck(undone, result.paycheck, result.as_of) == result
