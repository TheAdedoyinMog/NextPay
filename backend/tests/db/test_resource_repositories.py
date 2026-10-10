"""What the income source, goal, and balance snapshot repositories add to
UserOwnedRepository, against a real PostgreSQL."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import EmergencyGoalExistsError, IncomeSourceInUseError
from app.models import BalanceSnapshot, Goal, IncomeSource, Paycheck, PayFrequency, User
from app.repositories import (
    BalanceSnapshotRepository,
    GoalRepository,
    IncomeSourceRepository,
    UserRepository,
)
from nextpay_engine import GoalKind

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def two_users(session: Session) -> tuple[User, User]:
    users = UserRepository(session)
    return users.add(User(email="ada@example.com")), users.add(User(email="bob@example.com"))


def make_source(user: User, name: str = "Day job") -> IncomeSource:
    return IncomeSource(
        user_id=user.id,
        name=name,
        expected_amount_cents=150_000,
        pay_frequency=PayFrequency.BIWEEKLY,
        anchor_date=date(2026, 10, 2),
    )


def make_goal(user: User, name: str = "Camera", kind: GoalKind = GoalKind.PURCHASE) -> Goal:
    return Goal(
        user_id=user.id, name=name, kind=kind, target_cents=200_000, current_cents=0, priority=2
    )


# --- income sources ------------------------------------------------------------


def test_a_source_without_paychecks_is_deleted(db_session: Session) -> None:
    ada, _ = two_users(db_session)
    sources = IncomeSourceRepository(db_session)
    job = sources.add(make_source(ada))
    sources.delete(job)
    assert sources.list_for(ada.id) == []


def test_a_source_with_paychecks_is_kept_and_the_transaction_survives(
    db_session: Session,
) -> None:
    ada, _ = two_users(db_session)
    sources = IncomeSourceRepository(db_session)
    job = sources.add(make_source(ada))
    db_session.add(
        Paycheck(
            user_id=ada.id,
            income_source_id=job.id,
            pay_date=date(2026, 10, 2),
            expected_amount_cents=150_000,
        )
    )
    db_session.flush()

    with pytest.raises(IncomeSourceInUseError):
        sources.delete(job)

    # Only the savepoint was rolled back; the source and the session are intact.
    assert sources.get(ada.id, job.id) is job
    side_job = sources.add(make_source(ada, "Side job"))
    sources.delete(side_job)
    assert sources.list_for(ada.id) == [job]


# --- goals ---------------------------------------------------------------------


def test_goals_are_listed_by_priority_then_name(db_session: Session) -> None:
    ada, bob = two_users(db_session)
    goals = GoalRepository(db_session)
    goals.add(make_goal(ada, "Trip"))
    goals.add(make_goal(ada, "Camera"))
    fund = make_goal(ada, "Emergency fund", GoalKind.EMERGENCY)
    fund.priority = 1
    goals.add(fund)
    goals.add(make_goal(bob, "Bob's bike"))

    assert [goal.name for goal in goals.list_for(ada.id)] == ["Emergency fund", "Camera", "Trip"]


def test_a_second_emergency_goal_raises_without_breaking_the_transaction(
    db_session: Session,
) -> None:
    ada, bob = two_users(db_session)
    goals = GoalRepository(db_session)
    fund = goals.add(make_goal(ada, "Emergency fund", GoalKind.EMERGENCY))

    with pytest.raises(EmergencyGoalExistsError):
        goals.add(make_goal(ada, "Another", GoalKind.EMERGENCY))

    # Only the savepoint was rolled back. Another user's emergency goal is no conflict.
    assert goals.list_for(ada.id) == [fund]
    goals.add(make_goal(bob, "Bob's fund", GoalKind.EMERGENCY))
    goals.add(make_goal(ada, "Camera"))


def test_save_raises_when_a_goal_becomes_a_second_emergency_goal(db_session: Session) -> None:
    ada, _ = two_users(db_session)
    goals = GoalRepository(db_session)
    goals.add(make_goal(ada, "Emergency fund", GoalKind.EMERGENCY))
    camera = goals.add(make_goal(ada))
    goals.save()  # nothing pending: no error

    camera.kind = GoalKind.EMERGENCY
    with pytest.raises(EmergencyGoalExistsError):
        goals.save()


def test_other_integrity_errors_are_not_mistaken_for_a_second_emergency_goal(
    db_session: Session,
) -> None:
    ada, _ = two_users(db_session)
    goals = GoalRepository(db_session)
    with pytest.raises(IntegrityError):
        goals.add(make_goal(ada, name="   "))

    camera = goals.add(make_goal(ada))
    camera.target_cents = 0
    with pytest.raises(IntegrityError):
        goals.save()


# --- balance snapshots ---------------------------------------------------------


def test_latest_is_newest_first_limited_and_scoped(db_session: Session) -> None:
    ada, bob = two_users(db_session)
    snapshots = BalanceSnapshotRepository(db_session)
    for days, cents in enumerate([100, 200, 300]):
        snapshots.add(
            BalanceSnapshot(user_id=ada.id, amount_cents=cents, as_of=NOW + timedelta(days=days))
        )
    snapshots.add(BalanceSnapshot(user_id=bob.id, amount_cents=999, as_of=NOW + timedelta(days=9)))

    assert [s.amount_cents for s in snapshots.latest(ada.id, 10)] == [300, 200, 100]
    assert [s.amount_cents for s in snapshots.latest(ada.id, 2)] == [300, 200]
    assert [s.amount_cents for s in snapshots.latest(bob.id, 10)] == [999]
    assert snapshots.latest(uuid.uuid4(), 10) == []


def test_snapshots_with_the_same_time_still_have_a_stable_order(db_session: Session) -> None:
    ada, _ = two_users(db_session)
    snapshots = BalanceSnapshotRepository(db_session)
    for cents in (100, 200, 300):
        snapshots.add(BalanceSnapshot(user_id=ada.id, amount_cents=cents, as_of=NOW))

    first = [s.id for s in snapshots.latest(ada.id, 10)]
    assert [s.id for s in snapshots.latest(ada.id, 10)] == first
    assert first == sorted(first, reverse=True)
