"""Income sources: create, list, get, update, delete, each for one user (ADR 0005).

Paychecks and their plans are history, so a source that has paychecks is
archived when the user deletes it: it stops paying and can no longer be read
or planned for, but its history stays (ADR 0011).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from app.core.clock import Clock
from app.core.errors import InvalidInputError, NotFoundError
from app.models import IncomeSource, PayFrequency
from app.services.engine_mapping import to_engine_income_source, to_engine_schedule, validated
from app.services.protocols import OwnedStore, Transaction

_SEMI_MONTHLY_RULE = (
    "Pick two paydays at least 7 days apart in every month, counting from the second "
    "payday to the next month's first: the 1st and 15th work, the 1st and 31st don't."
)


@dataclass(frozen=True, slots=True)
class IncomeSourceInput:
    """Everything a user sets on an income source.

    Each frequency takes exactly its own parameters: weekly and biweekly take
    ``anchor_date``, monthly takes ``day_of_month``, and semi-monthly takes
    ``day_of_month`` and ``second_day_of_month``.
    """

    name: str
    expected_amount_cents: int
    pay_frequency: PayFrequency
    # Any real payday, past or future.
    anchor_date: date | None = None
    day_of_month: int | None = None
    second_day_of_month: int | None = None


class IncomeSourceStore(OwnedStore[IncomeSource], Protocol):
    """``get`` and ``list_for`` never return an archived source."""

    def delete_or_archive(self, row: IncomeSource, at: datetime) -> bool: ...


class IncomeSourceService:
    def __init__(
        self, *, income_sources: IncomeSourceStore, transaction: Transaction, clock: Clock
    ) -> None:
        self._income_sources = income_sources
        self._transaction = transaction
        self._clock = clock

    def create(self, user_id: uuid.UUID, data: IncomeSourceInput) -> IncomeSource:
        """Raises ``InvalidInputError``."""
        source = _checked(_fill(IncomeSource(id=uuid.uuid4(), user_id=user_id), data))
        self._income_sources.add(source)
        self._transaction.commit()
        return source

    def list_for(self, user_id: uuid.UUID) -> Sequence[IncomeSource]:
        return self._income_sources.list_for(user_id)

    def get(self, user_id: uuid.UUID, source_id: uuid.UUID) -> IncomeSource:
        """Raises ``NotFoundError``, also when the source is another user's."""
        source = self._income_sources.get(user_id, source_id)
        if source is None:
            raise NotFoundError()
        return source

    def update(
        self, user_id: uuid.UUID, source_id: uuid.UUID, data: IncomeSourceInput
    ) -> IncomeSource:
        """Replace every field. Raises ``NotFoundError`` or ``InvalidInputError``.

        Paychecks already recorded keep the amounts and dates they were given.
        """
        source = self.get(user_id, source_id)
        # Check a copy first, so a rejected update never touches the stored source.
        _checked(_fill(IncomeSource(id=source.id, user_id=user_id), data))
        _fill(source, data)
        self._transaction.commit()
        return source

    def delete(self, user_id: uuid.UUID, source_id: uuid.UUID) -> None:
        """Remove the source: deleted if it has no paychecks, archived if it has.

        Either way it is gone from this service afterwards. Raises ``NotFoundError``.
        """
        self._income_sources.delete_or_archive(self.get(user_id, source_id), self._clock())
        self._transaction.commit()


def _checked(source: IncomeSource) -> IncomeSource:
    if source.pay_frequency is PayFrequency.SEMI_MONTHLY:
        # The one rule a request schema cannot express, so it gets its own message.
        try:
            to_engine_schedule(source)
        except ValueError as error:
            raise InvalidInputError(_SEMI_MONTHLY_RULE) from error
    return validated(source, to_engine_income_source)


def _fill(source: IncomeSource, data: IncomeSourceInput) -> IncomeSource:
    source.name = data.name
    source.expected_amount_cents = data.expected_amount_cents
    source.pay_frequency = data.pay_frequency
    source.anchor_date = data.anchor_date
    source.day_of_month = data.day_of_month
    source.second_day_of_month = data.second_day_of_month
    return source
