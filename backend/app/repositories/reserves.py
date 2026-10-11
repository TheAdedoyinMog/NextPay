"""Storage for reserves: money set aside for a bill, goal, or debt (ADR 0003).

One row per target holds its current amount. A target with no row has nothing
reserved.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import Reserve
from app.repositories.owned import UserOwnedRepository
from nextpay_engine import ReserveKind

_TARGET_COLUMN = {
    ReserveKind.BILL: Reserve.bill_id,
    ReserveKind.GOAL: Reserve.goal_id,
    ReserveKind.DEBT: Reserve.debt_id,
}


class ReserveRepository(UserOwnedRepository[Reserve]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Reserve, order_by=(Reserve.kind,))

    def find(self, user_id: uuid.UUID, kind: ReserveKind, target_id: uuid.UUID) -> Reserve | None:
        """The reserve for one bill, goal, or debt, if it has one."""
        return self._session.scalar(
            self._owned_by(user_id).where(_TARGET_COLUMN[kind] == target_id)
        )
