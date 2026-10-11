"""Essential expenses, debts, and the payments recorded against debts."""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.columns import Cents, TimestampsMixin, UserOwnedMixin, owned_by_user, tenant_fk


class EssentialExpense(UserOwnedMixin, TimestampsMixin, Base):
    """A spending need funded every pay period, such as groceries or gas."""

    __tablename__ = "essential_expenses"
    __table_args__ = (
        owned_by_user(),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("amount_per_period_cents > 0", name="amount_per_period_positive"),
    )

    name: Mapped[str] = mapped_column(String(100))
    amount_per_period_cents: Mapped[Cents]


class Debt(UserOwnedMixin, TimestampsMixin, Base):
    """A debt with a monthly minimum due on ``due_day`` (past a month's end: its last day)."""

    __tablename__ = "debts"
    __table_args__ = (
        owned_by_user(),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("balance_cents >= 0", name="balance_not_negative"),
        CheckConstraint("apr_bps >= 0", name="apr_bps_not_negative"),
        CheckConstraint("minimum_payment_cents >= 0", name="minimum_payment_not_negative"),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="due_day_range"),
    )

    name: Mapped[str] = mapped_column(String(100))
    balance_cents: Mapped[Cents]
    # Annual rate in basis points: 24.99% is 2499.
    apr_bps: Mapped[int]
    minimum_payment_cents: Mapped[Cents]
    due_day: Mapped[int]


class DebtPayment(UserOwnedMixin, TimestampsMixin, Base):
    """A payment toward a debt; it draws the debt's reserve and its balance down."""

    __tablename__ = "debt_payments"
    __table_args__ = (
        owned_by_user(),
        tenant_fk("debt_id", "debts", ondelete="CASCADE"),
        Index("ix_debt_payments_debt_id_paid_on", "debt_id", "paid_on"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
    )

    debt_id: Mapped[uuid.UUID]
    paid_on: Mapped[date]
    amount_cents: Mapped[Cents]
