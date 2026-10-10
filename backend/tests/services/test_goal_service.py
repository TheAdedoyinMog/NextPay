"""GoalService rules, with in-memory fakes (see conftest.py)."""

import uuid
from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from app.core.errors import EmergencyGoalExistsError, InvalidInputError, NotFoundError
from app.services.goals import GoalInput, GoalService
from nextpay_engine import GoalKind

ADA = uuid.uuid4()
BOB = uuid.uuid4()
CAMERA = GoalInput(
    name="Camera",
    kind=GoalKind.PURCHASE,
    target_cents=200_000,
    current_cents=0,
    priority=2,
    deadline=date(2027, 12, 1),
)
EMERGENCY = GoalInput("Emergency fund", GoalKind.EMERGENCY, 100_000, 0, 1, None)

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


def test_create_stores_the_goal_for_its_user(
    goal_service: GoalService, goals: Fake, transaction: Fake
) -> None:
    camera = goal_service.create(ADA, CAMERA)

    assert goals.rows == {camera.id: camera}
    assert (camera.user_id, camera.name, camera.kind) == (ADA, "Camera", GoalKind.PURCHASE)
    assert (camera.target_cents, camera.current_cents) == (200_000, 0)
    assert (camera.priority, camera.deadline) == (2, date(2027, 12, 1))
    assert transaction.commits == 1


@pytest.mark.parametrize(
    "change",
    [
        {"deadline": None},
        {"deadline": date(2020, 1, 1)},  # already passed: the planner flags it
        {"current_cents": 250_000},  # more than the target
        {"kind": GoalKind.SAVINGS},
    ],
)
def test_these_goals_are_valid(goal_service: GoalService, change: dict[str, Any]) -> None:
    goal_service.create(ADA, replace(CAMERA, **change))


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"kind": "purchase"},  # a string is not a GoalKind
        {"kind": "holiday"},
        {"target_cents": 0},
        {"target_cents": -1},
        {"target_cents": True},
        {"current_cents": -1},
        {"priority": 0},
        {"deadline": "2027-12-01"},  # a string is not a date
    ],
)
def test_create_rejects_what_the_engine_would_reject(
    goal_service: GoalService, goals: Fake, transaction: Fake, change: dict[str, Any]
) -> None:
    with pytest.raises(InvalidInputError):
        goal_service.create(ADA, replace(CAMERA, **change))
    assert goals.rows == {}
    assert transaction.commits == 0


# --- one emergency goal per user -----------------------------------------------


def test_a_second_emergency_goal_is_refused(
    goal_service: GoalService, goals: Fake, transaction: Fake
) -> None:
    first = goal_service.create(ADA, EMERGENCY)
    with pytest.raises(EmergencyGoalExistsError):
        goal_service.create(ADA, replace(EMERGENCY, name="Another"))
    assert goals.rows == {first.id: first}
    assert transaction.commits == 1


def test_each_user_has_their_own_emergency_goal(goal_service: GoalService) -> None:
    goal_service.create(ADA, EMERGENCY)
    goal_service.create(BOB, EMERGENCY)


def test_a_goal_cannot_become_a_second_emergency_goal(
    goal_service: GoalService, transaction: Fake
) -> None:
    goal_service.create(ADA, EMERGENCY)
    camera = goal_service.create(ADA, CAMERA)
    with pytest.raises(EmergencyGoalExistsError):
        goal_service.update(ADA, camera.id, replace(CAMERA, kind=GoalKind.EMERGENCY))
    assert transaction.commits == 2


def test_the_emergency_goal_itself_can_be_updated(goal_service: GoalService) -> None:
    fund = goal_service.create(ADA, EMERGENCY)
    goal_service.update(ADA, fund.id, replace(EMERGENCY, target_cents=300_000))
    assert fund.target_cents == 300_000


# --- list and get --------------------------------------------------------------


def test_list_and_get_show_only_the_users_own(goal_service: GoalService) -> None:
    camera = goal_service.create(ADA, CAMERA)
    goal_service.create(BOB, replace(CAMERA, name="Bob's bike"))

    assert list(goal_service.list_for(ADA)) == [camera]
    assert goal_service.get(ADA, camera.id) is camera
    with pytest.raises(NotFoundError):
        goal_service.get(BOB, camera.id)
    with pytest.raises(NotFoundError):
        goal_service.get(ADA, uuid.uuid4())


def test_list_can_be_narrowed_to_one_kind(goal_service: GoalService) -> None:
    camera = goal_service.create(ADA, CAMERA)
    fund = goal_service.create(ADA, EMERGENCY)
    trip = goal_service.create(ADA, replace(CAMERA, name="Trip", kind=GoalKind.SAVINGS))
    goal_service.create(BOB, CAMERA)

    assert list(goal_service.list_for(ADA)) == [camera, fund, trip]
    assert list(goal_service.list_for(ADA, GoalKind.PURCHASE)) == [camera]
    assert list(goal_service.list_for(ADA, GoalKind.EMERGENCY)) == [fund]
    assert list(goal_service.list_for(BOB, GoalKind.SAVINGS)) == []


# --- update and delete ---------------------------------------------------------


def test_update_replaces_every_field(goal_service: GoalService, transaction: Fake) -> None:
    camera = goal_service.create(ADA, CAMERA)
    new = GoalInput("Trip", GoalKind.SAVINGS, 500_000, 40_000, 1, None)

    updated = goal_service.update(ADA, camera.id, new)

    assert updated is camera
    assert (camera.name, camera.kind) == ("Trip", GoalKind.SAVINGS)
    assert (camera.target_cents, camera.current_cents) == (500_000, 40_000)
    assert (camera.priority, camera.deadline) == (1, None)
    assert transaction.commits == 2


def test_a_rejected_update_leaves_the_goal_untouched(
    goal_service: GoalService, transaction: Fake
) -> None:
    camera = goal_service.create(ADA, CAMERA)
    with pytest.raises(InvalidInputError):
        goal_service.update(ADA, camera.id, replace(CAMERA, name="Changed", target_cents=0))
    assert (camera.name, camera.target_cents) == ("Camera", 200_000)
    assert transaction.commits == 1


def test_update_and_delete_treat_another_users_goal_as_missing(
    goal_service: GoalService, goals: Fake, transaction: Fake
) -> None:
    camera = goal_service.create(ADA, CAMERA)
    with pytest.raises(NotFoundError):
        goal_service.update(BOB, camera.id, replace(CAMERA, name="Mine now"))
    with pytest.raises(NotFoundError):
        goal_service.delete(BOB, camera.id)
    assert goals.rows == {camera.id: camera}
    assert camera.name == "Camera"
    assert transaction.commits == 1


def test_delete_removes_the_goal(goal_service: GoalService, goals: Fake, transaction: Fake) -> None:
    camera = goal_service.create(ADA, CAMERA)
    goal_service.delete(ADA, camera.id)
    assert goals.rows == {}
    assert transaction.commits == 2
