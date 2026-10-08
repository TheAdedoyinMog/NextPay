"""Money already set aside for a bill, goal, or debt (ADR 0003).

One row per target holds its current amount. Committing a plan adds to it,
paying a bill draws it down, and deleting the target deletes the row, which
releases the money. History lives in allocations and bill payments.
"""

import uuid

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.columns import (
    Cents,
    TimestampsMixin,
    UserOwnedMixin,
    owned_by_user,
    str_enum,
    tenant_fk,
)
from nextpay_engine import ReserveKind


class Reserve(UserOwnedMixin, TimestampsMixin, Base):
    __tablename__ = "reserves"
    __table_args__ = (
        owned_by_user(),
        tenant_fk("bill_id", "bills", ondelete="CASCADE"),
        tenant_fk("goal_id", "goals", ondelete="CASCADE"),
        tenant_fk("debt_id", "debts", ondelete="CASCADE"),
        UniqueConstraint("bill_id"),
        UniqueConstraint("goal_id"),
        UniqueConstraint("debt_id"),
        CheckConstraint("amount_cents >= 0", name="amount_not_negative"),
        # Exactly the foreign key that matches kind is set.
        CheckConstraint(
            "(kind = 'bill' AND bill_id IS NOT NULL AND goal_id IS NULL AND debt_id IS NULL)"
            " OR (kind = 'goal' AND goal_id IS NOT NULL AND bill_id IS NULL AND debt_id IS NULL)"
            " OR (kind = 'debt' AND debt_id IS NOT NULL AND bill_id IS NULL AND goal_id IS NULL)",
            name="target_matches_kind",
        ),
    )

    kind: Mapped[ReserveKind] = mapped_column(str_enum(ReserveKind, "kind"))
    bill_id: Mapped[uuid.UUID | None]
    goal_id: Mapped[uuid.UUID | None]
    debt_id: Mapped[uuid.UUID | None]
    amount_cents: Mapped[Cents]
