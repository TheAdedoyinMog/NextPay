"""A user's planning settings: their time zone and the leftover share for open-ended goals."""

from dataclasses import dataclass

from app.core.clock import is_timezone
from app.core.errors import InvalidInputError
from app.models import User
from app.services.protocols import Transaction

_BPS_WHOLE = 10_000


@dataclass(frozen=True, slots=True)
class SettingsInput:
    # IANA name, e.g. "America/New_York": decides what "today" is for this user.
    timezone: str
    # FinancialState.no_deadline_goal_share_bps: 2000 is 20%.
    no_deadline_goal_share_bps: int


class SettingsService:
    def __init__(self, *, transaction: Transaction) -> None:
        self._transaction = transaction

    def update(self, user: User, data: SettingsInput) -> User:
        """Replace ``user``'s settings. Raises ``InvalidInputError``."""
        if not is_timezone(data.timezone):
            raise InvalidInputError("Pick a time zone such as America/New_York.")
        share = data.no_deadline_goal_share_bps
        if type(share) is not int or not 0 <= share <= _BPS_WHOLE:
            raise InvalidInputError("The share for goals without a deadline must be 0% to 100%.")
        user.timezone = data.timezone
        user.no_deadline_goal_share_bps = share
        self._transaction.commit()
        return user
