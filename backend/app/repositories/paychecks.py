"""Storage for paychecks. A paycheck is identified by its income source and pay date."""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from app.models import Paycheck
from app.repositories.owned import UserOwnedRepository


class PaycheckRepository(UserOwnedRepository[Paycheck]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Paycheck, order_by=(Paycheck.pay_date, Paycheck.income_source_id))

    def find(self, user_id: uuid.UUID, source_id: uuid.UUID, pay_date: date) -> Paycheck | None:
        return self._session.scalar(
            self._owned_by(user_id).where(
                Paycheck.income_source_id == source_id, Paycheck.pay_date == pay_date
            )
        )

    def list_between(self, user_id: uuid.UUID, start: date, end: date) -> Sequence[Paycheck]:
        """Stored paychecks with ``start <= pay_date <= end``, by date."""
        return self._session.scalars(
            self._owned_by(user_id)
            .where(Paycheck.pay_date.between(start, end))
            .order_by(*self._order_by)
        ).all()
