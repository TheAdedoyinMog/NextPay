"""Bill recurrence: when a bill is due.

Each rule is a small frozen dataclass with one method, ``due_dates_between``.
Due dates never move off weekends: a due date is a due date.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from nextpay_engine.dates import add_months, clamped_date, require_date, require_range


class BillRecurrence(Protocol):
    def due_dates_between(self, start: date, end: date) -> tuple[date, ...]:
        """Due dates from ``start`` to ``end`` inclusive, sorted ascending."""
        ...

    def next_due_after(self, day: date) -> date | None:
        """The first due date strictly after ``day``, or None if there is none."""
        ...


@dataclass(frozen=True, slots=True)
class OneTime:
    """Due once, on ``due``."""

    due: date

    def __post_init__(self) -> None:
        require_date(self.due, "due")

    def due_dates_between(self, start: date, end: date) -> tuple[date, ...]:
        require_range(start, end)
        return (self.due,) if start <= self.due <= end else ()

    def next_due_after(self, day: date) -> date | None:
        require_date(day, "day")
        return self.due if self.due > day else None


@dataclass(frozen=True, slots=True)
class EveryNMonths:
    """Due every ``months`` months, starting on ``first_due``.

    ``months=1`` is monthly, 3 quarterly, 12 yearly. Every occurrence uses
    ``first_due``'s day of the month, moved to the month's last day when the month
    is shorter. Each one is computed from ``first_due``, so a bill first due on
    Jan 31 is due Feb 28, then Mar 31: it never drifts to the 28th. A yearly bill
    first due on Feb 29 is due Feb 28 in non-leap years. Nothing is due before
    ``first_due``.
    """

    first_due: date
    months: int = 1

    def __post_init__(self) -> None:
        require_date(self.first_due, "first_due")
        if type(self.months) is not int or self.months < 1:
            raise ValueError(f"months must be an int >= 1, got {self.months!r}")

    def due_dates_between(self, start: date, end: date) -> tuple[date, ...]:
        require_range(start, end)
        months_to_start = (start.year - self.first_due.year) * 12 + (
            start.month - self.first_due.month
        )
        # Begin at the last occurrence in or before start's month (or the first one).
        index = max(0, months_to_start // self.months)
        due_dates: list[date] = []
        while (day := self._occurrence(index)) <= end:
            if day >= start:
                due_dates.append(day)
            index += 1
        return tuple(due_dates)

    def next_due_after(self, day: date) -> date:
        require_date(day, "day")
        months_to_day = (day.year - self.first_due.year) * 12 + (day.month - self.first_due.month)
        index = max(0, months_to_day // self.months)
        # At most two steps: the occurrence in day's month may be on or before day.
        while (due := self._occurrence(index)) <= day:
            index += 1
        return due

    def _occurrence(self, index: int) -> date:
        year, month = add_months(self.first_due.year, self.first_due.month, index * self.months)
        return clamped_date(year, month, self.first_due.day)
