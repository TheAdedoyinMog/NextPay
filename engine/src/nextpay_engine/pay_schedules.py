"""Pay schedules: when an income source pays.

Each schedule is a small frozen dataclass with one method, ``dates_between``.
Adding a frequency means adding one class that satisfies ``PaySchedule``.

A payday that falls on a weekend moves to the Friday before it (holidays are not
considered). Ranges are filtered on that adjusted date, the day the money arrives.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from nextpay_engine.dates import (
    clamped_date,
    months_spanning,
    previous_business_day,
    require_date,
    require_day_of_month,
    require_range,
)

# A weekend payday moves back at most two days, so a nominal payday up to two
# days after the range can still land inside it.
_MAX_ROLLBACK = timedelta(days=2)

# Consecutive semi-monthly paydays must be at least this far apart, so clamping
# and weekend rollback can never put two paychecks on the same date.
_MIN_SEMI_MONTHLY_GAP = 7


class PaySchedule(Protocol):
    def dates_between(self, start: date, end: date) -> tuple[date, ...]:
        """Paydays from ``start`` to ``end`` inclusive, sorted ascending."""
        ...


@dataclass(frozen=True, slots=True)
class Weekly:
    """Paid every 7 days, in step with ``anchor`` (any real payday, past or future)."""

    anchor: date

    def __post_init__(self) -> None:
        require_date(self.anchor, "anchor")

    def dates_between(self, start: date, end: date) -> tuple[date, ...]:
        require_range(start, end)
        return _settle(_every_n_days(self.anchor, 7, start, end + _MAX_ROLLBACK), start, end)


@dataclass(frozen=True, slots=True)
class Biweekly:
    """Paid every 14 days, in step with ``anchor`` (any real payday, past or future)."""

    anchor: date

    def __post_init__(self) -> None:
        require_date(self.anchor, "anchor")

    def dates_between(self, start: date, end: date) -> tuple[date, ...]:
        require_range(start, end)
        return _settle(_every_n_days(self.anchor, 14, start, end + _MAX_ROLLBACK), start, end)


@dataclass(frozen=True, slots=True)
class SemiMonthly:
    """Paid twice a month on two days of the month, e.g. the 15th and the 31st.

    A day past the end of a month means the month's last day. Consecutive paydays
    must be at least 7 days apart in every month, including from the second payday
    to the next month's first: (1, 15) and (15, 31) are fine, (1, 31) is not.
    """

    first_day: int
    second_day: int

    def __post_init__(self) -> None:
        require_day_of_month(self.first_day, "first_day")
        require_day_of_month(self.second_day, "second_day")
        # A 28-day February is the tightest month for both gaps: clamping pulls the
        # second payday closest to the first, and the month ends soonest after it.
        second_in_february = min(self.second_day, 28)
        within_month = second_in_february - self.first_day
        into_next_month = 28 - second_in_february + self.first_day
        if min(within_month, into_next_month) < _MIN_SEMI_MONTHLY_GAP:
            raise ValueError(
                f"paydays must be at least {_MIN_SEMI_MONTHLY_GAP} days apart in every month, "
                f"including into the next month; got days {self.first_day} and {self.second_day}"
            )

    def dates_between(self, start: date, end: date) -> tuple[date, ...]:
        require_range(start, end)
        nominal = (
            clamped_date(year, month, day)
            for year, month in months_spanning(start, end + _MAX_ROLLBACK)
            for day in (self.first_day, self.second_day)
        )
        return _settle(nominal, start, end)


@dataclass(frozen=True, slots=True)
class Monthly:
    """Paid once a month on ``day``; a day past the end of a month means its last day."""

    day: int

    def __post_init__(self) -> None:
        require_day_of_month(self.day, "day")

    def dates_between(self, start: date, end: date) -> tuple[date, ...]:
        require_range(start, end)
        nominal = (
            clamped_date(year, month, self.day)
            for year, month in months_spanning(start, end + _MAX_ROLLBACK)
        )
        return _settle(nominal, start, end)


def _every_n_days(anchor: date, days: int, start: date, end: date) -> Iterator[date]:
    """Dates ``anchor + k * days`` (any integer k) from ``start`` to ``end``."""
    steps_to_start = -(-(start - anchor).days // days)  # ceiling division
    current = anchor + timedelta(days=steps_to_start * days)
    while current <= end:
        yield current
        current += timedelta(days=days)


def _settle(nominal: Iterable[date], start: date, end: date) -> tuple[date, ...]:
    """Move weekend paydays to Friday and keep those that land in the range.

    ``nominal`` must be ascending; rollback never reorders paydays at least
    three days apart.
    """
    paydays = (previous_business_day(day) for day in nominal)
    return tuple(day for day in paydays if start <= day <= end)
