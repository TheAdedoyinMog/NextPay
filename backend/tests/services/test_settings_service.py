"""SettingsService rules, and what "today" is for a user."""

from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.core.clock import is_timezone, local_date
from app.core.errors import InvalidInputError
from app.models import User
from app.services.settings import SettingsInput, SettingsService

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


@pytest.fixture
def settings_service(transaction: Fake) -> SettingsService:
    return SettingsService(transaction=transaction)


def new_user() -> User:
    return User(email="ada@example.com", timezone="UTC", no_deadline_goal_share_bps=2000)


def test_update_replaces_both_settings(
    settings_service: SettingsService, transaction: Fake
) -> None:
    user = new_user()
    updated = settings_service.update(user, SettingsInput("America/New_York", 3500))
    assert updated is user
    assert (user.timezone, user.no_deadline_goal_share_bps) == ("America/New_York", 3500)
    assert transaction.commits == 1


@pytest.mark.parametrize("share", [0, 10_000])
def test_the_share_may_be_nothing_or_everything(
    settings_service: SettingsService, share: int
) -> None:
    assert settings_service.update(new_user(), SettingsInput("UTC", share)).timezone == "UTC"


@pytest.mark.parametrize(
    "data",
    [
        SettingsInput("Mars/Olympus_Mons", 2000),
        SettingsInput("", 2000),
        SettingsInput("new york", 2000),
        SettingsInput("UTC", -1),
        SettingsInput("UTC", 10_001),
        SettingsInput("UTC", True),
    ],
)
def test_invalid_settings_change_nothing(
    settings_service: SettingsService, transaction: Fake, data: SettingsInput
) -> None:
    user = new_user()
    with pytest.raises(InvalidInputError):
        settings_service.update(user, data)
    assert (user.timezone, user.no_deadline_goal_share_bps) == ("UTC", 2000)
    assert transaction.commits == 0


def test_time_zones_are_iana_names() -> None:
    assert is_timezone("America/Los_Angeles") and is_timezone("UTC")
    assert not is_timezone("PST8") and not is_timezone("../etc/passwd")


def test_today_depends_on_where_the_user_is() -> None:
    # 03:30 UTC on Oct 8 is still the evening of Oct 7 in New York, and already Oct 8 in Tokyo.
    now = datetime(2026, 10, 8, 3, 30, tzinfo=UTC)
    assert local_date(now, "UTC") == date(2026, 10, 8)
    assert local_date(now, "America/New_York") == date(2026, 10, 7)
    assert local_date(now, "Asia/Tokyo") == date(2026, 10, 8)
    assert type(local_date(now, "UTC")) is date
