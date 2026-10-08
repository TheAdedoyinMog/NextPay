from datetime import date, datetime

import pytest

from nextpay_engine.dates import (
    add_months,
    clamped_date,
    last_day_of_month,
    months_spanning,
    previous_business_day,
    require_date,
    require_day_of_month,
    require_range,
)


def test_require_date_accepts_plain_date() -> None:
    require_date(date(2026, 1, 1), "d")


@pytest.mark.parametrize("bad", [datetime(2026, 1, 1), "2026-01-01", None, 20260101])
def test_require_date_rejects_non_dates(bad: object) -> None:
    with pytest.raises(TypeError, match="d must be a date"):
        require_date(bad, "d")


def test_require_range_allows_single_day() -> None:
    require_range(date(2026, 1, 1), date(2026, 1, 1))


def test_require_range_rejects_inverted() -> None:
    with pytest.raises(ValueError):
        require_range(date(2026, 1, 2), date(2026, 1, 1))


def test_require_range_rejects_datetime() -> None:
    with pytest.raises(TypeError):
        require_range(date(2026, 1, 1), datetime(2026, 2, 1))  # type: ignore[arg-type]


@pytest.mark.parametrize("day", [1, 15, 31])
def test_require_day_of_month_accepts(day: int) -> None:
    require_day_of_month(day, "day")


@pytest.mark.parametrize("day", [0, 32, -1, True, 1.0])
def test_require_day_of_month_rejects(day: object) -> None:
    with pytest.raises(ValueError):
        require_day_of_month(day, "day")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("year", "month", "last"),
    [(2026, 1, 31), (2026, 4, 30), (2026, 2, 28), (2028, 2, 29), (2100, 2, 28), (2000, 2, 29)],
)
def test_last_day_of_month(year: int, month: int, last: int) -> None:
    assert last_day_of_month(year, month) == last


@pytest.mark.parametrize(
    ("year", "month", "day", "expected"),
    [
        (2026, 1, 31, date(2026, 1, 31)),
        (2026, 4, 31, date(2026, 4, 30)),
        (2026, 2, 31, date(2026, 2, 28)),
        (2028, 2, 31, date(2028, 2, 29)),
        (2028, 2, 29, date(2028, 2, 29)),
        (2027, 2, 29, date(2027, 2, 28)),
        (2026, 6, 15, date(2026, 6, 15)),
    ],
)
def test_clamped_date(year: int, month: int, day: int, expected: date) -> None:
    assert clamped_date(year, month, day) == expected


@pytest.mark.parametrize(
    ("year", "month", "count", "expected"),
    [
        (2026, 1, 0, (2026, 1)),
        (2026, 1, 1, (2026, 2)),
        (2026, 12, 1, (2027, 1)),
        (2026, 11, 14, (2028, 1)),
        (2026, 1, -1, (2025, 12)),
        (2026, 3, 12, (2027, 3)),
    ],
)
def test_add_months(year: int, month: int, count: int, expected: tuple[int, int]) -> None:
    assert add_months(year, month, count) == expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 9), date(2026, 10, 9)),  # Friday stays
        (date(2026, 10, 5), date(2026, 10, 5)),  # Monday stays
        (date(2026, 10, 10), date(2026, 10, 9)),  # Saturday -> Friday
        (date(2026, 10, 11), date(2026, 10, 9)),  # Sunday -> Friday
        (date(2026, 8, 1), date(2026, 7, 31)),  # Saturday the 1st -> previous month
        (date(2028, 1, 1), date(2027, 12, 31)),  # Saturday New Year -> previous year
    ],
)
def test_previous_business_day(day: date, expected: date) -> None:
    assert previous_business_day(day) == expected


def test_months_spanning_crosses_year_end() -> None:
    assert list(months_spanning(date(2026, 11, 30), date(2027, 2, 1))) == [
        (2026, 11),
        (2026, 12),
        (2027, 1),
        (2027, 2),
    ]


def test_months_spanning_single_month() -> None:
    assert list(months_spanning(date(2026, 5, 3), date(2026, 5, 4))) == [(2026, 5)]
