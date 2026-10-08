"""Property tests for pay schedules, bill recurrence, and debt due dates."""

from datetime import date, timedelta
from itertools import pairwise

from hypothesis import given, reject
from hypothesis import strategies as st

from nextpay_engine.dates import last_day_of_month
from nextpay_engine.domain import Debt
from nextpay_engine.money import Money
from nextpay_engine.pay_schedules import Biweekly, Monthly, PaySchedule, SemiMonthly, Weekly
from nextpay_engine.recurrence import BillRecurrence, EveryNMonths, OneTime

dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31))
days_of_month = st.integers(min_value=1, max_value=31)


@st.composite
def ranges(draw: st.DrawFn, max_days: int = 800) -> tuple[date, date]:
    start = draw(dates)
    return start, start + timedelta(days=draw(st.integers(min_value=0, max_value=max_days)))


@st.composite
def semi_monthly(draw: st.DrawFn) -> SemiMonthly:
    first = draw(st.integers(min_value=1, max_value=21))
    second = draw(st.integers(min_value=first + 7, max_value=31))
    try:
        return SemiMonthly(first, second)
    except ValueError:
        reject()  # too close across the month boundary


pay_schedules: st.SearchStrategy[PaySchedule] = st.one_of(
    st.builds(Weekly, dates),
    st.builds(Biweekly, dates),
    semi_monthly(),
    st.builds(Monthly, days_of_month),
)
recurrences: st.SearchStrategy[BillRecurrence] = st.one_of(
    st.builds(OneTime, dates),
    st.builds(EveryNMonths, dates, st.integers(min_value=1, max_value=24)),
)
debts = st.builds(
    Debt,
    id=st.just("debt"),
    name=st.just("Debt"),
    balance=st.just(Money(100_000)),
    apr_bps=st.just(0),
    minimum_payment=st.just(Money(5_000)),
    due_day=days_of_month,
)


def assert_sorted_within(result: tuple[date, ...], start: date, end: date) -> None:
    assert all(start <= day <= end for day in result)
    assert list(result) == sorted(set(result)), "dates must be strictly ascending"


# --- Pay schedules ----------------------------------------------------------


@given(pay_schedules, ranges())
def test_paydays_are_weekdays_in_range_and_ascending(
    schedule: PaySchedule, span: tuple[date, date]
) -> None:
    result = schedule.dates_between(*span)
    assert_sorted_within(result, *span)
    assert all(day.weekday() < 5 for day in result)


@given(pay_schedules, ranges(), st.integers(min_value=0, max_value=800))
def test_paydays_are_additive_over_split_ranges(
    schedule: PaySchedule, span: tuple[date, date], cut: int
) -> None:
    start, end = span
    middle = min(start + timedelta(days=cut), end)
    left = schedule.dates_between(start, middle)
    right = schedule.dates_between(middle + timedelta(days=1), end) if middle < end else ()
    assert left + right == schedule.dates_between(start, end)


@given(dates, ranges())
def test_biweekly_gaps_stay_near_fourteen_days(anchor: date, span: tuple[date, date]) -> None:
    result = Biweekly(anchor).dates_between(*span)
    gaps = [(later - earlier).days for earlier, later in pairwise(result)]
    assert all(12 <= gap <= 16 for gap in gaps)


@given(dates, ranges())
def test_weekly_gaps_stay_near_seven_days(anchor: date, span: tuple[date, date]) -> None:
    result = Weekly(anchor).dates_between(*span)
    gaps = [(later - earlier).days for earlier, later in pairwise(result)]
    assert all(5 <= gap <= 9 for gap in gaps)


@given(days_of_month, dates)
def test_monthly_pays_once_per_month_over_a_year(day: int, start: date) -> None:
    # Any 12 consecutive months hold 11, 12, or 13 paydays: a rollback can pull
    # one payday across the boundary at either end.
    end = start + timedelta(days=364)
    assert 11 <= len(Monthly(day).dates_between(start, end)) <= 13


# --- Bill recurrence and debt due dates -------------------------------------


@given(recurrences, ranges())
def test_due_dates_are_in_range_and_ascending(
    rule: BillRecurrence, span: tuple[date, date]
) -> None:
    assert_sorted_within(rule.due_dates_between(*span), *span)


@given(recurrences, ranges(), st.integers(min_value=0, max_value=800))
def test_due_dates_are_additive_over_split_ranges(
    rule: BillRecurrence, span: tuple[date, date], cut: int
) -> None:
    start, end = span
    middle = min(start + timedelta(days=cut), end)
    left = rule.due_dates_between(start, middle)
    right = rule.due_dates_between(middle + timedelta(days=1), end) if middle < end else ()
    assert left + right == rule.due_dates_between(start, end)


@given(dates, st.integers(min_value=1, max_value=24), ranges())
def test_every_n_months_follows_the_anchor(
    first_due: date, months: int, span: tuple[date, date]
) -> None:
    for day in EveryNMonths(first_due, months).due_dates_between(*span):
        assert day >= first_due
        months_from_anchor = (day.year - first_due.year) * 12 + day.month - first_due.month
        assert months_from_anchor % months == 0
        # No drift: always the anchor's day, clamped to this month's length.
        assert day.day == min(first_due.day, last_day_of_month(day.year, day.month))


@given(dates, st.integers(min_value=0, max_value=36))
def test_monthly_bill_is_due_exactly_once_each_month(first_due: date, offset: int) -> None:
    year, month = divmod(first_due.year * 12 + first_due.month - 1 + offset, 12)
    month += 1
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day_of_month(year, month))
    assert len(EveryNMonths(first_due).due_dates_between(month_start, month_end)) == 1


@given(debts, ranges())
def test_debt_due_once_per_month_in_range(debt: Debt, span: tuple[date, date]) -> None:
    result = debt.due_dates_between(*span)
    assert_sorted_within(result, *span)
    assert len({(day.year, day.month) for day in result}) == len(result)
    assert all(
        day.day == min(debt.due_day, last_day_of_month(day.year, day.month)) for day in result
    )


@given(recurrences, dates)
def test_next_due_after_matches_due_dates(rule: BillRecurrence, day: date) -> None:
    # EveryNMonths here repeats at most every 24 months, well inside 800 days;
    # a OneTime bill may be due further out than the window, or already past.
    window_end = day + timedelta(days=800)
    upcoming = rule.due_dates_between(day + timedelta(days=1), window_end)
    result = rule.next_due_after(day)
    if upcoming:
        assert result == upcoming[0]
    else:
        assert result is None or result > window_end


@given(debts, dates)
def test_debt_next_due_after_matches_due_dates(debt: Debt, day: date) -> None:
    upcoming = debt.due_dates_between(day + timedelta(days=1), day + timedelta(days=62))
    assert debt.next_due_after(day) == upcoming[0]
