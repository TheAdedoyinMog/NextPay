"""Debts: create, list, get, update, delete, each for one user.

Deleting a debt also deletes its reserve (the database cascades), which
releases the reserved money. Plans that mention the debt keep its name and
lose only the link (ADR 0010).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.errors import NotFoundError
from app.models import Debt
from app.services.engine_mapping import to_engine_debt, validated
from app.services.protocols import OwnedStore, Transaction


@dataclass(frozen=True, slots=True)
class DebtInput:
    """Everything a user sets on a debt. Create and update both take all of it."""

    name: str
    balance_cents: int
    # Annual rate in basis points: 24.99% is 2499.
    apr_bps: int
    minimum_payment_cents: int
    # Day of the month the minimum is due; past a month's end means its last day.
    due_day: int


class DebtService:
    def __init__(self, *, debts: OwnedStore[Debt], transaction: Transaction) -> None:
        self._debts = debts
        self._transaction = transaction

    def create(self, user_id: uuid.UUID, data: DebtInput) -> Debt:
        """Raises ``InvalidInputError``."""
        debt = validated(_fill(Debt(id=uuid.uuid4(), user_id=user_id), data), to_engine_debt)
        self._debts.add(debt)
        self._transaction.commit()
        return debt

    def list_for(self, user_id: uuid.UUID) -> Sequence[Debt]:
        return self._debts.list_for(user_id)

    def get(self, user_id: uuid.UUID, debt_id: uuid.UUID) -> Debt:
        """Raises ``NotFoundError``, also when the debt is another user's."""
        debt = self._debts.get(user_id, debt_id)
        if debt is None:
            raise NotFoundError()
        return debt

    def update(self, user_id: uuid.UUID, debt_id: uuid.UUID, data: DebtInput) -> Debt:
        """Replace every field. Raises ``NotFoundError`` or ``InvalidInputError``."""
        debt = self.get(user_id, debt_id)
        # Check a copy first, so a rejected update never touches the stored debt.
        validated(_fill(Debt(id=debt.id, user_id=user_id), data), to_engine_debt)
        _fill(debt, data)
        self._transaction.commit()
        return debt

    def delete(self, user_id: uuid.UUID, debt_id: uuid.UUID) -> None:
        """Raises ``NotFoundError``."""
        self._debts.delete(self.get(user_id, debt_id))
        self._transaction.commit()


def _fill(debt: Debt, data: DebtInput) -> Debt:
    debt.name = data.name
    debt.balance_cents = data.balance_cents
    debt.apr_bps = data.apr_bps
    debt.minimum_payment_cents = data.minimum_payment_cents
    debt.due_day = data.due_day
    return debt
