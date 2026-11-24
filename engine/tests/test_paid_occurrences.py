"""Occurrences already paid are not reserved for again (ADR 0018).

The worked examples are the ADR's, with the same numbers: a biweekly paycheck on
Fridays Nov 6, Nov 20, Dec 4, Dec 18 and Jan 1.
"""

from dataclasses import replace
from datetime import date

import pytest

from nextpay_engine.domain import (
    Bill,
    Debt,
    IncomeSource,
    Paycheck,
    Payment,
    PaymentKind,
    Reserve,
    ReserveKind,
)
from nextpay_engine.explanations import explain_allocation
from nextpay_engine.money import Money
from nextpay_engine.pay_schedules import Biweekly
from nextpay_engine.planning import Allocation, PlanResult, Reason, plan_paycheck
from nextpay_engine.recurrence import EveryNMonths, OneTime
from nextpay_engine.state import FinancialState

JOB = IncomeSource("job", "Job", Biweekly(date(2026, 11, 6)), Money.parse("2000"))
CAR = Debt("car", "Car loan", Money.parse("3000"), 699, Money.parse("150"), due_day=25)
PHONE = Bill("phone", "Phone", Money.parse("90"), EveryNMonths(date(2026, 1, 10)), priority=1)
CARD = Debt("card", "Card", Money.parse("900"), 2499, Money.parse("35"), due_day=15)
GYM = Bill("gym", "Gym", Money.parse("60"), EveryNMonths(date(2026, 1, 25)), priority=2)

NOV_6, NOV_20, DEC_4 = date(2026, 11, 6), date(2026, 11, 20), date(2026, 12, 4)
NOV_22 = date(2026, 11, 22)


def state(**changes: object) -> FinancialState:
    base = FinancialState(available_balance=Money.parse("500"), income_sources=(JOB,))
    return replace(base, **changes)  # type: ignore[arg-type]


def plan(financial_state: FinancialState, pay_date: date) -> PlanResult:
    paycheck = Paycheck(JOB.id, pay_date, JOB.expected_amount)
    return plan_paycheck(financial_state, paycheck, as_of=NOV_22)


def line(result: PlanResult, target_id: str) -> Allocation:
    (found,) = (a for a in result.allocations if a.target_id == target_id)
    return found


def has_line(result: PlanResult, target_id: str) -> bool:
    return any(a.target_id == target_id for a in result.allocations)


def car_payment(due: date, amount: str = "150", paid_on: date = NOV_22) -> Payment:
    return Payment(PaymentKind.DEBT, "car", due, paid_on, Money.parse(amount))


# --- A. A debt paid early, then the payment undone ---------------------------


def test_example_a_the_nov_6_plan_reserves_half_the_nov_25_minimum() -> None:
    result = plan(state(debts=(CAR,)), NOV_6)
    car = line(result, "car")
    assert (car.requested, car.basis.due, car.basis.paychecks) == (
        Money.parse("75"),
        date(2026, 11, 25),
        2,
    )


def test_example_a_an_early_payment_moves_the_next_plan_on_to_december() -> None:
    # After "Mark paid" on Nov 22: the $75 reserve was drawn, the balance fell by $150.
    paid = state(
        debts=(replace(CAR, balance=Money.parse("2850")),),
        payments=(car_payment(date(2026, 11, 25)),),
    )
    car = line(plan(paid, NOV_20), "car")

    assert car.requested == Money.parse("50")
    assert (car.basis.due, car.basis.paychecks) == (date(2026, 12, 25), 3)
    assert (car.basis.paid_ahead, car.basis.paid_through, car.basis.paid_ahead_on) == (
        1,
        date(2026, 11, 25),
        NOV_22,
    )
    assert explain_allocation(car, plan(paid, NOV_20)) == (
        "We reserved $50 toward Car loan because the $150 minimum payment is due Dec 25 and "
        "is split across the 3 paychecks before then. "
        "The Nov 25 minimum payment was already paid on Nov 22."
    )


def test_example_a_without_the_payment_the_full_minimum_is_reserved_again() -> None:
    # What happened before ADR 0018: the reserve is gone and Nov 25 still looks unpaid.
    car = line(plan(state(debts=(replace(CAR, balance=Money.parse("2850")),)), NOV_20), "car")
    assert (car.requested, car.basis.due) == (Money.parse("150"), date(2026, 11, 25))


def test_example_a_after_undo_the_plan_is_as_if_nothing_was_paid() -> None:
    # Undo puts the $75 reserve and the $3,000 balance back, and the payment drops out.
    undone = state(debts=(CAR,), reserves=(Reserve(ReserveKind.DEBT, "car", Money.parse("75")),))
    result = plan(undone, NOV_20)
    car = line(result, "car")
    assert car.requested == Money.parse("75")
    assert explain_allocation(car, result) == (
        "We reserved $75 toward Car loan because the $150 minimum payment is due Nov 25; "
        "with $75 already set aside, the rest is due before your next paycheck."
    )


# --- B. A partial bill payment ---------------------------------------------


PHONE_PAYMENT = Payment(
    PaymentKind.BILL, "phone", date(2026, 12, 10), date(2026, 11, 21), Money.parse("40")
)


def test_example_b_a_partial_payment_lowers_what_is_still_needed() -> None:
    result = plan(state(bills=(PHONE,), payments=(PHONE_PAYMENT,)), NOV_20)
    phone = line(result, "phone")
    assert phone.requested == Money.parse("25")
    assert explain_allocation(phone, result) == (
        "We reserved $25 toward Phone because the $90 bill is due Dec 10; "
        "with $40 already paid on Nov 21, the rest is split across the 2 paychecks before then."
    )


def test_example_b_with_part_of_the_reserve_left_after_the_payment() -> None:
    # $45 was reserved; the $40 payment drew it down to $5.
    reserve = Reserve(ReserveKind.BILL, "phone", Money.parse("5"))
    result = plan(state(bills=(PHONE,), payments=(PHONE_PAYMENT,), reserves=(reserve,)), NOV_20)
    phone = line(result, "phone")
    assert phone.requested == Money.parse("22.50")
    assert explain_allocation(phone, result) == (
        "We reserved $22.50 toward Phone because the $90 bill is due Dec 10; "
        "with $40 already paid on Nov 21 and $5 set aside, the rest is split across the "
        "2 paychecks before then."
    )


# --- C. Extra principal ----------------------------------------------------


def test_example_c_paying_above_the_minimum_does_not_pay_next_month() -> None:
    payment = Payment(
        PaymentKind.DEBT, "card", date(2026, 12, 15), date(2026, 11, 21), Money.parse("300")
    )
    result = plan(state(debts=(CARD,), payments=(payment,)), DEC_4)
    card = line(result, "card")
    assert card.requested == Money.parse("11.66")
    assert (card.basis.total, card.basis.due, card.basis.paychecks) == (
        Money.parse("35"),
        date(2027, 1, 15),
        3,
    )
    assert card.basis.paid.is_zero()  # none of the extra $265 counts toward January
    assert explain_allocation(card, result) == (
        "We reserved $11.66 toward Card because the $35 minimum payment is due "
        "Jan 15, 2027 and is split across the 3 paychecks before then. "
        "The Dec 15 minimum payment was already paid on Nov 21."
    )


# --- Bills have no principal -----------------------------------------------


def test_overpaying_a_bill_covers_that_occurrence_only() -> None:
    # $70 on a $60 bill: Nov 25 is covered; the extra $10 does not count toward Dec 25.
    overpaid = Payment(PaymentKind.BILL, "gym", date(2026, 11, 25), NOV_22, Money.parse("70"))
    gym = line(plan(state(bills=(GYM,), payments=(overpaid,)), NOV_20), "gym")
    assert (gym.basis.due, gym.basis.paid, gym.basis.paid_ahead) == (
        date(2026, 12, 25),
        Money.zero(),
        1,
    )
    assert gym.requested == Money.parse("20")  # the full $60, over 3 paychecks


# --- Edges -----------------------------------------------------------------


def test_several_paid_occurrences_are_skipped_and_summed_up() -> None:
    paid = (car_payment(date(2026, 11, 25)), car_payment(date(2026, 12, 25)))
    result = plan(state(debts=(CAR,), payments=paid), NOV_20)
    car = line(result, "car")
    assert (car.basis.due, car.basis.paid_ahead) == (date(2027, 1, 25), 2)
    assert explain_allocation(car, result).endswith(
        " Everything due through Dec 25 was already paid, most recently on Nov 22."
    )


def test_two_partial_payments_together_cover_an_occurrence() -> None:
    paid = (
        car_payment(date(2026, 11, 25), "100", date(2026, 11, 10)),
        car_payment(date(2026, 11, 25), "50"),
    )
    car = line(plan(state(debts=(CAR,), payments=paid), NOV_20), "car")
    assert (car.basis.due, car.basis.paid_ahead_on) == (date(2026, 12, 25), NOV_22)


def test_a_partial_debt_payment_lowers_the_minimum_still_needed() -> None:
    result = plan(state(debts=(CAR,), payments=(car_payment(date(2026, 11, 25), "100"),)), NOV_20)
    car = line(result, "car")
    assert (car.requested, car.reason) == (Money.parse("50"), Reason.DEBT_MINIMUM)
    assert explain_allocation(car, result) == (
        "We reserved $50 toward Car loan because the $150 minimum payment is due Nov 25; "
        "with $100 already paid on Nov 22, the rest is due before your next paycheck."
    )


def test_paying_off_counts_the_balance_alone() -> None:
    # $100 paid toward Nov 25 left $30 owed, less than the $50 left of the minimum.
    nearly_paid = replace(CAR, balance=Money.parse("30"))
    paid = (car_payment(date(2026, 11, 25), "100"),)
    result = plan(state(debts=(nearly_paid,), payments=paid), NOV_20)
    car = line(result, "car")
    assert (car.requested, car.reason, car.basis.total) == (
        Money.parse("30"),
        Reason.DEBT_PAYOFF,
        Money.parse("30"),
    )
    assert explain_allocation(car, result) == (
        "We reserved $30 toward Car loan because the last $30 you owe is due Nov 25, "
        "before your next paycheck."
    )


def test_a_paid_off_debt_gets_no_line_even_after_an_early_payment() -> None:
    paid_off = replace(CAR, balance=Money.zero())
    paid = (car_payment(date(2026, 11, 25)),)
    assert not has_line(plan(state(debts=(paid_off,), payments=paid), NOV_20), "car")


def test_a_one_time_bill_paid_early_gets_no_line() -> None:
    deposit = Bill("deposit", "Deposit", Money.parse("200"), OneTime(date(2026, 12, 1)), 1)
    payment = Payment(PaymentKind.BILL, "deposit", date(2026, 12, 1), NOV_22, Money.parse("200"))
    assert has_line(plan(state(bills=(deposit,)), NOV_20), "deposit")
    assert not has_line(plan(state(bills=(deposit,), payments=(payment,)), NOV_20), "deposit")


def test_a_payment_that_is_not_on_a_due_date_changes_nothing() -> None:
    # The schedule was edited after the payment, so it pays no occurrence any more.
    orphan = car_payment(date(2026, 11, 24))
    assert plan(state(debts=(CAR,), payments=(orphan,)), NOV_20) == plan(
        state(debts=(CAR,)), NOV_20
    )


def test_a_payment_for_an_earlier_occurrence_changes_nothing() -> None:
    on_time = car_payment(date(2026, 10, 25), paid_on=date(2026, 10, 25))
    assert plan(state(debts=(CAR,), payments=(on_time,)), NOV_20) == plan(
        state(debts=(CAR,)), NOV_20
    )


def test_a_payment_for_a_later_occurrence_leaves_the_next_one_owed() -> None:
    # Paying December first does not pay November.
    car = line(
        plan(state(debts=(CAR,), payments=(car_payment(date(2026, 12, 25)),)), NOV_20), "car"
    )
    assert (car.basis.due, car.requested, car.basis.paid_ahead) == (
        date(2026, 11, 25),
        Money.parse("150"),
        0,
    )


# --- State and dates -------------------------------------------------------


def test_a_payment_must_point_at_a_known_bill_or_debt() -> None:
    with pytest.raises(ValueError, match="payment points at unknown debt 'car'"):
        state(payments=(car_payment(date(2026, 11, 25)),))
    with pytest.raises(ValueError, match="payment points at unknown bill 'car'"):
        state(
            debts=(CAR,),
            payments=(
                Payment(PaymentKind.BILL, "car", date(2026, 11, 25), NOV_22, Money.parse("1")),
            ),
        )


def test_a_payment_must_be_positive() -> None:
    with pytest.raises(ValueError, match="amount must be positive"):
        car_payment(date(2026, 11, 25), "0")


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 11, 22), date(2026, 11, 25)),
        (date(2026, 11, 25), date(2026, 11, 25)),
        (date(2026, 12, 10), date(2026, 11, 25)),  # tie: 15 days either way, earlier wins
        (date(2026, 12, 11), date(2026, 12, 25)),
        (date(2026, 12, 31), date(2026, 12, 25)),
    ],
)
def test_a_debt_payment_defaults_to_the_closest_due_date(day: date, expected: date) -> None:
    assert CAR.closest_due_date(day) == expected


def test_a_debt_due_on_the_31st_is_due_on_the_last_day_of_short_months() -> None:
    end_of_month = replace(CAR, due_day=31)
    assert end_of_month.is_due_date(date(2027, 2, 28))
    assert not end_of_month.is_due_date(date(2027, 3, 30))
    assert end_of_month.closest_due_date(date(2027, 3, 2)) == date(2027, 2, 28)


def test_a_bill_payment_defaults_to_the_closest_due_date() -> None:
    assert PHONE.closest_due_date(date(2026, 11, 22)) == date(2026, 11, 10)
    assert PHONE.closest_due_date(date(2026, 11, 26)) == date(2026, 12, 10)
    assert PHONE.closest_due_date(date(2026, 1, 1)) == date(2026, 1, 10)
    one_time = Bill("x", "X", Money.parse("1"), OneTime(date(2026, 5, 1)), 1)
    assert one_time.closest_due_date(date(2027, 1, 1)) == date(2026, 5, 1)
