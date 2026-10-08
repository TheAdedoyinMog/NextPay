"""Calendar helpers shared by pay schedules, bill recurrence, and debts.

Pure date math: nothing here reads the clock. Callers always pass dates in.
"""

import calendar
from collections.abc import Iterator
from datetime import date, timedelta

_SATURDAY = 5
_SUNDAY = 6


def require_date(value: object, name: str) -> None:
    """Raise ``TypeError`` unless ``value`` is a plain ``date``.

    ``datetime`` is a subclass of ``date``, so ``isinstance`` would accept it and
    comparisons against plain dates would later fail. Reject it up front.
    """
    if type(value) is not date:
        raise TypeError(f"{name} must be a date, got {type(value).__name__}")


def require_range(start: date, end: date) -> None:
    """Validate an inclusive date range: both plain dates and ``start <= end``."""
    require_date(start, "start")
    require_date(end, "end")
    if start > end:
        raise ValueError(f"start {start} is after end {end}")


def require_day_of_month(day: int, name: str) -> None:
    """Raise ``ValueError`` unless ``day`` is an int from 1 to 31."""
    if type(day) is not int or not 1 <= day <= 31:
        raise ValueError(f"{name} must be an int from 1 to 31, got {day!r}")


def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def clamped_date(year: int, month: int, day: int) -> date:
    """The given day of the month, moved to the month's last day if it is too large.

    A bill due on the 31st falls on Apr 30, Feb 28, or Feb 29 in a leap year.
    """
    return date(year, month, min(day, last_day_of_month(year, month)))


def add_months(year: int, month: int, count: int) -> tuple[int, int]:
    """The (year, month) that is ``count`` months after the given one."""
    index = year * 12 + (month - 1) + count
    return index // 12, index % 12 + 1


def months_spanning(start: date, end: date) -> Iterator[tuple[int, int]]:
    """Each (year, month) from ``start``'s month to ``end``'s month inclusive."""
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = add_months(year, month, 1)


def previous_business_day(day: date) -> date:
    """The same date on a weekday; the Friday before when it falls on a weekend.

    Holidays are not considered.
    """
    weekday = day.weekday()
    if weekday == _SATURDAY:
        return day - timedelta(days=1)
    if weekday == _SUNDAY:
        return day - timedelta(days=2)
    return day
