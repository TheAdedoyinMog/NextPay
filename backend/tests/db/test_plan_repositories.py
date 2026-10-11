"""PlanRepository and ReserveRepository against a real PostgreSQL."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Allocation,
    Bill,
    BillPayment,
    Debt,
    DebtPayment,
    Goal,
    GoalProjection,
    IncomeSource,
    Paycheck,
    PaycheckPlan,
    PayFrequency,
    PlanStatus,
    Reserve,
    User,
)
from app.repositories import (
    BillPaymentRepository,
    DebtPaymentRepository,
    PlanRepository,
    ReserveRepository,
    UserRepository,
)
from nextpay_engine import GoalKind, GoalStatus, Reason, ReserveKind, Tier

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


class Setup:
    """One user with a job, two paychecks, a bill, a debt, and a goal."""

    def __init__(self, session: Session, email: str) -> None:
        self.user = UserRepository(session).add(User(email=email))
        owner = {"user_id": self.user.id}
        self.job = IncomeSource(
            name="Day job",
            expected_amount_cents=150_000,
            pay_frequency=PayFrequency.BIWEEKLY,
            anchor_date=date(2026, 10, 2),
            **owner,
        )
        self.rent = Bill(
            name="Rent",
            amount_cents=80_000,
            priority=1,
            first_due_date=date(2026, 10, 20),
            repeat_every_months=1,
            **owner,
        )
        self.car = Debt(
            name="Car loan",
            balance_cents=900_000,
            apr_bps=699,
            minimum_payment_cents=15_000,
            due_day=20,
            **owner,
        )
        self.camera = Goal(
            name="Camera",
            kind=GoalKind.PURCHASE,
            target_cents=200_000,
            current_cents=0,
            priority=2,
            **owner,
        )
        session.add_all([self.job, self.rent, self.car, self.camera])
        session.flush()
        self.first = Paycheck(
            income_source_id=self.job.id,
            pay_date=date(2026, 10, 2),
            expected_amount_cents=150_000,
            **owner,
        )
        self.second = Paycheck(
            income_source_id=self.job.id,
            pay_date=date(2026, 10, 16),
            expected_amount_cents=150_000,
            **owner,
        )
        session.add_all([self.first, self.second])
        session.flush()

    def plan(
        self, paycheck: Paycheck, version: int, status: PlanStatus = PlanStatus.DRAFT
    ) -> PaycheckPlan:
        return PaycheckPlan(
            user_id=self.user.id,
            paycheck_id=paycheck.id,
            version=version,
            status=status,
            committed_at=NOW if status is PlanStatus.COMMITTED else None,
            engine_version="0.2.0",
            input_hash="a" * 64,
            as_of=date(2026, 10, 7),
            next_pay_date=date(2026, 10, 16),
            paycheck_amount_cents=150_000,
            available_balance_cents=0,
            safe_to_spend_cents=100_000,
            reserve_deficit_cents=0,
        )

    def lines(self, plan: PaycheckPlan) -> tuple[list[Allocation], list[GoalProjection]]:
        """Two allocations and a projection, given out of order on purpose."""
        goal_line = Allocation(
            user_id=self.user.id,
            plan_id=plan.id,
            position=1,
            tier=Tier.GOAL,
            goal_id=self.camera.id,
            requested_cents=6_667,
            funded_cents=6_667,
            reason=Reason.GOAL_NO_DEADLINE,
            name="Camera",
            total_cents=200_000,
            set_aside_cents=0,
            share_bps=2000,
        )
        bill_line = Allocation(
            user_id=self.user.id,
            plan_id=plan.id,
            position=0,
            tier=Tier.BILL,
            bill_id=self.rent.id,
            requested_cents=40_000,
            funded_cents=40_000,
            reason=Reason.BILL_DUE,
            name="Rent",
            total_cents=80_000,
            set_aside_cents=0,
            due_date=date(2026, 10, 20),
            paychecks=2,
        )
        projection = GoalProjection(
            user_id=self.user.id,
            plan_id=plan.id,
            position=0,
            goal_id=self.camera.id,
            name="Camera",
            contribution_cents=6_667,
            still_needed_cents=193_333,
            status=GoalStatus.NO_DEADLINE,
        )
        return [goal_line, bill_line], [projection]


@pytest.fixture
def ada(db_session: Session) -> Setup:
    return Setup(db_session, "ada@example.com")


@pytest.fixture
def bob(db_session: Session) -> Setup:
    return Setup(db_session, "bob@example.com")


# --- plans ---------------------------------------------------------------------


def test_a_plan_is_stored_with_its_lines_in_order(db_session: Session, ada: Setup) -> None:
    plans = PlanRepository(db_session)
    plan = ada.plan(ada.first, 1)
    plan.id = uuid.uuid4()
    allocations, projections = ada.lines(plan)

    assert plans.add_plan(plan, allocations, projections) is plan

    assert plans.get(ada.user.id, plan.id) is plan
    assert [line.name for line in plans.allocations(ada.user.id, plan.id)] == ["Rent", "Camera"]
    assert [line.name for line in plans.projections(ada.user.id, plan.id)] == ["Camera"]
    assert plan.created_at is not None and plan.balance_as_of is None


def test_a_plan_and_its_lines_are_only_visible_to_their_owner(
    db_session: Session, ada: Setup, bob: Setup
) -> None:
    plans = PlanRepository(db_session)
    plan = ada.plan(ada.first, 1)
    plan.id = uuid.uuid4()
    plans.add_plan(plan, *ada.lines(plan))

    assert plans.get(bob.user.id, plan.id) is None
    assert plans.allocations(bob.user.id, plan.id) == []
    assert plans.projections(bob.user.id, plan.id) == []
    assert plans.list_for_paycheck(bob.user.id, ada.first.id) == []
    assert plans.current_for_paychecks(bob.user.id, [ada.first.id]) == {}


def test_versions_of_a_paychecks_plan_are_listed_oldest_first(
    db_session: Session, ada: Setup
) -> None:
    plans = PlanRepository(db_session)
    third = plans.add(ada.plan(ada.first, 3))
    first = plans.add(ada.plan(ada.first, 1, PlanStatus.SUPERSEDED))
    second = plans.add(ada.plan(ada.first, 2, PlanStatus.SUPERSEDED))
    plans.add(ada.plan(ada.second, 1))

    assert plans.list_for_paycheck(ada.user.id, ada.first.id) == [first, second, third]
    assert plans.list_for_paycheck(ada.user.id, uuid.uuid4()) == []


def test_the_current_plan_is_the_newest_one_not_superseded(db_session: Session, ada: Setup) -> None:
    plans = PlanRepository(db_session)
    plans.add(ada.plan(ada.first, 1, PlanStatus.SUPERSEDED))
    committed = plans.add(ada.plan(ada.first, 2, PlanStatus.COMMITTED))
    plans.add(ada.plan(ada.second, 1, PlanStatus.SUPERSEDED))
    draft = plans.add(ada.plan(ada.second, 2))

    both = plans.current_for_paychecks(ada.user.id, [ada.first.id, ada.second.id])
    assert both == {ada.first.id: committed, ada.second.id: draft}
    assert plans.current_for_paychecks(ada.user.id, [ada.second.id]) == {ada.second.id: draft}
    assert plans.current_for_paychecks(ada.user.id, []) == {}
    assert plans.current_for_paychecks(ada.user.id, [uuid.uuid4()]) == {}


def test_a_paycheck_with_only_superseded_plans_has_no_current_plan(
    db_session: Session, ada: Setup
) -> None:
    plans = PlanRepository(db_session)
    plans.add(ada.plan(ada.first, 1, PlanStatus.SUPERSEDED))
    assert plans.current_for_paychecks(ada.user.id, [ada.first.id]) == {}


def test_the_database_allows_only_one_committed_plan_per_paycheck(
    db_session: Session, ada: Setup
) -> None:
    plans = PlanRepository(db_session)
    plans.add(ada.plan(ada.first, 1, PlanStatus.COMMITTED))
    with pytest.raises(IntegrityError, match="ix_paycheck_plans_one_committed_per_paycheck"):
        plans.add(ada.plan(ada.first, 2, PlanStatus.COMMITTED))


# --- payments ------------------------------------------------------------------


def test_a_bills_payments_are_listed_newest_first_for_its_owner_only(
    db_session: Session, ada: Setup, bob: Setup
) -> None:
    payments = BillPaymentRepository(db_session)

    def paid(setup: Setup, day: int) -> BillPayment:
        return payments.add(
            BillPayment(
                user_id=setup.user.id,
                bill_id=setup.rent.id,
                due_date=date(2026, 10, 20),
                paid_on=date(2026, 10, day),
                amount_cents=10_000,
            )
        )

    early, late, middle = paid(ada, 5), paid(ada, 25), paid(ada, 15)
    paid(bob, 30)

    assert payments.list_for_bill(ada.user.id, ada.rent.id) == [late, middle, early]
    assert payments.list_for_bill(ada.user.id, bob.rent.id) == []
    assert payments.list_for_bill(bob.user.id, ada.rent.id) == []
    assert payments.list_for_bill(ada.user.id, uuid.uuid4()) == []


def test_a_debts_payments_are_listed_newest_first_for_its_owner_only(
    db_session: Session, ada: Setup, bob: Setup
) -> None:
    payments = DebtPaymentRepository(db_session)

    def paid(setup: Setup, day: int) -> DebtPayment:
        return payments.add(
            DebtPayment(
                user_id=setup.user.id,
                debt_id=setup.car.id,
                paid_on=date(2026, 10, day),
                amount_cents=15_000,
            )
        )

    early, late, middle = paid(ada, 5), paid(ada, 25), paid(ada, 15)
    paid(bob, 30)

    assert payments.list_for_debt(ada.user.id, ada.car.id) == [late, middle, early]
    assert payments.list_for_debt(ada.user.id, bob.car.id) == []
    assert payments.list_for_debt(bob.user.id, ada.car.id) == []


# --- reserves ------------------------------------------------------------------


def test_a_reserve_is_found_by_its_target_for_its_owner_only(
    db_session: Session, ada: Setup, bob: Setup
) -> None:
    reserves = ReserveRepository(db_session)
    owner = {"user_id": ada.user.id}
    for_rent = reserves.add(
        Reserve(kind=ReserveKind.BILL, bill_id=ada.rent.id, amount_cents=40_000, **owner)
    )
    for_car = reserves.add(
        Reserve(kind=ReserveKind.DEBT, debt_id=ada.car.id, amount_cents=7_500, **owner)
    )
    for_camera = reserves.add(
        Reserve(kind=ReserveKind.GOAL, goal_id=ada.camera.id, amount_cents=6_667, **owner)
    )
    reserves.add(
        Reserve(user_id=bob.user.id, kind=ReserveKind.BILL, bill_id=bob.rent.id, amount_cents=1)
    )

    assert reserves.find(ada.user.id, ReserveKind.BILL, ada.rent.id) is for_rent
    assert reserves.find(ada.user.id, ReserveKind.DEBT, ada.car.id) is for_car
    assert reserves.find(ada.user.id, ReserveKind.GOAL, ada.camera.id) is for_camera
    # The id must be of the kind asked for, and the reserve must be the user's.
    assert reserves.find(ada.user.id, ReserveKind.GOAL, ada.rent.id) is None
    assert reserves.find(ada.user.id, ReserveKind.BILL, uuid.uuid4()) is None
    assert reserves.find(bob.user.id, ReserveKind.BILL, ada.rent.id) is None
    assert set(reserves.list_for(ada.user.id)) == {for_rent, for_car, for_camera}
    assert len(reserves.list_for(bob.user.id)) == 1
