"""/goals: the signed-in user's goals, including purchases (ADR 0004, ADR 0010)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, GoalServiceDep
from app.api.errors import error_responses
from app.api.mappers import to_goal_input, to_goal_list_response, to_goal_response
from app.schemas.goals import GoalListResponse, GoalRequest, GoalResponse
from nextpay_engine import GoalKind

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 409, 422),
    summary="Add a goal",
    description="A second emergency goal is refused with 409 `emergency_goal_exists`.",
)
def create_goal(body: GoalRequest, user: CurrentUser, goals: GoalServiceDep) -> GoalResponse:
    return to_goal_response(goals.create(user.id, to_goal_input(body)))


@router.get("", responses=error_responses(401, 422), summary="List your goals")
def list_goals(
    user: CurrentUser,
    goals: GoalServiceDep,
    kind: Annotated[GoalKind | None, Query(description="Only goals of this kind.")] = None,
) -> GoalListResponse:
    return to_goal_list_response(goals.list_for(user.id, kind))


@router.get("/{goal_id}", responses=error_responses(401, 404, 422), summary="Get a goal")
def get_goal(goal_id: uuid.UUID, user: CurrentUser, goals: GoalServiceDep) -> GoalResponse:
    return to_goal_response(goals.get(user.id, goal_id))


@router.put(
    "/{goal_id}",
    responses=error_responses(401, 404, 409, 422),
    summary="Replace a goal",
    description=(
        "Send the whole goal: every field is replaced. Making it a second emergency goal "
        "is refused with 409 `emergency_goal_exists`."
    ),
)
def replace_goal(
    goal_id: uuid.UUID, body: GoalRequest, user: CurrentUser, goals: GoalServiceDep
) -> GoalResponse:
    return to_goal_response(goals.update(user.id, goal_id, to_goal_input(body)))


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 404, 422),
    summary="Delete a goal",
    description=(
        "Releases any money reserved for the goal: it counts toward Safe to Spend again. "
        "Past plans keep the goal's name."
    ),
)
def delete_goal(goal_id: uuid.UUID, user: CurrentUser, goals: GoalServiceDep) -> None:
    goals.delete(user.id, goal_id)
