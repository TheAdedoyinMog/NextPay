"""Storage for balance snapshots, which are append-only."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BalanceSnapshot
from app.repositories.owned import UserOwnedRepository


class BalanceSnapshotRepository(UserOwnedRepository[BalanceSnapshot]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BalanceSnapshot, order_by=(BalanceSnapshot.as_of,))

    def latest(self, user_id: uuid.UUID, limit: int) -> Sequence[BalanceSnapshot]:
        """Up to ``limit`` snapshots, newest first: the first one is the current balance."""
        return self._session.scalars(
            select(BalanceSnapshot)
            .where(BalanceSnapshot.user_id == user_id)
            .order_by(
                BalanceSnapshot.as_of.desc(),
                BalanceSnapshot.created_at.desc(),
                BalanceSnapshot.id.desc(),
            )
            .limit(limit)
        ).all()
