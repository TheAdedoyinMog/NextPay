"""Essential expenses: create, list, get, update, delete, each for one user.

Nothing hangs off an essential expense except plan history, which keeps its
name and loses only the link when it is deleted (ADR 0010).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.errors import NotFoundError
from app.models import EssentialExpense
from app.services.engine_mapping import to_engine_essential, validated
from app.services.protocols import OwnedStore, Transaction


@dataclass(frozen=True, slots=True)
class EssentialExpenseInput:
    """Everything a user sets on an essential expense."""

    name: str
    # Needed every pay period, e.g. groceries until the next paycheck.
    amount_per_period_cents: int


class EssentialExpenseService:
    def __init__(
        self, *, essentials: OwnedStore[EssentialExpense], transaction: Transaction
    ) -> None:
        self._essentials = essentials
        self._transaction = transaction

    def create(self, user_id: uuid.UUID, data: EssentialExpenseInput) -> EssentialExpense:
        """Raises ``InvalidInputError``."""
        essential = validated(
            _fill(EssentialExpense(id=uuid.uuid4(), user_id=user_id), data), to_engine_essential
        )
        self._essentials.add(essential)
        self._transaction.commit()
        return essential

    def list_for(self, user_id: uuid.UUID) -> Sequence[EssentialExpense]:
        return self._essentials.list_for(user_id)

    def get(self, user_id: uuid.UUID, essential_id: uuid.UUID) -> EssentialExpense:
        """Raises ``NotFoundError``, also when the expense is another user's."""
        essential = self._essentials.get(user_id, essential_id)
        if essential is None:
            raise NotFoundError()
        return essential

    def update(
        self, user_id: uuid.UUID, essential_id: uuid.UUID, data: EssentialExpenseInput
    ) -> EssentialExpense:
        """Replace every field. Raises ``NotFoundError`` or ``InvalidInputError``."""
        essential = self.get(user_id, essential_id)
        # Check a copy first, so a rejected update never touches the stored row.
        validated(
            _fill(EssentialExpense(id=essential.id, user_id=user_id), data), to_engine_essential
        )
        _fill(essential, data)
        self._transaction.commit()
        return essential

    def delete(self, user_id: uuid.UUID, essential_id: uuid.UUID) -> None:
        """Raises ``NotFoundError``."""
        self._essentials.delete(self.get(user_id, essential_id))
        self._transaction.commit()


def _fill(essential: EssentialExpense, data: EssentialExpenseInput) -> EssentialExpense:
    essential.name = data.name
    essential.amount_per_period_cents = data.amount_per_period_cents
    return essential
