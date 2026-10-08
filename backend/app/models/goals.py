"""Goals, including purchases (ADR 0004)."""

from datetime import date

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.columns import Cents, TimestampsMixin, UserOwnedMixin, owned_by_user, str_enum
from nextpay_engine import GoalKind


class Goal(UserOwnedMixin, TimestampsMixin, Base):
    __tablename__ = "goals"
    __table_args__ = (
        owned_by_user(),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("target_cents > 0", name="target_positive"),
        CheckConstraint("current_cents >= 0", name="current_not_negative"),
        CheckConstraint("priority >= 1", name="priority_positive"),
        # FinancialState allows at most one emergency goal.
        Index(
            "ix_goals_one_emergency_per_user",
            "user_id",
            unique=True,
            postgresql_where="kind = 'emergency'",
        ),
    )

    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[GoalKind] = mapped_column(str_enum(GoalKind, "kind"))
    target_cents: Mapped[Cents]
    # Saved so far; may exceed the target once it is reached.
    current_cents: Mapped[Cents]
    # 1 is the most important.
    priority: Mapped[int]
    deadline: Mapped[date | None]
