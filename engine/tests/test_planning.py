from dataclasses import replace
from datetime import date, datetime

import pytest

from nextpay_engine.domain import (
    Bill,
    Debt,
    EssentialExpense,
    Goal,
    GoalKind,
    IncomeSource,
    Paycheck,
    Reserve,
    ReserveKind,
)
from nextpay_engine.money import Money
from nextpay_engine.pay_schedules import Biweekly, Monthly, SemiMonthly
from nextpay_engine.planning import (
    Allocation,
    Basis,
    GoalProjection,
    GoalStatus,
    PlanResult,
    Reason,
    Tier,
    plan_paycheck,
)
from nextpay_engine.recurrence import EveryNMonths, OneTime
from nextpay_engine.state import FinancialState

# Biweekly Fridays: Oct 2, Oct 16, Oct 30, Nov 13 2026.
JOB = IncomeSource("job", "Job", Biweekly(date(2026, 10, 2)), Money.parse("1500"))
SIDE = IncomeSource("side", "Tutoring", SemiMonthly(1, 16), Money.parse("300"))
RENT = Bill("rent", "Rent", Money.parse("800"), EveryNMonths(date(2026, 1, 20)), priority=1)
GROCERIES = EssentialExpense("groceries", "Groceries", Money.parse("200"))
CAR = Debt("car", "Car loan", Money.parse("9000"), 699, Money.parse("150"), due_day=20)
EMERGENCY = Goal("ef", "Emergency", GoalKind.EMERGENCY, Money.parse("1000"), Money.parse("200"), 1)
# Nov 12 2027 is the 30th biweekly paycheck from Oct 2 2026, the last before the deadline.
CAMERA = Goal(
    "camera", "Camera", GoalKind.PURCHASE, Money.parse("2000"), Money.zero(), 2, date(2027, 11, 20)
)

# Tiers 1-4 of the design doc's worked example; WORKED_EXAMPLE adds its camera.
STATE = FinancialState(
    available_balance=Money.zero(),
    income_sources=(JOB,),
    bills=(RENT,),
    essentials=(GROCERIES,),
    debts=(CAR,),
)
WORKED_EXAMPLE = replace(STATE, goals=(CAMERA,))


def plan(
    state: FinancialState = STATE,
    pay_date: date = date(2026, 10, 2),
    source: IncomeSource = JOB,
    actual: Money | None = None,
) -> PlanResult:
    paycheck = Paycheck(source.id, pay_date, source.expected_amount, actual)
    return plan_paycheck(state, paycheck, as_of=pay_date)


def lines(result: PlanResult) -> dict[tuple[Tier, str], tuple[str, str]]:
    """Allocations as {(tier, target): (requested, funded)} in dollars, for readable asserts."""
    return {(a.tier, a.target_id): (str(a.requested), str(a.funded)) for a in result.allocations}


# --- The worked example -----------------------------------------------------


def test_design_doc_worked_example() -> None:
    result = plan(WORKED_EXAMPLE)
    oct_20, zero = date(2026, 10, 20), Money.zero()
    assert result.allocations == (
        Allocation(
            Tier.BILL,
            "rent",
            Money.parse("400"),
            Money.parse("400"),
            Basis(Reason.BILL_DUE, "Rent", Money.parse("800"), zero, oct_20, paychecks=2),
        ),
        Allocation(
            Tier.ESSENTIAL,
            "groceries",
            Money.parse("200"),
            Money.parse("200"),
            Basis(Reason.ESSENTIAL, "Groceries", Money.parse("200"), zero, None, None, 14, 14),
        ),
        Allocation(
            Tier.DEBT_MINIMUM,
            "car",
            Money.parse("75"),
            Money.parse("75"),
            Basis(Reason.DEBT_MINIMUM, "Car loan", Money.parse("150"), zero, oct_20, 2),
        ),
        # $2,000 / 30 = $66.666..., rounded up so 30 paychecks always reach it.
        Allocation(
            Tier.GOAL,
            "camera",
            Money.parse("66.67"),
            Money.parse("66.67"),
            Basis(
                Reason.GOAL_DEADLINE, "Camera", Money.parse("2000"), zero, date(2027, 11, 20), 30
            ),
        ),
    )
    assert result.safe_to_spend == Money.parse("758.33")
    assert result.reserve_deficit == Money.zero()
    assert result.underfunded == ()
    assert result.next_pay_date == date(2026, 10, 16)
    assert result.as_of == date(2026, 10, 2)


# --- Bills ------------------------------------------------------------------


def test_payday_on_due_date_does_not_count_toward_the_bill() -> None:
    # Rent due Oct 16, a payday: only the Oct 2 paycheck counts, so it pays it all.
    state = replace(STATE, bills=(replace(RENT, recurrence=EveryNMonths(date(2026, 1, 16))),))
    assert lines(plan(state))[(Tier.BILL, "rent")] == ("$800.00", "$800.00")


def test_planning_on_the_due_date_funds_the_next_occurrence() -> None:
    # Planning Oct 16 with rent due Oct 16: next due is Nov 16, three paychecks away.
    state = replace(STATE, bills=(replace(RENT, recurrence=EveryNMonths(date(2026, 1, 16))),))
    result = plan(state, pay_date=date(2026, 10, 16))
    assert lines(result)[(Tier.BILL, "rent")] == ("$266.66", "$266.66")


def test_reserve_reduces_what_the_bill_needs() -> None:
    # Oct 16 is the last paycheck before the Oct 20 due date; $400 is already set aside.
    state = replace(
        STATE,
        available_balance=Money.parse("400"),
        reserves=(Reserve(ReserveKind.BILL, "rent", Money.parse("400")),),
    )
    result = plan(state, pay_date=date(2026, 10, 16))
    assert lines(result)[(Tier.BILL, "rent")] == ("$400.00", "$400.00")


def test_fully_reserved_bill_gets_no_line() -> None:
    state = replace(
        STATE,
        available_balance=Money.parse("800"),
        reserves=(Reserve(ReserveKind.BILL, "rent", Money.parse("800")),),
    )
    assert (Tier.BILL, "rent") not in lines(plan(state))


def test_past_one_time_bill_gets_no_line() -> None:
    old = Bill("old", "Old fee", Money.parse("50"), OneTime(date(2026, 9, 1)), priority=1)
    assert (Tier.BILL, "old") not in lines(plan(replace(STATE, bills=(RENT, old))))


def test_yearly_bill_is_saved_for_across_every_paycheck_before_it() -> None:
    # 13 biweekly paychecks from Oct 2 2026 up to Mar 20 2027.
    insurance = Bill(
        "insurance", "Insurance", Money.parse("1200"), EveryNMonths(date(2027, 3, 20), 12), 2
    )
    result = plan(replace(STATE, bills=(insurance,)))
    assert lines(result)[(Tier.BILL, "insurance")] == ("$92.30", "$92.30")


def test_bills_are_funded_by_priority_and_the_money_runs_out() -> None:
    phone = Bill("phone", "Phone", Money.parse("100"), OneTime(date(2026, 10, 10)), priority=2)
    state = replace(STATE, bills=(phone, RENT))
    result = plan(state, actual=Money.parse("450"))
    assert [(a.tier, a.target_id) for a in result.allocations] == [
        (Tier.BILL, "rent"),  # priority 1 first, though phone is due sooner
        (Tier.BILL, "phone"),
        (Tier.ESSENTIAL, "groceries"),
        (Tier.DEBT_MINIMUM, "car"),
    ]
    assert lines(result) == {
        (Tier.BILL, "rent"): ("$400.00", "$400.00"),
        (Tier.BILL, "phone"): ("$100.00", "$50.00"),  # partly funded where money ran out
        (Tier.ESSENTIAL, "groceries"): ("$200.00", "$0.00"),
        (Tier.DEBT_MINIMUM, "car"): ("$75.00", "$0.00"),
    }
    assert result.safe_to_spend == Money.zero()
    assert [a.target_id for a in result.underfunded] == ["phone", "groceries", "car"]


# --- Essentials -------------------------------------------------------------


def test_two_jobs_prorate_essentials_by_days_until_next_paycheck() -> None:
    state = replace(STATE, income_sources=(JOB, SIDE))
    # Side job pays Thu Oct 1; the job pays the next day: 1 day of a 14-day period.
    assert lines(plan(state, date(2026, 10, 1), SIDE))[(Tier.ESSENTIAL, "groceries")] == (
        "$14.29",  # $200 x 1/14 = $14.2857, rounded up
        "$14.29",
    )


def test_two_paychecks_on_one_day_fund_essentials_once() -> None:
    # Essentials only: otherwise rent, due Oct 20, would claim the small side paycheck.
    state = replace(STATE, income_sources=(JOB, SIDE), bills=(), debts=())
    # Both pay Fri Oct 16. "job" sorts first, so its next paycheck is "side", 0 days later.
    assert (Tier.ESSENTIAL, "groceries") not in lines(plan(state, date(2026, 10, 16), JOB))
    # "side" then covers the 14 days to Oct 30.
    side_result = plan(state, date(2026, 10, 16), SIDE)
    assert lines(side_result)[(Tier.ESSENTIAL, "groceries")] == ("$200.00", "$200.00")
    assert side_result.next_pay_date == date(2026, 10, 30)


def test_two_jobs_split_bills_across_all_paychecks_before_due() -> None:
    # Before Oct 20: this Oct 2 paycheck, then job and side on Oct 16.
    state = replace(STATE, income_sources=(JOB, SIDE))
    assert lines(plan(state))[(Tier.BILL, "rent")] == ("$266.66", "$266.66")


# --- Debt minimums ----------------------------------------------------------


def test_debt_minimum_is_capped_at_the_balance() -> None:
    state = replace(STATE, debts=(replace(CAR, balance=Money.parse("50")),))
    assert lines(plan(state))[(Tier.DEBT_MINIMUM, "car")] == ("$25.00", "$25.00")


def test_paid_off_or_reserved_debt_gets_no_line() -> None:
    paid_off = replace(STATE, debts=(replace(CAR, balance=Money.zero()),))
    assert (Tier.DEBT_MINIMUM, "car") not in lines(plan(paid_off))
    reserved = replace(
        STATE,
        available_balance=Money.parse("150"),
        reserves=(Reserve(ReserveKind.DEBT, "car", Money.parse("150")),),
    )
    assert (Tier.DEBT_MINIMUM, "car") not in lines(plan(reserved))


# --- Emergency fund ---------------------------------------------------------


def test_emergency_fund_takes_what_it_still_needs() -> None:
    result = plan(replace(STATE, goals=(EMERGENCY,)))
    assert lines(result)[(Tier.EMERGENCY_FUND, "ef")] == ("$800.00", "$800.00")
    assert result.safe_to_spend == Money.parse("25")


def test_emergency_fund_is_partly_funded_when_money_is_short() -> None:
    result = plan(replace(STATE, goals=(EMERGENCY,)), actual=Money.parse("1000"))
    assert lines(result)[(Tier.EMERGENCY_FUND, "ef")] == ("$800.00", "$325.00")
    assert result.safe_to_spend == Money.zero()


def test_no_or_full_emergency_goal_gets_no_line() -> None:
    assert all(a.tier is not Tier.EMERGENCY_FUND for a in plan().allocations)
    full = replace(EMERGENCY, current=Money.parse("1200"))
    assert all(
        a.tier is not Tier.EMERGENCY_FUND for a in plan(replace(STATE, goals=(full,))).allocations
    )


# --- Goals with a deadline -------------------------------------------------


def goal(
    goal_id: str, priority: int, deadline: date | None, target: str = "600", current: str = "0"
) -> Goal:
    return Goal(
        goal_id,
        goal_id.title(),
        GoalKind.SAVINGS,
        Money.parse(target),
        Money.parse(current),
        priority,
        deadline,
    )


def test_goal_share_is_rounded_up() -> None:
    # $100 over the 3 paychecks before Nov 1 (Oct 2, 16, 30): $33.34, not $33.33.
    state = replace(STATE, goals=(goal("trip", 1, date(2026, 11, 1), target="100"),))
    assert lines(plan(state))[(Tier.GOAL, "trip")] == ("$33.34", "$33.34")


def test_goal_progress_reduces_what_it_needs() -> None:
    state = replace(STATE, goals=(goal("trip", 1, date(2026, 11, 1), current="300"),))
    assert lines(plan(state))[(Tier.GOAL, "trip")] == ("$100.00", "$100.00")


def test_reached_goal_gets_no_line() -> None:
    state = replace(STATE, goals=(goal("trip", 1, date(2026, 11, 1), current="700"),))
    assert all(a.tier is not Tier.GOAL for a in plan(state).allocations)


def test_payday_on_the_deadline_does_not_count_toward_the_goal() -> None:
    # Deadline Oct 30, a payday: only Oct 2 and Oct 16 count.
    state = replace(STATE, goals=(goal("trip", 1, date(2026, 10, 30)),))
    assert lines(plan(state))[(Tier.GOAL, "trip")] == ("$300.00", "$300.00")


def test_goals_are_funded_by_priority_then_deadline() -> None:
    goals = (
        goal("later", 1, date(2027, 1, 1)),
        goal("low", 2, date(2026, 10, 10)),
        goal("sooner", 1, date(2026, 11, 1)),
    )
    result = plan(replace(STATE, goals=(*goals, EMERGENCY)))
    tier_order = [
        (a.tier, a.target_id)
        for a in result.allocations
        if a.tier in (Tier.EMERGENCY_FUND, Tier.GOAL)
    ]
    assert tier_order == [
        (Tier.EMERGENCY_FUND, "ef"),  # the emergency goal is tier 4, never tier 5
        (Tier.GOAL, "sooner"),
        (Tier.GOAL, "later"),
        (Tier.GOAL, "low"),
    ]


def test_goal_is_partly_funded_when_money_is_short() -> None:
    state = replace(STATE, goals=(goal("trip", 1, date(2026, 10, 10), target="1000"),))
    assert lines(plan(state))[(Tier.GOAL, "trip")] == ("$1,000.00", "$825.00")
    assert plan(state).safe_to_spend == Money.zero()


# --- Goals with no deadline: a share of what is left -------------------------
# STATE leaves $825 after tiers 1-4, so the default 20% share is $165.


def test_goal_with_no_deadline_gets_a_share_of_what_is_left() -> None:
    result = plan(replace(STATE, goals=(goal("trip", 1, None),)))
    assert lines(result)[(Tier.GOAL, "trip")] == ("$165.00", "$165.00")
    assert result.safe_to_spend == Money.parse("660")


def test_share_comes_after_every_goal_with_a_deadline() -> None:
    # $758.33 left after the camera; 20% is $151.666..., rounded up. Priority 1 still waits.
    result = plan(replace(WORKED_EXAMPLE, goals=(CAMERA, goal("trip", 1, None))))
    assert [a.target_id for a in result.allocations][-2:] == ["camera", "trip"]
    assert lines(result)[(Tier.GOAL, "trip")] == ("$151.67", "$151.67")
    assert result.safe_to_spend == Money.parse("606.66")


def test_share_goes_by_priority_then_evenly_and_never_past_a_goals_need() -> None:
    goals = (
        goal("a", 2, None),
        goal("b", 2, None, target="20"),  # fills at $20; its unused part goes to "a"
        goal("top", 1, None, target="50"),
        goal("c", 3, None),  # nothing left for priority 3
    )
    result = plan(replace(STATE, goals=goals))
    assert [a.target_id for a in result.allocations if a.tier is Tier.GOAL] == ["top", "a", "b"]
    assert lines(result)[(Tier.GOAL, "top")] == ("$50.00", "$50.00")
    assert lines(result)[(Tier.GOAL, "a")] == ("$95.00", "$95.00")
    assert lines(result)[(Tier.GOAL, "b")] == ("$20.00", "$20.00")
    assert result.safe_to_spend == Money.parse("660")


def test_share_left_over_after_every_goal_is_full_stays_safe_to_spend() -> None:
    result = plan(replace(STATE, goals=(goal("trip", 1, None, target="40"),)))
    assert result.safe_to_spend == Money.parse("785")


def test_share_size_is_a_setting() -> None:
    goals = (goal("trip", 1, None, target="5000"),)
    none = plan(replace(STATE, goals=goals, no_deadline_goal_share_bps=0))
    assert all(a.tier is not Tier.GOAL for a in none.allocations)
    everything = plan(replace(STATE, goals=goals, no_deadline_goal_share_bps=10_000))
    assert lines(everything)[(Tier.GOAL, "trip")] == ("$825.00", "$825.00")
    assert everything.safe_to_spend == Money.zero()


def test_share_is_nothing_when_the_money_ran_out() -> None:
    result = plan(replace(STATE, goals=(goal("trip", 1, None),)), actual=Money.parse("500"))
    assert all(a.tier is not Tier.GOAL for a in result.allocations)


def test_goal_whose_deadline_has_passed_shares_the_leftover() -> None:
    # Before as_of, or on this payday: no paycheck can reach it, so it waits for a new date.
    for deadline in (date(2026, 9, 1), date(2026, 10, 2)):
        result = plan(replace(STATE, goals=(goal("trip", 1, deadline),)))
        assert lines(result)[(Tier.GOAL, "trip")] == ("$165.00", "$165.00")
    # Planning Oct 16 ahead of time on Oct 2: an Oct 10 deadline comes before the paycheck.
    state = replace(STATE, goals=(goal("trip", 1, date(2026, 10, 10)),))
    paycheck = Paycheck("job", date(2026, 10, 16), Money.parse("1500"))
    ahead = plan_paycheck(state, paycheck, as_of=date(2026, 10, 2))
    # Oct 16 pays all of rent ($800) and the car minimum ($150): $350 left, 20% is $70.
    assert lines(ahead)[(Tier.GOAL, "trip")] == ("$70.00", "$70.00")


# --- Projected completion dates ---------------------------------------------


def projection(result: PlanResult, goal_id: str) -> GoalProjection:
    return next(p for p in result.goal_projections if p.goal_id == goal_id)


def test_worked_example_camera_is_on_track() -> None:
    camera = projection(plan(WORKED_EXAMPLE), "camera")
    assert camera.contribution == Money.parse("66.67")
    assert camera.still_needed == Money.parse("1933.33")
    # 30 x $66.67 reaches $2,000 on the 30th paycheck, Nov 12 2027.
    assert camera.projected_date == date(2027, 11, 12)
    assert camera.status is GoalStatus.ON_TRACK
    assert camera.suggested_deadline is None


def test_goal_finished_by_this_paycheck_is_complete_today() -> None:
    ef = projection(plan(replace(STATE, goals=(EMERGENCY,))), "ef")
    assert (ef.contribution, ef.still_needed) == (Money.parse("800"), Money.zero())
    assert ef.projected_date == date(2026, 10, 2)
    assert ef.status is GoalStatus.COMPLETE


def test_goal_already_reached_is_complete_with_no_date() -> None:
    reached = projection(
        plan(replace(STATE, goals=(goal("trip", 1, None, current="600"),))), "trip"
    )
    assert reached.contribution == Money.zero()
    assert reached.projected_date is None
    assert reached.status is GoalStatus.COMPLETE


def test_underfunded_goal_is_behind_and_gets_a_suggested_date() -> None:
    # Needs $1,000 by Oct 10 but gets $825: at that rate it finishes Oct 16.
    state = replace(STATE, goals=(goal("trip", 1, date(2026, 10, 10), target="1000"),))
    trip = projection(plan(state), "trip")
    assert trip.projected_date == date(2026, 10, 16)
    assert trip.status is GoalStatus.BEHIND
    assert trip.suggested_deadline == date(2026, 10, 16)


def test_goal_with_no_deadline_projects_at_its_share() -> None:
    # $600 at $165 a paycheck: the 4th paycheck, Nov 13.
    trip = projection(plan(replace(STATE, goals=(goal("trip", 1, None),))), "trip")
    assert trip.projected_date == date(2026, 11, 13)
    assert trip.status is GoalStatus.NO_DEADLINE
    assert trip.suggested_deadline is None


def test_passed_deadline_is_flagged_with_a_suggested_date() -> None:
    trip = projection(plan(replace(STATE, goals=(goal("trip", 1, date(2026, 9, 1)),))), "trip")
    assert trip.status is GoalStatus.DEADLINE_PASSED
    assert trip.suggested_deadline == date(2026, 11, 13)


def test_goal_with_no_contribution_has_no_projected_date() -> None:
    state = replace(STATE, goals=(goal("trip", 1, date(2027, 1, 1)),))
    trip = projection(plan(state, actual=Money.parse("500")), "trip")
    assert trip.contribution == Money.zero()
    assert trip.projected_date is None
    assert trip.status is GoalStatus.BEHIND
    assert trip.suggested_deadline is None


def test_goal_more_than_ten_years_away_has_no_projected_date() -> None:
    # $165 a paycheck toward $1,000,000 is about 233 years.
    state = replace(STATE, goals=(goal("house", 1, None, target="1000000"),))
    house = projection(plan(state), "house")
    assert house.contribution == Money.parse("165")
    assert house.projected_date is None


def test_every_goal_gets_a_projection_in_state_order() -> None:
    goals = (goal("b", 2, None), EMERGENCY, goal("a", 1, date(2027, 1, 1)))
    result = plan(replace(STATE, goals=goals))
    assert [p.goal_id for p in result.goal_projections] == ["b", "ef", "a"]
    assert plan().goal_projections == ()


# --- Money in, Safe to Spend out --------------------------------------------


def test_unreserved_balance_is_planned_too() -> None:
    result = plan(replace(STATE, available_balance=Money.parse("300")))
    assert result.safe_to_spend == Money.parse("1125")


def test_actual_amount_replaces_expected() -> None:
    assert plan(actual=Money.parse("1200")).safe_to_spend == Money.parse("525")


def test_reserves_beyond_the_money_on_hand_fund_nothing() -> None:
    state = replace(
        STATE,
        available_balance=Money.parse("200"),
        reserves=(Reserve(ReserveKind.BILL, "rent", Money.parse("2000")),),
    )
    result = plan(state)
    assert result.reserve_deficit == Money.parse("300")  # 2000 - (200 + 1500)
    assert result.safe_to_spend == Money.zero()
    assert all(a.funded == Money.zero() for a in result.allocations)


# --- Reason codes -----------------------------------------------------------


def basis(result: PlanResult, tier: Tier, target_id: str) -> Basis:
    return next(a.basis for a in result.allocations if (a.tier, a.target_id) == (tier, target_id))


def test_bill_basis_records_what_was_already_set_aside() -> None:
    state = replace(
        STATE,
        available_balance=Money.parse("300"),
        reserves=(Reserve(ReserveKind.BILL, "rent", Money.parse("300")),),
    )
    rent = basis(plan(state), Tier.BILL, "rent")
    assert (rent.reason, rent.total, rent.set_aside) == (
        Reason.BILL_DUE,
        Money.parse("800"),
        Money.parse("300"),
    )


def test_essential_covering_part_of_a_period_is_prorated() -> None:
    state = replace(STATE, income_sources=(JOB, SIDE))
    groceries = basis(plan(state, date(2026, 10, 1), SIDE), Tier.ESSENTIAL, "groceries")
    assert groceries.reason is Reason.ESSENTIAL_PRORATED
    assert (groceries.days_covered, groceries.days_in_period) == (1, 14)


def test_debt_minimum_capped_at_the_balance_is_a_payoff() -> None:
    state = replace(STATE, debts=(replace(CAR, balance=Money.parse("50")),))
    car = basis(plan(state), Tier.DEBT_MINIMUM, "car")
    assert (car.reason, car.total) == (Reason.DEBT_PAYOFF, Money.parse("50"))


def test_emergency_fund_basis_records_progress() -> None:
    ef = basis(plan(replace(STATE, goals=(EMERGENCY,))), Tier.EMERGENCY_FUND, "ef")
    assert (ef.reason, ef.total, ef.set_aside) == (
        Reason.EMERGENCY_FUND,
        Money.parse("1000"),
        Money.parse("200"),
    )


def test_leftover_goals_record_why_they_share_the_leftover() -> None:
    goals = (goal("open", 1, None), goal("late", 1, date(2026, 9, 1)))
    result = plan(replace(STATE, goals=goals, no_deadline_goal_share_bps=1500))
    open_goal, late = basis(result, Tier.GOAL, "open"), basis(result, Tier.GOAL, "late")
    assert (open_goal.reason, open_goal.due, open_goal.share_bps) == (
        Reason.GOAL_NO_DEADLINE,
        None,
        1500,
    )
    assert (late.reason, late.due, late.share_bps) == (
        Reason.GOAL_DEADLINE_PASSED,
        date(2026, 9, 1),
        1500,
    )


def test_reason_values_are_stable_strings() -> None:
    assert [reason.value for reason in Reason] == [
        "bill_due",
        "essential",
        "essential_prorated",
        "debt_minimum",
        "debt_payoff",
        "emergency_fund",
        "goal_deadline",
        "goal_no_deadline",
        "goal_deadline_passed",
    ]


# --- Validation and result helpers ------------------------------------------


def test_paycheck_from_unknown_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown income source"):
        plan(source=SIDE)


def test_as_of_must_be_a_plain_date() -> None:
    paycheck = Paycheck("job", date(2026, 10, 2), Money.parse("1500"))
    with pytest.raises(TypeError):
        plan_paycheck(STATE, paycheck, as_of=datetime(2026, 10, 2))  # type: ignore[arg-type]


def test_allocation_shortfall() -> None:
    basis = Basis(Reason.BILL_DUE, "Rent", Money.parse("100"))
    allocation = Allocation(Tier.BILL, "rent", Money.parse("100"), Money.parse("40"), basis)
    assert allocation.reason is Reason.BILL_DUE
    assert allocation.shortfall == Money.parse("60")
    assert allocation.is_underfunded
    assert not replace(allocation, funded=Money.parse("100")).is_underfunded


def test_tier_values_are_stable_strings() -> None:
    # Stored with each plan's allocations; changing them is a migration.
    assert [tier.value for tier in Tier] == [
        "bill",
        "essential",
        "debt_minimum",
        "emergency_fund",
        "goal",
    ]


def test_goal_status_values_are_stable_strings() -> None:
    assert [status.value for status in GoalStatus] == [
        "complete",
        "on_track",
        "behind",
        "no_deadline",
        "deadline_passed",
    ]


def test_longest_gap_between_paydays_is_33_days() -> None:
    # Found by Hypothesis: Monthly(4) pays Fri Oct 2 (Sun Oct 4 rolled back), then Wed Nov 4.
    monthly = IncomeSource("job", "Job", Monthly(4), Money.parse("1500"))
    result = plan(replace(STATE, income_sources=(monthly,)), source=monthly)
    assert result.next_pay_date == date(2026, 11, 4)
    assert lines(result)[(Tier.ESSENTIAL, "groceries")] == ("$200.00", "$200.00")
