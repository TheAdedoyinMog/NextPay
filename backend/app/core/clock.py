"""The current time, injected wherever it matters, so tests can control it."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, available_timezones

type Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def is_timezone(name: str) -> bool:
    """Whether ``name`` is an IANA time zone, such as "America/New_York"."""
    return name in available_timezones()


def local_date(now: datetime, timezone: str) -> date:
    """The calendar date at ``now`` in ``timezone``: what "today" is for a user there.

    The engine never reads the clock, so this is the ``as_of`` it is given.
    """
    return now.astimezone(ZoneInfo(timezone)).date()
