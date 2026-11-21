"""Bills and the payments recorded against them."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.columns import Cents, TimestampsMixin, UserOwnedMixin, owned_by_user, tenant_fk


class Bill(UserOwnedMixin, TimestampsMixin, Base):
    """A bill. ``repeat_every_months`` None is the engine's ``OneTime(first_due_date)``;
    a number N is ``EveryNMonths(first_due_date, N)``."""

    __tablename__ = "bills"
    __table_args__ = (
        owned_by_user(),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint("priority >= 1", name="priority_positive"),
        CheckConstraint("repeat_every_months >= 1", name="repeat_every_months_positive"),
    )

    name: Mapped[str] = mapped_column(String(100))
    amount_cents: Mapped[Cents]
    # 1 is the most important.
    priority: Mapped[int]
    first_due_date: Mapped[date]
    repeat_every_months: Mapped[int | None]


class BillPayment(UserOwnedMixin, TimestampsMixin, Base):
    """A payment toward one occurrence of a bill; it draws that bill's reserve down."""

    __tablename__ = "bill_payments"
    __table_args__ = (
        owned_by_user(),
        tenant_fk("bill_id", "bills", ondelete="CASCADE"),
        Index("ix_bill_payments_bill_id_due_date", "bill_id", "due_date"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint(
            "reserve_drawn_cents >= 0 AND reserve_drawn_cents <= amount_cents",
            name="reserve_drawn_range",
        ),
    )

    bill_id: Mapped[uuid.UUID]
    # Which occurrence this pays, e.g. the Oct 20 rent.
    due_date: Mapped[date]
    paid_on: Mapped[date]
    amount_cents: Mapped[Cents]
    # How much of the payment came out of its reserve; the rest came out of Safe to Spend.
    # Sorted after the timestamps because a migration added it to the table's end.
    reserve_drawn_cents: Mapped[Cents] = mapped_column(sort_order=3)
    # When the payment was undone (ADR 0017): it then counts for nothing, and is kept as history.
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), sort_order=4)
