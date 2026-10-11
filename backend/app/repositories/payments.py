"""Storage for payments recorded against bills and debts."""

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.models import BillPayment, DebtPayment
from app.repositories.owned import UserOwnedRepository


class BillPaymentRepository(UserOwnedRepository[BillPayment]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BillPayment, order_by=(BillPayment.paid_on,))

    def list_for_bill(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> Sequence[BillPayment]:
        """One bill's payments, newest first."""
        return self._session.scalars(
            self._owned_by(user_id)
            .where(BillPayment.bill_id == bill_id)
            .order_by(
                BillPayment.paid_on.desc(), BillPayment.created_at.desc(), BillPayment.id.desc()
            )
        ).all()


class DebtPaymentRepository(UserOwnedRepository[DebtPayment]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DebtPayment, order_by=(DebtPayment.paid_on,))

    def list_for_debt(self, user_id: uuid.UUID, debt_id: uuid.UUID) -> Sequence[DebtPayment]:
        """One debt's payments, newest first."""
        return self._session.scalars(
            self._owned_by(user_id)
            .where(DebtPayment.debt_id == debt_id)
            .order_by(
                DebtPayment.paid_on.desc(), DebtPayment.created_at.desc(), DebtPayment.id.desc()
            )
        ).all()
