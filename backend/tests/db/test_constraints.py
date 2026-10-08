"""The database enforces the rules that keep data valid and users apart.

Each rejection test names the constraint it expects, so a test cannot pass
because some other constraint happened to fire.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime

import psycopg
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Allocation,
    Bill,
    Goal,
    IncomeSource,
    Paycheck,
    PaycheckPlan,
    PayFrequency,
    PlanStatus,
    Reserve,
    User,
)
from nextpay_engine import GoalKind, Reason, ReserveKind, Tier

HASH = "0" * 64


@contextmanager
def violates(session: Session, constraint: str) -> Iterator[None]:
    """Expect the block's flush to be rejected by ``constraint``."""
    with pytest.raises(IntegrityError) as error:
        yield
        session.flush()
    session.rollback()
    cause = error.value.orig
    assert isinstance(cause, psycopg.Error)
    assert cause.diag.constraint_name == constraint


def add_user(session: Session, email: str = "ada@example.com") -> User:
    user = User(email=email)
    session.add(user)
    session.flush()
    return user


def add_income_source(session: Session, user: User) -> IncomeSource:
    source = IncomeSource(
        user_id=user.id,
        name="Job",
        expected_amount_cents=150_000,
        pay_frequency=PayFrequency.BIWEEKLY,
        anchor_date=date(2026, 10, 2),
    )
    session.add(source)
    session.flush()
    return source


def add_goal(session: Session, user: User, kind: GoalKind = GoalKind.SAVINGS) -> Goal:
    goal = Goal(
        user_id=user.id, name="Camera", kind=kind, target_cents=200_000, current_cents=0, priority=1
    )
    session.add(goal)
    session.flush()
    return goal


def add_plan(session: Session, user: User) -> PaycheckPlan:
    source = add_income_source(session, user)
    paycheck = Paycheck(
        user_id=user.id,
        income_source_id=source.id,
        pay_date=date(2026, 10, 2),
        expected_amount_cents=150_000,
    )
    session.add(paycheck)
    session.flush()
    plan = PaycheckPlan(
        user_id=user.id,
        paycheck_id=paycheck.id,
        version=1,
        status=PlanStatus.DRAFT,
        engine_version="0.2.0",
        input_hash=HASH,
        as_of=date(2026, 10, 2),
        next_pay_date=date(2026, 10, 16),
        paycheck_amount_cents=150_000,
        available_balance_cents=0,
        safe_to_spend_cents=75_833,
        reserve_deficit_cents=0,
    )
    session.add(plan)
    session.flush()
    return plan


def goal_allocation(user: User, plan: PaycheckPlan, goal: Goal) -> Allocation:
    return Allocation(
        user_id=user.id,
        plan_id=plan.id,
        position=0,
        tier=Tier.GOAL,
        goal_id=goal.id,
        requested_cents=6_667,
        funded_cents=6_667,
        reason=Reason.GOAL_DEADLINE,
        name=goal.name,
        total_cents=200_000,
        set_aside_cents=0,
        due_date=date(2027, 12, 1),
        paychecks=30,
    )


# --- Values ------------------------------------------------------------------


def test_timestamps_and_defaults_are_filled_in(db_session: Session) -> None:
    user = add_user(db_session)
    db_session.refresh(user)
    assert user.timezone == "UTC"
    assert user.no_deadline_goal_share_bps == 2000
    assert user.created_at.tzinfo is not None
    assert isinstance(user.id, uuid.UUID)


def test_enums_are_stored_as_the_engines_values(db_session: Session) -> None:
    user = add_user(db_session)
    add_goal(db_session, user, GoalKind.PURCHASE)
    assert db_session.execute(text("SELECT kind FROM goals")).scalar_one() == "purchase"
    assert db_session.execute(select(Goal.kind)).scalar_one() is GoalKind.PURCHASE


def test_money_columns_hold_more_than_32_bits(db_session: Session) -> None:
    user = add_user(db_session)
    goal = add_goal(db_session, user)
    goal.target_cents = 2**40
    db_session.flush()
    db_session.expire(goal)
    assert goal.target_cents == 2**40


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("amount_cents", 0, "ck_bills_amount_positive"),
        ("amount_cents", -100, "ck_bills_amount_positive"),
        ("priority", 0, "ck_bills_priority_positive"),
        ("name", "   ", "ck_bills_name_not_blank"),
        ("repeat_every_months", 0, "ck_bills_repeat_every_months_positive"),
    ],
)
def test_invalid_bill_values_are_rejected(
    db_session: Session, field: str, value: object, constraint: str
) -> None:
    user = add_user(db_session)
    values: dict[str, object] = {
        "name": "Rent",
        "amount_cents": 80_000,
        "priority": 1,
        "first_due_date": date(2026, 10, 20),
        field: value,
    }
    with violates(db_session, constraint):
        db_session.add(Bill(user_id=user.id, **values))


def test_email_must_be_stored_lowercase(db_session: Session) -> None:
    with violates(db_session, "ck_users_email_lowercase"):
        db_session.add(User(email="Ada@Example.com"))


@pytest.mark.parametrize(
    "schedule",
    [
        {"pay_frequency": PayFrequency.BIWEEKLY},  # no anchor
        {"pay_frequency": PayFrequency.MONTHLY, "day_of_month": 1, "second_day_of_month": 15},
        {"pay_frequency": PayFrequency.SEMI_MONTHLY, "day_of_month": 15, "second_day_of_month": 1},
        {"pay_frequency": PayFrequency.WEEKLY, "anchor_date": date(2026, 10, 2), "day_of_month": 1},
    ],
)
def test_a_schedule_must_carry_exactly_its_own_parameters(
    db_session: Session, schedule: dict[str, object]
) -> None:
    user = add_user(db_session)
    with violates(db_session, "ck_income_sources_schedule_parameters"):
        db_session.add(
            IncomeSource(user_id=user.id, name="Job", expected_amount_cents=1, **schedule)
        )


def test_a_user_has_at_most_one_emergency_goal(db_session: Session) -> None:
    user = add_user(db_session)
    add_goal(db_session, user, GoalKind.EMERGENCY)
    add_goal(db_session, user, GoalKind.SAVINGS)
    with violates(db_session, "ix_goals_one_emergency_per_user"):
        db_session.add(
            Goal(
                user_id=user.id,
                name="Rainy day",
                kind=GoalKind.EMERGENCY,
                target_cents=100_000,
                current_cents=0,
                priority=1,
            )
        )


def test_a_reserve_must_point_at_the_target_its_kind_names(db_session: Session) -> None:
    user = add_user(db_session)
    goal = add_goal(db_session, user)
    with violates(db_session, "ck_reserves_target_matches_kind"):
        db_session.add(
            Reserve(user_id=user.id, kind=ReserveKind.BILL, goal_id=goal.id, amount_cents=1)
        )


def test_an_allocation_may_only_point_at_its_tiers_target(db_session: Session) -> None:
    user = add_user(db_session)
    plan = add_plan(db_session, user)
    allocation = goal_allocation(user, plan, add_goal(db_session, user))
    allocation.tier = Tier.BILL
    with violates(db_session, "ck_allocations_target_matches_tier"):
        db_session.add(allocation)


def test_an_allocation_cannot_be_funded_beyond_its_request(db_session: Session) -> None:
    user = add_user(db_session)
    plan = add_plan(db_session, user)
    allocation = goal_allocation(user, plan, add_goal(db_session, user))
    allocation.funded_cents = allocation.requested_cents + 1
    with violates(db_session, "ck_allocations_funded_range"):
        db_session.add(allocation)


def test_a_paycheck_has_one_committed_plan(db_session: Session) -> None:
    user = add_user(db_session)
    first = add_plan(db_session, user)
    first.status, first.committed_at = PlanStatus.COMMITTED, datetime.now(UTC)
    db_session.flush()
    with violates(db_session, "ix_paycheck_plans_one_committed_per_paycheck"):
        db_session.add(
            PaycheckPlan(
                user_id=user.id,
                paycheck_id=first.paycheck_id,
                version=2,
                status=PlanStatus.COMMITTED,
                committed_at=datetime.now(UTC),
                engine_version="0.2.0",
                input_hash=HASH,
                as_of=first.as_of,
                next_pay_date=first.next_pay_date,
                paycheck_amount_cents=150_000,
                available_balance_cents=0,
                safe_to_spend_cents=0,
                reserve_deficit_cents=0,
            )
        )


# --- Tenant isolation (composite foreign keys) --------------------------------


def test_a_paycheck_cannot_use_another_users_income_source(db_session: Session) -> None:
    ada, bob = add_user(db_session), add_user(db_session, "bob@example.com")
    adas_job = add_income_source(db_session, ada)
    with violates(db_session, "fk_paychecks_user_id_income_source_id_income_sources"):
        db_session.add(
            Paycheck(
                user_id=bob.id,
                income_source_id=adas_job.id,
                pay_date=date(2026, 10, 2),
                expected_amount_cents=150_000,
            )
        )


def test_an_allocation_cannot_point_at_another_users_goal(db_session: Session) -> None:
    ada, bob = add_user(db_session), add_user(db_session, "bob@example.com")
    bobs_plan = add_plan(db_session, bob)
    with violates(db_session, "fk_allocations_user_id_goal_id_goals"):
        db_session.add(goal_allocation(bob, bobs_plan, add_goal(db_session, ada)))


# --- Deletes -------------------------------------------------------------------


def test_deleting_a_goal_releases_its_reserve_but_keeps_plan_history(
    db_session: Session,
) -> None:
    user = add_user(db_session)
    plan = add_plan(db_session, user)
    goal = add_goal(db_session, user)
    allocation = goal_allocation(user, plan, goal)
    db_session.add_all(
        [
            allocation,
            Reserve(user_id=user.id, kind=ReserveKind.GOAL, goal_id=goal.id, amount_cents=6_667),
        ]
    )
    db_session.flush()

    db_session.delete(goal)
    db_session.flush()
    db_session.expire_all()

    assert db_session.scalars(select(Reserve)).all() == []
    kept = db_session.get_one(Allocation, allocation.id)
    assert kept.goal_id is None  # SET NULL (goal_id) clears only the target...
    assert kept.user_id == user.id  # ...never the owner
    assert kept.name == "Camera"


def test_an_income_source_with_paychecks_cannot_be_deleted(db_session: Session) -> None:
    user = add_user(db_session)
    plan = add_plan(db_session, user)
    source = db_session.get_one(Paycheck, plan.paycheck_id).income_source_id
    with violates(db_session, "fk_paychecks_user_id_income_source_id_income_sources"):
        db_session.execute(text("DELETE FROM income_sources WHERE id = :id"), {"id": source})


def test_deleting_a_user_deletes_all_their_data(db_session: Session) -> None:
    ada, bob = add_user(db_session), add_user(db_session, "bob@example.com")
    for user in (ada, bob):
        plan = add_plan(db_session, user)
        db_session.add(goal_allocation(user, plan, add_goal(db_session, user)))
    db_session.flush()

    db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": ada.id})

    for table in ("income_sources", "paychecks", "paycheck_plans", "allocations", "goals"):
        owners = db_session.execute(text(f"SELECT DISTINCT user_id FROM {table}")).scalars()
        assert list(owners) == [bob.id], table
