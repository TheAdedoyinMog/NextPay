from dataclasses import replace
from datetime import date

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
from nextpay_engine.explanations import explain_allocation, explain_plan, explain_projection
from nextpay_engine.money import Money
from nextpay_engine.pay_schedules import Biweekly, SemiMonthly
from nextpay_engine.planning import PlanResult, plan_paycheck
from nextpay_engine.recurrence import EveryNMonths, OneTime
from nextpay_engine.state import FinancialState

# Biweekly Fridays from Oct 2 2026; rent and the car minimum are due Oct 20.
JOB = IncomeSource("job", "Job", Biweekly(date(2026, 10, 2)), Money.parse("1500"))
SIDE = IncomeSource("side", "Tutoring", SemiMonthly(1, 16), Money.parse("300"))
RENT = Bill("rent", "Rent", Money.parse("800"), EveryNMonths(date(2026, 1, 20)), priority=1)
GROCERIES = EssentialExpense("groceries", "Groceries", Money.parse("200"))
CAR = Debt("car", "Car loan", Money.parse("9000"), 699, Money.parse("150"), due_day=20)
EMERGENCY = Goal("ef", "Emergency", GoalKind.EMERGENCY, Money.parse("1000"), Money.parse("200"), 1)
CAMERA = Goal(
    "camera", "Camera", GoalKind.PURCHASE, Money.parse("2000"), Money.zero(), 2, date(2027, 11, 20)
)
STATE = FinancialState(
    available_balance=Money.zero(),
    income_sources=(JOB,),
    bills=(RENT,),
    essentials=(GROCERIES,),
    debts=(CAR,),
)


def savings(goal_id: str, deadline: date | None, target: str = "600") -> Goal:
    name = goal_id.title()
    return Goal(goal_id, name, GoalKind.SAVINGS, Money.parse(target), Money.zero(), 1, deadline)


def plan(
    state: FinancialState,
    pay_date: date = date(2026, 10, 2),
    source: IncomeSource = JOB,
    actual: Money | None = None,
    as_of: date | None = None,
) -> PlanResult:
    paycheck = Paycheck(source.id, pay_date, source.expected_amount, actual)
    return plan_paycheck(state, paycheck, as_of=as_of or pay_date)


def explained(result: PlanResult) -> dict[str, str]:
    return {a.target_id: explain_allocation(a, result) for a in result.allocations}


def projected(result: PlanResult) -> dict[str, str]:
    return {p.goal_id: explain_projection(p, result) for p in result.goal_projections}


# --- Allocations ------------------------------------------------------------


def test_design_doc_worked_example() -> None:
    result = plan(replace(STATE, goals=(CAMERA,)))
    assert explained(result) == {
        "rent": "We reserved $400 toward Rent because the $800 bill is due Oct 20 "
        "and is split across the 2 paychecks before then.",
        "groceries": "We set aside $200 for Groceries to cover this pay period.",
        "car": "We reserved $75 toward Car loan because the $150 minimum payment is due "
        "Oct 20 and is split across the 2 paychecks before then.",
        "camera": "We put $66.67 toward Camera because its $2,000 is needed by Nov 20, 2027, "
        "split across the 30 paychecks before then.",
    }
    assert projected(result) == {
        "camera": "At $66.67 a paycheck, Camera will be reached by Nov 12, 2027, "
        "ahead of its deadline of Nov 20, 2027."
    }
    assert explain_plan(result) == "Safe to Spend is $758.33: what's left after everything above."


def test_bill_due_before_the_next_paycheck() -> None:
    result = plan(STATE, pay_date=date(2026, 10, 16))
    assert explained(result)["rent"] == (
        "We reserved $800 toward Rent because the $800 bill is due Oct 20, "
        "before your next paycheck."
    )


def test_reserved_money_is_mentioned() -> None:
    state = replace(
        STATE,
        available_balance=Money.parse("300"),
        reserves=(Reserve(ReserveKind.BILL, "rent", Money.parse("300")),),
    )
    assert explained(plan(state))["rent"] == (
        "We reserved $250 toward Rent because the $800 bill is due Oct 20; with $300 "
        "already set aside, the rest is split across the 2 paychecks before then."
    )
    on_due_week = plan(state, pay_date=date(2026, 10, 16))
    assert explained(on_due_week)["rent"] == (
        "We reserved $500 toward Rent because the $800 bill is due Oct 20; with $300 "
        "already set aside, the rest is due before your next paycheck."
    )


def test_prorated_essential() -> None:
    result = plan(replace(STATE, income_sources=(JOB, SIDE)), date(2026, 10, 1), SIDE)
    assert explained(result)["groceries"] == (
        "We set aside $14.29 for Groceries to cover the 1 day until your next paycheck, "
        "at $200 per 14-day pay period."
    )


def test_debt_payoff() -> None:
    result = plan(replace(STATE, debts=(replace(CAR, balance=Money.parse("50")),)))
    assert explained(result)["car"] == (
        "We reserved $25 toward Car loan because the last $50 you owe is due Oct 20 "
        "and is split across the 2 paychecks before then."
    )


def test_emergency_fund() -> None:
    result = plan(replace(STATE, goals=(EMERGENCY,)))
    assert explained(result)["ef"] == (
        "We put $800 toward Emergency to reach its $1,000 target ($200 saved so far)."
    )
    assert projected(result)["ef"] == "This paycheck finishes Emergency."


def test_goal_with_progress_names_what_is_still_needed() -> None:
    camera = replace(CAMERA, current=Money.parse("500"))
    assert explained(plan(replace(STATE, goals=(camera,))))["camera"] == (
        "We put $50 toward Camera because $1,500 of its $2,000 is still needed by "
        "Nov 20, 2027, split across the 30 paychecks before then."
    )


def test_goal_sharing_the_leftover() -> None:
    result = plan(replace(STATE, goals=(savings("trip", None),), no_deadline_goal_share_bps=1250))
    assert explained(result)["trip"] == (
        "We put $103.13 toward Trip as its share of the 12.5% of leftover money "
        "that goes to goals without a deadline."
    )


def test_goal_whose_deadline_passed() -> None:
    result = plan(replace(STATE, goals=(savings("trip", date(2026, 9, 1)),)))
    assert explained(result)["trip"] == (
        "We put $165 toward Trip as its share of the 20% of leftover money that goes to "
        "goals without a deadline, since its date (Sep 1) has passed."
    )
    assert projected(result)["trip"] == (
        "Trip's date (Sep 1) has passed. At $165 a paycheck it would be reached by Nov 13; "
        "consider that as its new date."
    )


def test_goal_deadline_before_a_paycheck_planned_ahead() -> None:
    state = replace(STATE, goals=(savings("trip", date(2026, 10, 10)),))
    result = plan(state, pay_date=date(2026, 10, 16), as_of=date(2026, 10, 2))
    assert explained(result)["trip"].endswith(
        "since its date (Oct 10) is too soon for this paycheck to help."
    )


def test_shortfalls() -> None:
    phone = Bill("phone", "Phone", Money.parse("100"), OneTime(date(2026, 10, 10)), priority=2)
    state = replace(STATE, bills=(phone, RENT), goals=(EMERGENCY,))
    result = plan(state, actual=Money.parse("450"))
    lines = explained(result)
    assert lines["phone"] == (
        "Phone needs $100 from this paycheck because the $100 bill is due Oct 10, before "
        "your next paycheck. Only $50 could be covered, so you're $50 short."
    )
    assert lines["groceries"] == (
        "Groceries needs $200 from this paycheck to cover this pay period. "
        "Nothing could be covered, so you're $200 short."
    )
    assert lines["ef"] == (
        "Emergency needs $800 from this paycheck to reach its $1,000 target ($200 saved so "
        "far). Nothing could go toward it this time, so it will take longer."
    )
    assert explain_plan(result) == (
        "Safe to Spend is $0: this paycheck can't cover everything, and 4 items are short. "
        "Bills not fully covered: Phone."
    )


# --- Projections ------------------------------------------------------------


def test_goal_behind_its_deadline_gets_a_suggested_date() -> None:
    result = plan(replace(STATE, goals=(savings("trip", date(2026, 10, 10), target="1000"),)))
    assert explained(result)["trip"].endswith(
        "Only $825 could go toward it this time, so it will take longer."
    )
    assert projected(result)["trip"] == (
        "At $825 a paycheck, Trip will be reached by Oct 16, which misses its deadline of "
        "Oct 10. Consider moving it to Oct 16."
    )
    assert explain_plan(result) == (
        "Safe to Spend is $0: this paycheck can't cover everything, and 1 item is short."
    )


def test_goal_with_nothing_this_paycheck() -> None:
    goals = (savings("trip", date(2027, 1, 1)), savings("open", None))
    result = plan(replace(STATE, goals=goals), actual=Money.parse("500"))
    assert projected(result) == {
        "trip": "Nothing went toward Trip this paycheck, so it will miss its deadline of "
        "Jan 1, 2027.",
        "open": "Nothing went toward Open this paycheck.",
    }


def test_goal_more_than_ten_years_away() -> None:
    result = plan(replace(STATE, goals=(savings("house", None, target="1000000"),)))
    assert projected(result)["house"] == "At $165 a paycheck, House is more than ten years away."


def test_goal_with_no_deadline_and_a_reached_goal() -> None:
    reached = replace(savings("done", None), current=Money.parse("600"))
    result = plan(replace(STATE, goals=(savings("trip", None), reached)))
    assert projected(result) == {
        "trip": "At $165 a paycheck, Trip will be reached by Nov 13.",
        "done": "Done is fully funded.",
    }


def test_passed_deadline_with_nothing_this_paycheck() -> None:
    result = plan(replace(STATE, goals=(savings("trip", date(2026, 9, 1)),)), actual=Money.zero())
    assert projected(result)["trip"] == (
        "Trip's date (Sep 1) has passed. Pick a new date to put it back on a schedule."
    )


# --- The plan ---------------------------------------------------------------


def test_plan_that_uses_the_whole_paycheck() -> None:
    result = plan(STATE, actual=Money.parse("675"))
    assert explain_plan(result) == "Safe to Spend is $0: everything above used the whole paycheck."


def test_reserve_deficit() -> None:
    state = replace(
        STATE,
        available_balance=Money.parse("200"),
        reserves=(Reserve(ReserveKind.BILL, "rent", Money.parse("2000")),),
    )
    assert explain_plan(plan(state)) == (
        "You've set aside $300 more than you have, so nothing could be planned from this "
        "paycheck. Check your balance and what's set aside."
    )
