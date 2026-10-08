from datetime import date, datetime

import pytest

from nextpay_engine.pay_schedules import Biweekly, Monthly, PaySchedule, SemiMonthly, Weekly

# --- Weekly -----------------------------------------------------------------


def test_weekly_from_friday_anchor() -> None:
    schedule = Weekly(anchor=date(2026, 10, 2))
    assert schedule.dates_between(date(2026, 10, 1), date(2026, 10, 31)) == (
        date(2026, 10, 2),
        date(2026, 10, 9),
        date(2026, 10, 16),
        date(2026, 10, 23),
        date(2026, 10, 30),
    )


def test_weekly_saturday_anchor_pays_on_fridays() -> None:
    # Oct 3 2026 is a Saturday; every payday moves to the Friday before.
    schedule = Weekly(anchor=date(2026, 10, 3))
    assert schedule.dates_between(date(2026, 10, 1), date(2026, 10, 9)) == (
        date(2026, 10, 2),
        date(2026, 10, 9),
    )


def test_weekend_payday_just_after_range_rolls_into_it() -> None:
    # Oct 31 2026 is a Saturday, paid Friday Oct 30, the last day of the range.
    schedule = Weekly(anchor=date(2026, 10, 3))
    assert schedule.dates_between(date(2026, 10, 30), date(2026, 10, 30)) == (date(2026, 10, 30),)


# --- Biweekly ---------------------------------------------------------------


def test_biweekly_after_anchor() -> None:
    schedule = Biweekly(anchor=date(2026, 10, 2))
    assert schedule.dates_between(date(2026, 10, 1), date(2026, 11, 30)) == (
        date(2026, 10, 2),
        date(2026, 10, 16),
        date(2026, 10, 30),
        date(2026, 11, 13),
        date(2026, 11, 27),
    )


def test_biweekly_before_anchor_keeps_the_cycle() -> None:
    schedule = Biweekly(anchor=date(2026, 10, 2))
    assert schedule.dates_between(date(2026, 9, 1), date(2026, 9, 30)) == (
        date(2026, 9, 4),
        date(2026, 9, 18),
    )


def test_biweekly_range_between_paydays_is_empty() -> None:
    schedule = Biweekly(anchor=date(2026, 10, 2))
    assert schedule.dates_between(date(2026, 10, 3), date(2026, 10, 15)) == ()


def test_biweekly_single_day_range_on_payday() -> None:
    schedule = Biweekly(anchor=date(2026, 10, 2))
    assert schedule.dates_between(date(2026, 10, 16), date(2026, 10, 16)) == (date(2026, 10, 16),)


# --- Semi-monthly -----------------------------------------------------------


def test_semi_monthly_15th_and_last_day_with_weekend() -> None:
    # May 15 2026 is a Friday; May 31 is a Sunday, paid Friday May 29.
    schedule = SemiMonthly(first_day=15, second_day=31)
    assert schedule.dates_between(date(2026, 5, 1), date(2026, 5, 31)) == (
        date(2026, 5, 15),
        date(2026, 5, 29),
    )


def test_semi_monthly_leap_february() -> None:
    schedule = SemiMonthly(first_day=15, second_day=31)
    assert schedule.dates_between(date(2028, 2, 1), date(2028, 2, 29)) == (
        date(2028, 2, 15),
        date(2028, 2, 29),
    )


def test_semi_monthly_non_leap_february_clamps_then_rolls_back() -> None:
    # Feb 28 2027 is a Sunday, paid Friday Feb 26.
    schedule = SemiMonthly(first_day=15, second_day=31)
    assert schedule.dates_between(date(2027, 2, 1), date(2027, 2, 28)) == (
        date(2027, 2, 15),
        date(2027, 2, 26),
    )


@pytest.mark.parametrize(("first", "second"), [(1, 15), (15, 31), (5, 20), (10, 25), (1, 22)])
def test_semi_monthly_accepts_common_schedules(first: int, second: int) -> None:
    assert SemiMonthly(first_day=first, second_day=second).second_day == second


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (15, 15),
        (20, 15),
        (25, 31),  # 3 days apart in February
        (22, 31),  # 6 days apart in February
        (1, 30),  # Mar 30 to Apr 1 is 2 days
        (1, 31),  # the 31st to the 1st is 1 day
        (0, 15),
        (15, 32),
        (1.0, 15),
    ],
)
def test_semi_monthly_rejects_bad_days(first: object, second: object) -> None:
    with pytest.raises(ValueError):
        SemiMonthly(first_day=first, second_day=second)  # type: ignore[arg-type]


# --- Monthly ----------------------------------------------------------------


def test_monthly_on_31st_clamps_and_rolls_back() -> None:
    # Jan 31 2026 and Feb 28 2026 are Saturdays.
    schedule = Monthly(day=31)
    assert schedule.dates_between(date(2026, 1, 1), date(2026, 4, 30)) == (
        date(2026, 1, 30),
        date(2026, 2, 27),
        date(2026, 3, 31),
        date(2026, 4, 30),
    )


def test_monthly_saturday_first_is_paid_in_previous_month() -> None:
    # Aug 1 2026 is a Saturday, so it is paid Friday Jul 31.
    schedule = Monthly(day=1)
    assert schedule.dates_between(date(2026, 7, 1), date(2026, 7, 31)) == (
        date(2026, 7, 1),
        date(2026, 7, 31),
    )
    # ...and August has no payday at all.
    assert schedule.dates_between(date(2026, 8, 1), date(2026, 8, 31)) == ()


def test_monthly_across_year_end() -> None:
    schedule = Monthly(day=15)
    assert schedule.dates_between(date(2026, 12, 1), date(2027, 1, 31)) == (
        date(2026, 12, 15),
        date(2027, 1, 15),
    )


@pytest.mark.parametrize("day", [0, 32, True])
def test_monthly_rejects_bad_day(day: object) -> None:
    with pytest.raises(ValueError):
        Monthly(day=day)  # type: ignore[arg-type]


# --- Shared behaviour -------------------------------------------------------

ALL_SCHEDULES: list[PaySchedule] = [
    Weekly(date(2026, 10, 2)),
    Biweekly(date(2026, 10, 2)),
    SemiMonthly(1, 15),
    Monthly(1),
]


@pytest.mark.parametrize("schedule", ALL_SCHEDULES)
def test_rejects_inverted_range(schedule: PaySchedule) -> None:
    with pytest.raises(ValueError):
        schedule.dates_between(date(2026, 2, 1), date(2026, 1, 1))


@pytest.mark.parametrize("schedule", ALL_SCHEDULES)
def test_rejects_datetime_range(schedule: PaySchedule) -> None:
    with pytest.raises(TypeError):
        schedule.dates_between(datetime(2026, 1, 1), date(2026, 2, 1))  # type: ignore[arg-type]


@pytest.mark.parametrize("cls", [Weekly, Biweekly])
def test_anchor_must_be_a_date(cls: type[Weekly] | type[Biweekly]) -> None:
    with pytest.raises(TypeError):
        cls(anchor=datetime(2026, 10, 2))


def test_schedules_are_immutable_and_hashable() -> None:
    schedule = Monthly(15)
    with pytest.raises(AttributeError):
        schedule.day = 1  # type: ignore[misc]
    assert hash(Monthly(15)) == hash(Monthly(15))


def test_semi_monthly_regression_month_end_and_next_first_never_collide() -> None:
    # Found by Hypothesis: (1, 30) paid Fri Mar 30 2001 twice, because Sun Apr 1
    # rolled back onto it. Such schedules are now rejected; (1, 15) is safe.
    assert SemiMonthly(1, 15).dates_between(date(2001, 3, 1), date(2001, 4, 30)) == (
        date(2001, 3, 1),
        date(2001, 3, 15),
        date(2001, 3, 30),  # Sun Apr 1 -> Fri Mar 30
        date(2001, 4, 13),  # Sun Apr 15 -> Fri Apr 13
    )
