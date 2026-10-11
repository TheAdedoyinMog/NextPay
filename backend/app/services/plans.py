"""Paycheck plans: generating one with the engine, reading it, committing it (ADR 0011).

A plan is a stored snapshot of ``plan_paycheck``'s answer for one paycheck. It
starts as a draft. Planning the same paycheck again replaces the draft with a
new version, unless nothing the engine reads has changed, in which case the
same draft is returned. Committing a draft turns what it funded into reserves
(ADR 0003); a committed plan is final.
"""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Protocol

import nextpay_engine as engine
from app.core.clock import Clock, local_date
from app.core.errors import (
    NotFoundError,
    PaycheckAlreadyCommittedError,
    PlanOutOfDateError,
    PlanSupersededError,
)
from app.models import (
    Allocation,
    Goal,
    GoalProjection,
    IncomeSource,
    Paycheck,
    PaycheckPlan,
    PlanStatus,
    User,
)
from app.services.engine_mapping import to_engine_paycheck
from app.services.paychecks import PaycheckStore, find_or_create_paycheck
from app.services.plan_inputs import input_hash
from app.services.plan_records import PlanDetails, allocation_target, describe, new_plan_rows
from app.services.planning_state import PlanningStateLoader
from app.services.protocols import Transaction, UserLock
from app.services.reserves import ReserveStore, add_to_reserve
from nextpay_engine import ReserveKind


class PlanSources(Protocol):
    """Income sources, as plans need them. ``get`` skips archived ones."""

    def get(self, user_id: uuid.UUID, row_id: uuid.UUID) -> IncomeSource | None: ...
    def get_including_archived(
        self, user_id: uuid.UUID, source_id: uuid.UUID
    ) -> IncomeSource | None: ...


class PlanPaychecks(PaycheckStore, Protocol):
    def get(self, user_id: uuid.UUID, row_id: uuid.UUID) -> Paycheck | None: ...


class PlanStore(Protocol):
    def get(self, user_id: uuid.UUID, row_id: uuid.UUID) -> PaycheckPlan | None: ...
    def list_for_paycheck(
        self, user_id: uuid.UUID, paycheck_id: uuid.UUID
    ) -> Sequence[PaycheckPlan]: ...
    def add_plan(
        self,
        plan: PaycheckPlan,
        allocations: Sequence[Allocation],
        projections: Sequence[GoalProjection],
    ) -> PaycheckPlan: ...
    def allocations(self, user_id: uuid.UUID, plan_id: uuid.UUID) -> Sequence[Allocation]: ...
    def projections(self, user_id: uuid.UUID, plan_id: uuid.UUID) -> Sequence[GoalProjection]: ...


class GoalLookup(Protocol):
    def get(self, user_id: uuid.UUID, row_id: uuid.UUID) -> Goal | None: ...


# What a funded line sets aside when its plan is committed. Essentials are missing
# on purpose: they are money to spend this period, not money to hold.
_RESERVE_KIND = {
    engine.Tier.BILL: ReserveKind.BILL,
    engine.Tier.DEBT_MINIMUM: ReserveKind.DEBT,
    engine.Tier.EMERGENCY_FUND: ReserveKind.GOAL,
    engine.Tier.GOAL: ReserveKind.GOAL,
}


class PlanService:
    def __init__(
        self,
        *,
        users: UserLock,
        income_sources: PlanSources,
        paychecks: PlanPaychecks,
        plans: PlanStore,
        goals: GoalLookup,
        reserves: ReserveStore,
        state: PlanningStateLoader,
        transaction: Transaction,
        clock: Clock,
    ) -> None:
        self._users = users
        self._income_sources = income_sources
        self._paychecks = paychecks
        self._plans = plans
        self._goals = goals
        self._reserves = reserves
        self._state = state
        self._transaction = transaction
        self._clock = clock

    def generate(
        self, user: User, source_id: uuid.UUID, pay_date: date
    ) -> tuple[PlanDetails, bool]:
        """Plan the paycheck ``source_id`` pays on ``pay_date``, as of today for ``user``.

        Returns the draft and whether it is new. It is not new when the paycheck's
        current draft was made from exactly the same inputs: the engine would
        give the same answer, so that draft is returned as it is.

        Raises ``NotFoundError`` for an unknown or archived source,
        ``InvalidInputError`` for a date that is not one of its paydays, and
        ``PaycheckAlreadyCommittedError`` once the paycheck has a committed plan.
        """
        self._users.lock(user.id)
        source = self._income_sources.get(user.id, source_id)
        if source is None:
            raise NotFoundError()
        paycheck = find_or_create_paycheck(self._paychecks, source, pay_date)
        versions = self._plans.list_for_paycheck(user.id, paycheck.id)
        if any(plan.status is PlanStatus.COMMITTED for plan in versions):
            raise PaycheckAlreadyCommittedError()
        # Until a plan is committed, the paycheck follows its source's expected amount.
        paycheck.expected_amount_cents = source.expected_amount_cents

        inputs = self._state.load(user)
        engine_paycheck = to_engine_paycheck(paycheck)
        as_of = local_date(self._clock(), user.timezone)
        digest = input_hash(inputs.state, engine_paycheck, as_of)

        drafts = [plan for plan in versions if plan.status is PlanStatus.DRAFT]
        if drafts and drafts[-1].input_hash == digest:
            self._transaction.commit()
            return self._details(drafts[-1], paycheck, source), False

        result = engine.plan_paycheck(inputs.state, engine_paycheck, as_of)
        for draft in drafts:
            draft.status = PlanStatus.SUPERSEDED
        plan, allocations, projections = new_plan_rows(
            result,
            user_id=user.id,
            paycheck_id=paycheck.id,
            version=1 + max((plan.version for plan in versions), default=0),
            input_hash=digest,
            inputs=inputs,
        )
        self._plans.add_plan(plan, allocations, projections)
        self._transaction.commit()
        return self._details(plan, paycheck, source), True

    def get(self, user: User, plan_id: uuid.UUID) -> PlanDetails:
        """Raises ``NotFoundError``, also when the plan is another user's."""
        plan = self._plans.get(user.id, plan_id)
        if plan is None:
            raise NotFoundError()
        paycheck = self._paychecks.get(user.id, plan.paycheck_id)
        assert paycheck is not None  # a plan cannot outlive its paycheck (RESTRICT)
        source = self._income_sources.get_including_archived(user.id, paycheck.income_source_id)
        assert source is not None  # nor a paycheck its source
        return self._details(plan, paycheck, source)

    def commit(self, user: User, plan_id: uuid.UUID) -> PlanDetails:
        """Accept a draft: what it funded becomes reserves (ADR 0003).

        Each funded bill, debt, and goal line is added to that target's reserve,
        and a goal's line also to its progress. Essentials are spending money and
        reserve nothing. Committing a plan that is already committed changes
        nothing and returns it, so a retried request is harmless.

        The plan must still be what the engine would say today: its inputs are
        hashed again (as of the day the plan was made for) and compared.

        Raises ``NotFoundError``; ``PlanSupersededError`` for a replaced draft;
        ``PaycheckAlreadyCommittedError`` if another plan for the paycheck is
        committed; ``PlanOutOfDateError`` if anything the plan was built from has
        changed, including its income source being archived.
        """
        self._users.lock(user.id)
        plan = self._plans.get(user.id, plan_id)
        if plan is None:
            raise NotFoundError()
        paycheck = self._paychecks.get(user.id, plan.paycheck_id)
        assert paycheck is not None  # a plan cannot outlive its paycheck (RESTRICT)
        if plan.status is PlanStatus.COMMITTED:
            return self.get(user, plan_id)
        if plan.status is PlanStatus.SUPERSEDED:
            raise PlanSupersededError()
        versions = self._plans.list_for_paycheck(user.id, paycheck.id)
        if any(other.status is PlanStatus.COMMITTED for other in versions):
            raise PaycheckAlreadyCommittedError()
        source = self._income_sources.get(user.id, paycheck.income_source_id)
        if source is None:
            raise PlanOutOfDateError()
        inputs = self._state.load(user)
        if input_hash(inputs.state, to_engine_paycheck(paycheck), plan.as_of) != plan.input_hash:
            raise PlanOutOfDateError()

        for line in self._plans.allocations(user.id, plan.id):
            self._reserve(user.id, line)
        plan.status = PlanStatus.COMMITTED
        plan.committed_at = self._clock()
        self._transaction.commit()
        return self._details(plan, paycheck, source)

    def _reserve(self, user_id: uuid.UUID, line: Allocation) -> None:
        """Turn one funded line of a plan being committed into money set aside."""
        kind = _RESERVE_KIND.get(line.tier)
        if kind is None or line.funded_cents == 0:
            return
        target_id = allocation_target(line)
        assert target_id is not None  # the hash matched, so every target still exists
        add_to_reserve(self._reserves, user_id, kind, target_id, line.funded_cents)
        if kind is ReserveKind.GOAL:
            goal = self._goals.get(user_id, target_id)
            assert goal is not None
            goal.current_cents += line.funded_cents

    def _details(self, plan: PaycheckPlan, paycheck: Paycheck, source: IncomeSource) -> PlanDetails:
        return describe(
            plan,
            paycheck,
            source,
            self._plans.allocations(plan.user_id, plan.id),
            self._plans.projections(plan.user_id, plan.id),
        )
