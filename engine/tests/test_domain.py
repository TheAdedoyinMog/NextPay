from dataclasses import replace
from datetime import date, datetime
from typing import Any

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
    paycheck_timeline,
)
from nextpay_engine.money import Money
from nextpay_engine.pay_schedules import Biweekly, SemiMonthly
from nextpay_engine.recurrence import EveryNMonths, OneTime


def dollars(text: str) -> Money:
    return Money.parse(text)


JOB = IncomeSource(
    id="job",
    name="Coffee shop",
    schedule=Biweekly(anchor=date(2026, 10, 2)),
    expected_amount=dollars("1500"),
)
RENT = Bill(
    id="rent",
    name="Rent",
    amount=dollars("800"),
    recurrence=EveryNMonths(first_due=date(2026, 1, 31)),
    priority=1,
)
GROCERIES = EssentialExpense(id="groceries", name="Groceries", amount_per_period=dollars("200"))
CAR = Debt(
    id="car",
    name="Car loan",
    balance=dollars("9000"),
    apr_bps=699,
    minimum_payment=dollars("150"),
    due_day=31,
)
CAMERA = Goal(
    id="camera",
    name="Camera",
    kind=GoalKind.PURCHASE,
    target=dollars("2000"),
    current=Money.zero(),
    priority=2,
    deadline=date(2027, 12, 1),
)
PAYCHECK = Paycheck(source_id="job", pay_date=date(2026, 10, 2), expected_amount=dollars("1500"))
RESERVE = Reserve(kind=ReserveKind.BILL, target_id="rent", amount=dollars("400"))

VALID_OBJECTS: list[Any] = [JOB, RENT, GROCERIES, CAR, CAMERA, PAYCHECK, RESERVE]


def rejects(obj: Any, error: type[Exception], **changes: object) -> None:
    """Assert that copying ``obj`` with ``changes`` fails validation with ``error``."""
    with pytest.raises(error):
        replace(obj, **changes)


# --- Shared behaviour -------------------------------------------------------


@pytest.mark.parametrize("obj", VALID_OBJECTS)
def test_valid_objects_are_immutable_and_hashable(obj: Any) -> None:
    field = next(iter(obj.__dataclass_fields__))
    with pytest.raises(AttributeError):
        setattr(obj, field, "changed")
    assert hash(obj) == hash(replace(obj))


@pytest.mark.parametrize("obj", [JOB, RENT, GROCERIES, CAR, CAMERA])
@pytest.mark.parametrize("field", ["id", "name"])
def test_id_and_name_must_be_non_blank(obj: Any, field: str) -> None:
    rejects(obj, ValueError, **{field: ""})
    rejects(obj, ValueError, **{field: "   "})
    rejects(obj, TypeError, **{field: 7})


@pytest.mark.parametrize(
    ("obj", "field"),
    [
        (JOB, "expected_amount"),
        (PAYCHECK, "expected_amount"),
        (RENT, "amount"),
        (GROCERIES, "amount_per_period"),
        (CAMERA, "target"),
    ],
)
def test_amounts_that_must_be_positive(obj: Any, field: str) -> None:
    rejects(obj, ValueError, **{field: Money.zero()})
    rejects(obj, ValueError, **{field: Money(-1)})
    rejects(obj, TypeError, **{field: 1500})
    rejects(obj, TypeError, **{field: 15.0})


@pytest.mark.parametrize(
    ("obj", "field"),
    [
        (PAYCHECK, "actual_amount"),
        (CAR, "balance"),
        (CAR, "minimum_payment"),
        (CAMERA, "current"),
        (RESERVE, "amount"),
    ],
)
def test_amounts_that_must_not_be_negative(obj: Any, field: str) -> None:
    assert getattr(replace(obj, **{field: Money.zero()}), field) == Money.zero()
    rejects(obj, ValueError, **{field: Money(-1)})
    rejects(obj, TypeError, **{field: 0})


@pytest.mark.parametrize("obj", [RENT, CAMERA])
@pytest.mark.parametrize("priority", [0, -1, True, 1.0])
def test_priority_must_be_int_at_least_one(obj: Any, priority: object) -> None:
    rejects(obj, ValueError, priority=priority)


# --- IncomeSource -----------------------------------------------------------


def test_income_source_generates_expected_paychecks() -> None:
    assert JOB.paychecks_between(date(2026, 10, 1), date(2026, 10, 31)) == (
        Paycheck("job", date(2026, 10, 2), dollars("1500")),
        Paycheck("job", date(2026, 10, 16), dollars("1500")),
        Paycheck("job", date(2026, 10, 30), dollars("1500")),
    )


# --- Paycheck ---------------------------------------------------------------


def test_paycheck_amount_is_expected_until_actual_recorded() -> None:
    assert PAYCHECK.actual_amount is None
    assert PAYCHECK.amount == dollars("1500")


def test_paycheck_amount_uses_actual_when_recorded() -> None:
    smaller = replace(PAYCHECK, actual_amount=dollars("1320.50"))
    assert smaller.amount == dollars("1320.50")
    assert replace(PAYCHECK, actual_amount=Money.zero()).amount == Money.zero()


def test_paycheck_date_must_be_plain_date() -> None:
    rejects(PAYCHECK, TypeError, pay_date=datetime(2026, 10, 2))


# --- Bill -------------------------------------------------------------------


def test_bill_delegates_due_dates_to_recurrence() -> None:
    assert RENT.due_dates_between(date(2026, 2, 1), date(2026, 3, 31)) == (
        date(2026, 2, 28),
        date(2026, 3, 31),
    )


def test_one_time_bill() -> None:
    bill = replace(RENT, recurrence=OneTime(due=date(2026, 12, 5)))
    assert bill.due_dates_between(date(2026, 12, 1), date(2026, 12, 31)) == (date(2026, 12, 5),)


# --- Debt -------------------------------------------------------------------


def test_debt_due_dates_clamp_to_month_end() -> None:
    assert CAR.due_dates_between(date(2026, 1, 1), date(2026, 4, 30)) == (
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    )


def test_debt_due_dates_respect_partial_months() -> None:
    debt = replace(CAR, due_day=15)
    assert debt.due_dates_between(date(2026, 1, 16), date(2026, 3, 14)) == (date(2026, 2, 15),)


def test_debt_due_dates_reject_bad_range() -> None:
    with pytest.raises(ValueError):
        CAR.due_dates_between(date(2026, 2, 1), date(2026, 1, 1))


def test_paid_off_debt_is_valid() -> None:
    assert replace(CAR, balance=Money.zero(), minimum_payment=Money.zero()).balance.is_zero()


@pytest.mark.parametrize("apr_bps", [-1, True, 6.99, "699"])
def test_debt_rejects_bad_apr(apr_bps: object) -> None:
    rejects(CAR, ValueError, apr_bps=apr_bps)


def test_debt_allows_zero_apr() -> None:
    assert replace(CAR, apr_bps=0).apr_bps == 0


@pytest.mark.parametrize("due_day", [0, 32])
def test_debt_rejects_bad_due_day(due_day: int) -> None:
    rejects(CAR, ValueError, due_day=due_day)


# --- Goal -------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(GoalKind))
def test_goal_accepts_every_kind(kind: GoalKind) -> None:
    assert replace(CAMERA, kind=kind).kind is kind


def test_goal_rejects_kind_as_plain_string() -> None:
    rejects(CAMERA, TypeError, kind="purchase")


def test_goal_deadline_is_optional() -> None:
    assert replace(CAMERA, deadline=None).deadline is None


def test_goal_deadline_must_be_plain_date() -> None:
    rejects(CAMERA, TypeError, deadline=datetime(2027, 12, 1))


def test_goal_current_may_exceed_target() -> None:
    assert replace(CAMERA, current=dollars("2500")).current == dollars("2500")


# --- Reserve ----------------------------------------------------------------


@pytest.mark.parametrize("kind", list(ReserveKind))
def test_reserve_accepts_every_kind(kind: ReserveKind) -> None:
    assert replace(RESERVE, kind=kind).kind is kind


def test_reserve_rejects_kind_as_plain_string() -> None:
    rejects(RESERVE, TypeError, kind="bill")


def test_reserve_target_id_must_be_non_blank() -> None:
    rejects(RESERVE, ValueError, target_id="")


def test_enum_values_are_stable_strings() -> None:
    # These values are stored by the backend; changing them is a migration.
    assert [k.value for k in GoalKind] == ["emergency", "savings", "purchase"]
    assert [k.value for k in ReserveKind] == ["bill", "goal", "debt"]


# --- Paycheck timeline ------------------------------------------------------


def test_timeline_merges_two_jobs_by_date_then_source() -> None:
    side_job = IncomeSource(
        id="a-side-job",
        name="Tutoring",
        schedule=SemiMonthly(first_day=1, second_day=16),
        expected_amount=dollars("300"),
    )
    assert paycheck_timeline([JOB, side_job], date(2026, 10, 1), date(2026, 10, 20)) == (
        Paycheck("a-side-job", date(2026, 10, 1), dollars("300")),
        Paycheck("job", date(2026, 10, 2), dollars("1500")),
        # Oct 16 2026 is a Friday: both pay that day, ordered by source id.
        Paycheck("a-side-job", date(2026, 10, 16), dollars("300")),
        Paycheck("job", date(2026, 10, 16), dollars("1500")),
    )


def test_timeline_with_no_sources_is_empty() -> None:
    assert paycheck_timeline([], date(2026, 10, 1), date(2026, 10, 31)) == ()


def test_timeline_rejects_duplicate_source_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        paycheck_timeline([JOB, JOB], date(2026, 10, 1), date(2026, 10, 31))


def test_timeline_rejects_bad_range_even_with_no_sources() -> None:
    with pytest.raises(ValueError):
        paycheck_timeline([], date(2026, 10, 31), date(2026, 10, 1))


# --- Next due date ----------------------------------------------------------


def test_bill_next_due_after_delegates() -> None:
    assert RENT.next_due_after(date(2026, 2, 1)) == date(2026, 2, 28)
    one_time = replace(RENT, recurrence=OneTime(due=date(2026, 1, 5)))
    assert one_time.next_due_after(date(2026, 2, 1)) is None


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 2, 10), date(2026, 2, 28)),  # due_day 31 clamps in February
        (date(2026, 2, 28), date(2026, 3, 31)),  # on the due date: next month
        (date(2026, 12, 31), date(2027, 1, 31)),  # across year end
    ],
)
def test_debt_next_due_after(day: date, expected: date) -> None:
    assert CAR.next_due_after(day) == expected


def test_debt_next_due_after_rejects_datetime() -> None:
    with pytest.raises(TypeError):
        CAR.next_due_after(datetime(2026, 1, 1))  # type: ignore[arg-type]
