"""Storage for payments recorded against bills and debts."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BillPayment, DebtPayment
from app.repositories.owned import UserOwnedRepository


class BillPaymentRepository(UserOwnedRepository[BillPayment]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BillPayment, order_by=(BillPayment.paid_on,))

    def list_for_bill(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> Sequence[BillPayment]:
        """One bill's payments that were not undone, newest first."""
        return self._session.scalars(
            self._owned_by(user_id)
            .where(BillPayment.bill_id == bill_id, BillPayment.undone_at.is_(None))
            .order_by(
                BillPayment.paid_on.desc(), BillPayment.created_at.desc(), BillPayment.id.desc()
            )
        ).all()

    def find_any_owner(self, payment_id: uuid.UUID) -> BillPayment | None:
        """The payment with this id, whoever owns it. Only for spotting a reused id:
        the caller must check the owner before returning it (ADR 0015)."""
        return self._session.get(BillPayment, payment_id)

    def unreserved_since(self, user_id: uuid.UUID, since: datetime) -> int:
        """Cents that payments recorded at or after ``since``, and not undone, paid beyond
        their reserves."""
        total = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(BillPayment.amount_cents - BillPayment.reserve_drawn_cents), 0
                )
            ).where(
                BillPayment.user_id == user_id,
                BillPayment.created_at >= since,
                BillPayment.undone_at.is_(None),
            )
        )
        return int(total or 0)


class DebtPaymentRepository(UserOwnedRepository[DebtPayment]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DebtPayment, order_by=(DebtPayment.paid_on,))

    def list_for_debt(self, user_id: uuid.UUID, debt_id: uuid.UUID) -> Sequence[DebtPayment]:
        """One debt's payments that were not undone, newest first."""
        return self._session.scalars(
            self._owned_by(user_id)
            .where(DebtPayment.debt_id == debt_id, DebtPayment.undone_at.is_(None))
            .order_by(
                DebtPayment.paid_on.desc(), DebtPayment.created_at.desc(), DebtPayment.id.desc()
            )
        ).all()

    def find_any_owner(self, payment_id: uuid.UUID) -> DebtPayment | None:
        """The payment with this id, whoever owns it. Only for spotting a reused id:
        the caller must check the owner before returning it (ADR 0015)."""
        return self._session.get(DebtPayment, payment_id)

    def unreserved_since(self, user_id: uuid.UUID, since: datetime) -> int:
        """Cents that payments recorded at or after ``since``, and not undone, paid beyond
        their reserves."""
        total = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(DebtPayment.amount_cents - DebtPayment.reserve_drawn_cents), 0
                )
            ).where(
                DebtPayment.user_id == user_id,
                DebtPayment.created_at >= since,
                DebtPayment.undone_at.is_(None),
            )
        )
        return int(total or 0)
