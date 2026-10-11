"""Storage for paycheck plans and their lines (ADR 0008: immutable snapshots)."""

import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Allocation, GoalProjection, PaycheckPlan, PlanStatus
from app.repositories.owned import UserOwnedRepository


class PlanRepository(UserOwnedRepository[PaycheckPlan]):
    def __init__(self, session: Session) -> None:
        super().__init__(
            session, PaycheckPlan, order_by=(PaycheckPlan.paycheck_id, PaycheckPlan.version)
        )

    def list_for_paycheck(
        self, user_id: uuid.UUID, paycheck_id: uuid.UUID
    ) -> Sequence[PaycheckPlan]:
        """Every version of one paycheck's plan, oldest first."""
        return self._session.scalars(
            self._owned_by(user_id)
            .where(PaycheckPlan.paycheck_id == paycheck_id)
            .order_by(PaycheckPlan.version)
        ).all()

    def current_for_paychecks(
        self, user_id: uuid.UUID, paycheck_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, PaycheckPlan]:
        """Each paycheck's plan that counts: its newest one that was not superseded."""
        if not paycheck_ids:
            return {}
        plans = self._session.scalars(
            self._owned_by(user_id)
            .where(
                PaycheckPlan.paycheck_id.in_(paycheck_ids),
                PaycheckPlan.status != PlanStatus.SUPERSEDED,
            )
            .order_by(PaycheckPlan.version)
        )
        # Later versions overwrite earlier ones.
        return {plan.paycheck_id: plan for plan in plans}

    def add_plan(
        self,
        plan: PaycheckPlan,
        allocations: Sequence[Allocation],
        projections: Sequence[GoalProjection],
    ) -> PaycheckPlan:
        """Insert a plan with its lines. The plan goes first: its lines reference it."""
        self.add(plan)
        self._session.add_all([*allocations, *projections])
        self._session.flush()
        return plan

    def allocations(self, user_id: uuid.UUID, plan_id: uuid.UUID) -> Sequence[Allocation]:
        """A plan's lines, in waterfall order."""
        return self._session.scalars(
            select(Allocation)
            .where(Allocation.user_id == user_id, Allocation.plan_id == plan_id)
            .order_by(Allocation.position)
        ).all()

    def projections(self, user_id: uuid.UUID, plan_id: uuid.UUID) -> Sequence[GoalProjection]:
        return self._session.scalars(
            select(GoalProjection)
            .where(GoalProjection.user_id == user_id, GoalProjection.plan_id == plan_id)
            .order_by(GoalProjection.position)
        ).all()
