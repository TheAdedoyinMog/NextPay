"""Paycheck plans: immutable, versioned snapshots of the engine's PlanResult.

A plan is never edited after it is generated, apart from its status. Its
allocations and goal projections copy everything needed to explain it later,
including target names, so an old plan still reads correctly after a bill or
goal is deleted (their foreign keys become NULL).
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CHAR, CheckConstraint, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.columns import (
    Cents,
    CreatedAtMixin,
    TimestampsMixin,
    UserOwnedMixin,
    owned_by_user,
    str_enum,
    tenant_fk,
)
from nextpay_engine import GoalStatus, Reason, Tier


class PlanStatus(StrEnum):
    DRAFT = "draft"  # generated, not yet accepted
    COMMITTED = "committed"  # accepted: its allocations became reserves
    SUPERSEDED = "superseded"  # replaced by a later version for the same paycheck


class PaycheckPlan(UserOwnedMixin, TimestampsMixin, Base):
    __tablename__ = "paycheck_plans"
    __table_args__ = (
        owned_by_user(),
        tenant_fk("paycheck_id", "paychecks", ondelete="RESTRICT"),
        UniqueConstraint("paycheck_id", "version"),
        Index(
            "ix_paycheck_plans_one_committed_per_paycheck",
            "paycheck_id",
            unique=True,
            postgresql_where="status = 'committed'",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(status <> 'draft' OR committed_at IS NULL)"
            " AND (status <> 'committed' OR committed_at IS NOT NULL)",
            name="committed_at_matches_status",
        ),
        CheckConstraint("input_hash ~ '^[0-9a-f]{64}$'", name="input_hash_sha256_hex"),
        CheckConstraint("paycheck_amount_cents >= 0", name="paycheck_amount_not_negative"),
        CheckConstraint("safe_to_spend_cents >= 0", name="safe_to_spend_not_negative"),
        CheckConstraint("reserve_deficit_cents >= 0", name="reserve_deficit_not_negative"),
    )

    paycheck_id: Mapped[uuid.UUID]
    # 1, 2, 3... per paycheck, e.g. regenerated after the actual amount is recorded.
    version: Mapped[int]
    status: Mapped[PlanStatus] = mapped_column(str_enum(PlanStatus, "status"))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engine_version: Mapped[str] = mapped_column(String(32))
    # SHA-256 (hex) of the engine inputs; a mismatch means the plan is out of date.
    input_hash: Mapped[str] = mapped_column(CHAR(64))
    # PlanResult.as_of and next_pay_date.
    as_of: Mapped[date]
    next_pay_date: Mapped[date]
    # The inputs that matter most, kept as planned: the paycheck amount used
    # (actual if recorded, else expected) and the available balance (signed).
    paycheck_amount_cents: Mapped[Cents]
    available_balance_cents: Mapped[Cents]
    safe_to_spend_cents: Mapped[Cents]
    reserve_deficit_cents: Mapped[Cents]


class Allocation(UserOwnedMixin, CreatedAtMixin, Base):
    """One line of a plan, with its Basis: the facts behind the amount."""

    __tablename__ = "allocations"
    __table_args__ = (
        owned_by_user(),
        tenant_fk("plan_id", "paycheck_plans", ondelete="CASCADE"),
        tenant_fk("bill_id", "bills", ondelete="SET NULL"),
        tenant_fk("essential_expense_id", "essential_expenses", ondelete="SET NULL"),
        tenant_fk("debt_id", "debts", ondelete="SET NULL"),
        tenant_fk("goal_id", "goals", ondelete="SET NULL"),
        UniqueConstraint("plan_id", "position"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        CheckConstraint("requested_cents > 0", name="requested_positive"),
        CheckConstraint(
            "funded_cents >= 0 AND funded_cents <= requested_cents", name="funded_range"
        ),
        CheckConstraint("total_cents >= 0", name="total_not_negative"),
        CheckConstraint("set_aside_cents >= 0", name="set_aside_not_negative"),
        CheckConstraint("paychecks >= 1", name="paychecks_positive"),
        CheckConstraint("days_covered >= 0", name="days_covered_not_negative"),
        CheckConstraint("days_in_period >= 1", name="days_in_period_positive"),
        CheckConstraint("share_bps BETWEEN 0 AND 10000", name="share_bps_range"),
        # Only the tier's own target may be set; it is NULL once the target is deleted.
        CheckConstraint(
            "(tier = 'bill'"
            " AND essential_expense_id IS NULL AND debt_id IS NULL AND goal_id IS NULL)"
            " OR (tier = 'essential'"
            " AND bill_id IS NULL AND debt_id IS NULL AND goal_id IS NULL)"
            " OR (tier = 'debt_minimum'"
            " AND bill_id IS NULL AND essential_expense_id IS NULL AND goal_id IS NULL)"
            " OR (tier IN ('emergency_fund', 'goal')"
            " AND bill_id IS NULL AND essential_expense_id IS NULL AND debt_id IS NULL)",
            name="target_matches_tier",
        ),
    )

    plan_id: Mapped[uuid.UUID]
    # Order in the waterfall, from 0.
    position: Mapped[int]
    tier: Mapped[Tier] = mapped_column(str_enum(Tier, "tier"))
    bill_id: Mapped[uuid.UUID | None]
    essential_expense_id: Mapped[uuid.UUID | None]
    debt_id: Mapped[uuid.UUID | None]
    goal_id: Mapped[uuid.UUID | None]
    requested_cents: Mapped[Cents]
    funded_cents: Mapped[Cents]
    # Basis, field for field.
    reason: Mapped[Reason] = mapped_column(str_enum(Reason, "reason"))
    name: Mapped[str] = mapped_column(String(100))
    total_cents: Mapped[Cents]
    set_aside_cents: Mapped[Cents]
    due_date: Mapped[date | None]
    paychecks: Mapped[int | None]
    days_covered: Mapped[int | None]
    days_in_period: Mapped[int | None]
    share_bps: Mapped[int | None]


class GoalProjection(UserOwnedMixin, CreatedAtMixin, Base):
    """When one goal would be reached at this plan's rate (engine GoalProjection)."""

    __tablename__ = "goal_projections"
    __table_args__ = (
        owned_by_user(),
        tenant_fk("plan_id", "paycheck_plans", ondelete="CASCADE"),
        tenant_fk("goal_id", "goals", ondelete="SET NULL"),
        UniqueConstraint("plan_id", "position"),
        UniqueConstraint("plan_id", "goal_id"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        CheckConstraint("contribution_cents >= 0", name="contribution_not_negative"),
        CheckConstraint("still_needed_cents >= 0", name="still_needed_not_negative"),
    )

    plan_id: Mapped[uuid.UUID]
    # Order in the plan, from 0.
    position: Mapped[int]
    goal_id: Mapped[uuid.UUID | None]
    name: Mapped[str] = mapped_column(String(100))
    deadline: Mapped[date | None]
    contribution_cents: Mapped[Cents]
    still_needed_cents: Mapped[Cents]
    projected_date: Mapped[date | None]
    status: Mapped[GoalStatus] = mapped_column(str_enum(GoalStatus, "status"))
