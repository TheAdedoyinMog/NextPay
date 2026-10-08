from datetime import date, datetime

import pytest

from nextpay_engine.recurrence import BillRecurrence, EveryNMonths, OneTime

# --- One-time ---------------------------------------------------------------


def test_one_time_inside_range() -> None:
    bill = OneTime(due=date(2026, 11, 3))
    assert bill.due_dates_between(date(2026, 11, 1), date(2026, 11, 30)) == (date(2026, 11, 3),)


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2026, 11, 4), date(2026, 11, 30)), (date(2026, 10, 1), date(2026, 11, 2))],
)
def test_one_time_outside_range(start: date, end: date) -> None:
    assert OneTime(due=date(2026, 11, 3)).due_dates_between(start, end) == ()


def test_one_time_on_range_edges() -> None:
    bill = OneTime(due=date(2026, 11, 3))
    assert bill.due_dates_between(date(2026, 11, 3), date(2026, 11, 3)) == (date(2026, 11, 3),)


# --- Every N months ---------------------------------------------------------


def test_monthly_on_31st_clamps_without_drift() -> None:
    bill = EveryNMonths(first_due=date(2026, 1, 31))
    assert bill.due_dates_between(date(2026, 1, 1), date(2026, 5, 31)) == (
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),  # back to the 31st, not stuck on the 28th
        date(2026, 4, 30),
        date(2026, 5, 31),
    )


def test_monthly_on_30th_in_leap_february() -> None:
    bill = EveryNMonths(first_due=date(2027, 12, 30))
    assert bill.due_dates_between(date(2028, 2, 1), date(2028, 3, 31)) == (
        date(2028, 2, 29),
        date(2028, 3, 30),
    )


def test_weekend_due_date_does_not_move() -> None:
    # Oct 31 2026 is a Saturday.
    bill = EveryNMonths(first_due=date(2026, 1, 31))
    assert bill.due_dates_between(date(2026, 10, 1), date(2026, 10, 31)) == (date(2026, 10, 31),)


def test_nothing_due_before_first_due() -> None:
    bill = EveryNMonths(first_due=date(2026, 6, 15))
    assert bill.due_dates_between(date(2026, 1, 1), date(2026, 7, 31)) == (
        date(2026, 6, 15),
        date(2026, 7, 15),
    )
    assert bill.due_dates_between(date(2026, 1, 1), date(2026, 6, 14)) == ()


def test_range_starting_mid_month_after_due_day() -> None:
    bill = EveryNMonths(first_due=date(2026, 1, 10))
    assert bill.due_dates_between(date(2026, 3, 11), date(2026, 5, 9)) == (date(2026, 4, 10),)


def test_quarterly() -> None:
    bill = EveryNMonths(first_due=date(2026, 1, 15), months=3)
    assert bill.due_dates_between(date(2026, 1, 1), date(2026, 12, 31)) == (
        date(2026, 1, 15),
        date(2026, 4, 15),
        date(2026, 7, 15),
        date(2026, 10, 15),
    )


def test_quarterly_far_after_first_due_stays_in_phase() -> None:
    bill = EveryNMonths(first_due=date(2026, 2, 1), months=3)
    assert bill.due_dates_between(date(2030, 1, 1), date(2030, 6, 30)) == (
        date(2030, 2, 1),
        date(2030, 5, 1),
    )


def test_yearly_on_leap_day() -> None:
    bill = EveryNMonths(first_due=date(2028, 2, 29), months=12)
    assert bill.due_dates_between(date(2028, 1, 1), date(2032, 12, 31)) == (
        date(2028, 2, 29),
        date(2029, 2, 28),
        date(2030, 2, 28),
        date(2031, 2, 28),
        date(2032, 2, 29),
    )


@pytest.mark.parametrize("months", [0, -1, True, 1.0])
def test_rejects_bad_interval(months: object) -> None:
    with pytest.raises(ValueError):
        EveryNMonths(first_due=date(2026, 1, 1), months=months)  # type: ignore[arg-type]


# --- Shared behaviour -------------------------------------------------------

ALL_RULES: list[BillRecurrence] = [OneTime(date(2026, 1, 1)), EveryNMonths(date(2026, 1, 1))]


@pytest.mark.parametrize("rule", ALL_RULES)
def test_rejects_inverted_range(rule: BillRecurrence) -> None:
    with pytest.raises(ValueError):
        rule.due_dates_between(date(2026, 2, 1), date(2026, 1, 1))


def test_dates_must_be_plain_dates() -> None:
    with pytest.raises(TypeError):
        OneTime(due=datetime(2026, 1, 1))
    with pytest.raises(TypeError):
        EveryNMonths(first_due=datetime(2026, 1, 1))


# --- Next due date ----------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 11, 2), date(2026, 11, 3)),
        (date(2026, 11, 3), None),  # strictly after: due today is not "next"
        (date(2026, 12, 1), None),
    ],
)
def test_one_time_next_due_after(day: date, expected: date | None) -> None:
    assert OneTime(due=date(2026, 11, 3)).next_due_after(day) == expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2025, 6, 1), date(2026, 1, 31)),  # before first_due
        (date(2026, 1, 30), date(2026, 1, 31)),
        (date(2026, 1, 31), date(2026, 2, 28)),  # on a due date: the next one
        (date(2026, 2, 28), date(2026, 3, 31)),  # no drift after clamping
        (date(2026, 12, 31), date(2027, 1, 31)),
    ],
)
def test_every_n_months_next_due_after(day: date, expected: date) -> None:
    assert EveryNMonths(first_due=date(2026, 1, 31)).next_due_after(day) == expected


def test_yearly_next_due_after_skips_whole_year() -> None:
    bill = EveryNMonths(first_due=date(2028, 2, 29), months=12)
    assert bill.next_due_after(date(2028, 2, 29)) == date(2029, 2, 28)
    assert bill.next_due_after(date(2029, 3, 1)) == date(2030, 2, 28)


@pytest.mark.parametrize("rule", ALL_RULES)
def test_next_due_after_rejects_datetime(rule: BillRecurrence) -> None:
    with pytest.raises(TypeError):
        rule.next_due_after(datetime(2026, 1, 1))  # type: ignore[arg-type]
