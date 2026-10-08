"""The user's available balance, as entered."""

from datetime import datetime

from sqlalchemy import DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.columns import Cents, TimestampsMixin, UserOwnedMixin, owned_by_user


class BalanceSnapshot(UserOwnedMixin, TimestampsMixin, Base):
    """Append-only: the latest ``as_of`` is the current balance; none means $0."""

    __tablename__ = "balance_snapshots"
    __table_args__ = (
        owned_by_user(),
        Index("ix_balance_snapshots_user_id_as_of", "user_id", "as_of"),
    )

    # Signed: negative when overdrawn.
    amount_cents: Mapped[Cents]
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
