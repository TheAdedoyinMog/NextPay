"""Storage shared by every user-owned table (ADR 0008, ADR 0010).

This is the tenant boundary, written once: every read takes a ``user_id`` and
filters by it, so a repository cannot return another user's row. The design
avoids generic base classes; this one is the deliberate exception, because six
hand-written copies would be six places to get the scoping wrong.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models.columns import UserOwnedMixin


class UserOwnedRepository[M: UserOwnedMixin]:
    def __init__(
        self, session: Session, model: type[M], *, order_by: Sequence[InstrumentedAttribute[Any]]
    ) -> None:
        self._session = session
        self._model = model
        # id last, so the order is total even when every other column ties.
        self._order_by = (*order_by, model.id)

    def get(self, user_id: uuid.UUID, row_id: uuid.UUID) -> M | None:
        """The row with ``row_id`` if ``user_id`` owns it; None otherwise."""
        return self._session.scalar(
            select(self._model).where(self._model.user_id == user_id, self._model.id == row_id)
        )

    def list_for(self, user_id: uuid.UUID) -> Sequence[M]:
        return self._session.scalars(
            select(self._model).where(self._model.user_id == user_id).order_by(*self._order_by)
        ).all()

    def add(self, row: M) -> M:
        self._session.add(row)
        self._session.flush()
        return row

    def delete(self, row: M) -> None:
        """Delete ``row``; the database cascades to what hangs off it (ADR 0010)."""
        self._session.delete(row)
        self._session.flush()
