"""Storage for income sources.

An archived source is history: ``get`` and ``list_for`` never return one. Code
that shows old paychecks reads it with ``get_including_archived``.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import IncomeSource
from app.repositories.owned import UserOwnedRepository


class IncomeSourceRepository(UserOwnedRepository[IncomeSource]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, IncomeSource, order_by=(IncomeSource.name,))

    def _owned_by(self, user_id: uuid.UUID) -> Select[IncomeSource]:
        return super()._owned_by(user_id).where(IncomeSource.archived_at.is_(None))

    def get_including_archived(
        self, user_id: uuid.UUID, source_id: uuid.UUID
    ) -> IncomeSource | None:
        return self._session.scalar(
            select(IncomeSource).where(
                IncomeSource.user_id == user_id, IncomeSource.id == source_id
            )
        )

    def list_including_archived(self, user_id: uuid.UUID) -> Sequence[IncomeSource]:
        return self._session.scalars(
            select(IncomeSource).where(IncomeSource.user_id == user_id).order_by(IncomeSource.id)
        ).all()

    def delete_or_archive(self, row: IncomeSource, at: datetime) -> bool:
        """Delete ``row``, or archive it as of ``at`` if it has paychecks.

        Returns whether it was archived. The database decides (paychecks reference
        their source with RESTRICT), so a paycheck recorded while this request
        runs is still caught.
        """
        try:
            with self._session.begin_nested():
                self._session.delete(row)
        except IntegrityError:
            # The only way deleting a row can break integrity: something still points at it.
            row.archived_at = at
            self._session.flush()
            return True
        return False
