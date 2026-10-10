"""Bills: create, list, get, update, delete, each for one user.

Deleting a bill also deletes its payments and its reserve (the database
cascades), which releases the reserved money. Plans that mention the bill keep
its name and lose only the link (ADR 0010).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.core.errors import NotFoundError
from app.models import Bill
from app.services.engine_mapping import to_engine_bill, validated
from app.services.protocols import OwnedStore, Transaction


@dataclass(frozen=True, slots=True)
class BillInput:
    """Everything a user sets on a bill. Create and update both take all of it."""

    name: str
    amount_cents: int
    # 1 is the most important.
    priority: int
    first_due_date: date
    # None: due once, on first_due_date.
    repeat_every_months: int | None


class BillService:
    def __init__(self, *, bills: OwnedStore[Bill], transaction: Transaction) -> None:
        self._bills = bills
        self._transaction = transaction

    def create(self, user_id: uuid.UUID, data: BillInput) -> Bill:
        """Raises ``InvalidInputError``."""
        bill = validated(_fill(Bill(id=uuid.uuid4(), user_id=user_id), data), to_engine_bill)
        self._bills.add(bill)
        self._transaction.commit()
        return bill

    def list_for(self, user_id: uuid.UUID) -> Sequence[Bill]:
        return self._bills.list_for(user_id)

    def get(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> Bill:
        """Raises ``NotFoundError``, also when the bill is another user's."""
        bill = self._bills.get(user_id, bill_id)
        if bill is None:
            raise NotFoundError()
        return bill

    def update(self, user_id: uuid.UUID, bill_id: uuid.UUID, data: BillInput) -> Bill:
        """Replace every field. Raises ``NotFoundError`` or ``InvalidInputError``."""
        bill = self.get(user_id, bill_id)
        # Check a copy first, so a rejected update never touches the stored bill.
        validated(_fill(Bill(id=bill.id, user_id=user_id), data), to_engine_bill)
        _fill(bill, data)
        self._transaction.commit()
        return bill

    def delete(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> None:
        """Raises ``NotFoundError``."""
        self._bills.delete(self.get(user_id, bill_id))
        self._transaction.commit()


def _fill(bill: Bill, data: BillInput) -> Bill:
    bill.name = data.name
    bill.amount_cents = data.amount_cents
    bill.priority = data.priority
    bill.first_due_date = data.first_due_date
    bill.repeat_every_months = data.repeat_every_months
    return bill
