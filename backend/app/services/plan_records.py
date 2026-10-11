"""The engine's PlanResult to stored rows, and back again to explain it (ADR 0008).

A stored plan copies every fact behind every number, so it can be rebuilt as a
``PlanResult`` and explained by the engine long after the bills and goals it
mentions have changed or gone. The sentences are not stored: they are written
by the engine each time a plan is read.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import nextpay_engine as engine
from app.models import (
    Allocation,
    GoalProjection,
    IncomeSource,
    Paycheck,
    PaycheckPlan,
    PlanStatus,
)
from app.services.planning_state import PlanningInputs

# The column that holds an allocation's target, by tier (the table's CHECK agrees).
_TARGET_COLUMN = {
    engine.Tier.BILL: "bill_id",
    engine.Tier.ESSENTIAL: "essential_expense_id",
    engine.Tier.DEBT_MINIMUM: "debt_id",
    engine.Tier.EMERGENCY_FUND: "goal_id",
    engine.Tier.GOAL: "goal_id",
}


@dataclass(frozen=True, slots=True)
class ExplainedAllocation:
    row: Allocation
    # None once the bill, expense, debt, or goal has been deleted.
    target_id: uuid.UUID | None
    explanation: str


@dataclass(frozen=True, slots=True)
class ExplainedProjection:
    row: GoalProjection
    # The date to offer when the goal is behind or its deadline has passed.
    suggested_deadline: date | None
    explanation: str


@dataclass(frozen=True, slots=True)
class PlanDetails:
    """A stored plan with everything needed to show it."""

    plan: PaycheckPlan
    paycheck: Paycheck
    source: IncomeSource
    summary: str
    allocations: tuple[ExplainedAllocation, ...]
    projections: tuple[ExplainedProjection, ...]


def allocation_target(row: Allocation) -> uuid.UUID | None:
    target: uuid.UUID | None = getattr(row, _TARGET_COLUMN[row.tier])
    return target


def new_plan_rows(
    result: engine.PlanResult,
    *,
    user_id: uuid.UUID,
    paycheck_id: uuid.UUID,
    version: int,
    input_hash: str,
    inputs: PlanningInputs,
) -> tuple[PaycheckPlan, list[Allocation], list[GoalProjection]]:
    """A draft plan and its lines, ready to store."""
    plan = PaycheckPlan(
        id=uuid.uuid4(),
        user_id=user_id,
        paycheck_id=paycheck_id,
        version=version,
        status=PlanStatus.DRAFT,
        engine_version=engine.ENGINE_VERSION,
        input_hash=input_hash,
        as_of=result.as_of,
        next_pay_date=result.next_pay_date,
        paycheck_amount_cents=result.paycheck.amount.cents,
        available_balance_cents=inputs.state.available_balance.cents,
        safe_to_spend_cents=result.safe_to_spend.cents,
        reserve_deficit_cents=result.reserve_deficit.cents,
        balance_as_of=None if inputs.balance is None else inputs.balance.as_of,
    )
    allocations = [
        _allocation_row(allocation, user_id, plan.id, position)
        for position, allocation in enumerate(result.allocations)
    ]
    projections = [
        GoalProjection(
            id=uuid.uuid4(),
            user_id=user_id,
            plan_id=plan.id,
            position=position,
            goal_id=uuid.UUID(projection.goal_id),
            name=projection.name,
            deadline=projection.deadline,
            contribution_cents=projection.contribution.cents,
            still_needed_cents=projection.still_needed.cents,
            projected_date=projection.projected_date,
            status=projection.status,
        )
        for position, projection in enumerate(result.goal_projections)
    ]
    return plan, allocations, projections


def _allocation_row(
    allocation: engine.Allocation, user_id: uuid.UUID, plan_id: uuid.UUID, position: int
) -> Allocation:
    basis = allocation.basis
    row = Allocation(
        id=uuid.uuid4(),
        user_id=user_id,
        plan_id=plan_id,
        position=position,
        tier=allocation.tier,
        requested_cents=allocation.requested.cents,
        funded_cents=allocation.funded.cents,
        reason=basis.reason,
        name=basis.name,
        total_cents=basis.total.cents,
        set_aside_cents=basis.set_aside.cents,
        due_date=basis.due,
        paychecks=basis.paychecks,
        days_covered=basis.days_covered,
        days_in_period=basis.days_in_period,
        share_bps=basis.share_bps,
    )
    setattr(row, _TARGET_COLUMN[allocation.tier], uuid.UUID(allocation.target_id))
    return row


def to_engine_plan(
    plan: PaycheckPlan,
    paycheck: Paycheck,
    allocations: Sequence[Allocation],
    projections: Sequence[GoalProjection],
) -> engine.PlanResult:
    """The ``PlanResult`` a stored plan was made from, as far as explaining it needs.

    A deleted target's id comes back empty; the names and amounts are the plan's own.
    """
    return engine.PlanResult(
        paycheck=engine.Paycheck(
            source_id=str(paycheck.income_source_id),
            pay_date=paycheck.pay_date,
            expected_amount=engine.Money(paycheck.expected_amount_cents),
            # The amount as planned, whatever has been recorded since.
            actual_amount=engine.Money(plan.paycheck_amount_cents),
        ),
        as_of=plan.as_of,
        next_pay_date=plan.next_pay_date,
        allocations=tuple(_engine_allocation(row) for row in allocations),
        safe_to_spend=engine.Money(plan.safe_to_spend_cents),
        reserve_deficit=engine.Money(plan.reserve_deficit_cents),
        goal_projections=tuple(_engine_projection(row) for row in projections),
    )


def _engine_allocation(row: Allocation) -> engine.Allocation:
    return engine.Allocation(
        tier=row.tier,
        target_id=str(allocation_target(row) or ""),
        requested=engine.Money(row.requested_cents),
        funded=engine.Money(row.funded_cents),
        basis=engine.Basis(
            reason=row.reason,
            name=row.name,
            total=engine.Money(row.total_cents),
            set_aside=engine.Money(row.set_aside_cents),
            due=row.due_date,
            paychecks=row.paychecks,
            days_covered=row.days_covered,
            days_in_period=row.days_in_period,
            share_bps=row.share_bps,
        ),
    )


def _engine_projection(row: GoalProjection) -> engine.GoalProjection:
    return engine.GoalProjection(
        goal_id=str(row.goal_id or ""),
        name=row.name,
        deadline=row.deadline,
        contribution=engine.Money(row.contribution_cents),
        still_needed=engine.Money(row.still_needed_cents),
        projected_date=row.projected_date,
        status=row.status,
    )


def describe(
    plan: PaycheckPlan,
    paycheck: Paycheck,
    source: IncomeSource,
    allocations: Sequence[Allocation],
    projections: Sequence[GoalProjection],
) -> PlanDetails:
    """A stored plan with the engine's explanation of every line."""
    result = to_engine_plan(plan, paycheck, allocations, projections)
    return PlanDetails(
        plan=plan,
        paycheck=paycheck,
        source=source,
        summary=engine.explain_plan(result),
        allocations=tuple(
            ExplainedAllocation(
                row, allocation_target(row), engine.explain_allocation(allocation, result)
            )
            for row, allocation in zip(allocations, result.allocations, strict=True)
        ),
        projections=tuple(
            ExplainedProjection(
                row, projection.suggested_deadline, engine.explain_projection(projection, result)
            )
            for row, projection in zip(projections, result.goal_projections, strict=True)
        ),
    )
