"""Income sources and their paychecks (ADR 0005).

A pay schedule is stored as a frequency plus the parameters its engine class
needs: Weekly and Biweekly take ``anchor_date``; Monthly takes ``day_of_month``;
SemiMonthly takes ``day_of_month`` and ``second_day_of_month``. A CHECK makes each
frequency carry exactly its own parameters. Rules that span both semi-monthly
days (at least 7 days apart) stay in the engine.
"""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.columns import (
    Cents,
    NullableCents,
    TimestampsMixin,
    UserOwnedMixin,
    owned_by_user,
    str_enum,
    tenant_fk,
)


class PayFrequency(StrEnum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    SEMI_MONTHLY = "semi_monthly"
    MONTHLY = "monthly"


class IncomeSource(UserOwnedMixin, TimestampsMixin, Base):
    __tablename__ = "income_sources"
    __table_args__ = (
        owned_by_user(),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("expected_amount_cents > 0", name="expected_amount_positive"),
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="day_of_month_range"),
        CheckConstraint("second_day_of_month BETWEEN 1 AND 31", name="second_day_of_month_range"),
        CheckConstraint(
            "(pay_frequency IN ('weekly', 'biweekly')"
            " AND anchor_date IS NOT NULL"
            " AND day_of_month IS NULL AND second_day_of_month IS NULL)"
            " OR (pay_frequency = 'semi_monthly'"
            " AND anchor_date IS NULL"
            " AND day_of_month IS NOT NULL AND second_day_of_month IS NOT NULL"
            " AND day_of_month < second_day_of_month)"
            " OR (pay_frequency = 'monthly'"
            " AND anchor_date IS NULL"
            " AND day_of_month IS NOT NULL AND second_day_of_month IS NULL)",
            name="schedule_parameters",
        ),
    )

    name: Mapped[str] = mapped_column(String(100))
    expected_amount_cents: Mapped[Cents]
    pay_frequency: Mapped[PayFrequency] = mapped_column(str_enum(PayFrequency, "pay_frequency"))
    # Any real payday, past or future (weekly and biweekly).
    anchor_date: Mapped[date | None]
    day_of_month: Mapped[int | None]
    second_day_of_month: Mapped[int | None]


class Paycheck(UserOwnedMixin, TimestampsMixin, Base):
    """One paycheck: expected up front; the actual amount is recorded when paid."""

    __tablename__ = "paychecks"
    __table_args__ = (
        owned_by_user(),
        # Paychecks and their plans are history: an income source with paychecks
        # cannot be deleted out from under them (2C decides archive vs. refuse).
        tenant_fk("income_source_id", "income_sources", ondelete="RESTRICT"),
        UniqueConstraint("income_source_id", "pay_date"),
        CheckConstraint("expected_amount_cents > 0", name="expected_amount_positive"),
        # $0 is a real outcome, for example unpaid leave.
        CheckConstraint("actual_amount_cents >= 0", name="actual_amount_not_negative"),
    )

    income_source_id: Mapped[uuid.UUID]
    pay_date: Mapped[date]
    expected_amount_cents: Mapped[Cents]
    actual_amount_cents: Mapped[NullableCents]
