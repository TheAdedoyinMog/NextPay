"""Goals, including purchases (ADR 0004): create, list, get, update, delete.

A user has at most one emergency goal. Deleting a goal also deletes its
reserve (the database cascades), which releases the reserved money: the next
Safe to Spend no longer subtracts it (ADR 0003, ADR 0010). Plans that mention
the goal keep its name and lose only the link.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.core.errors import NotFoundError
from app.models import Goal
from app.services.engine_mapping import to_engine_goal, validated
from app.services.protocols import OwnedStore, Transaction
from nextpay_engine import GoalKind


class GoalStore(OwnedStore[Goal], Protocol):
    """``add`` and ``save`` raise ``EmergencyGoalExistsError`` for a second emergency goal."""

    def save(self) -> None: ...


@dataclass(frozen=True, slots=True)
class GoalInput:
    """Everything a user sets on a goal. Create and update both take all of it."""

    name: str
    kind: GoalKind
    target_cents: int
    # Saved so far; may exceed the target once it is reached.
    current_cents: int
    # 1 is the most important.
    priority: int
    # A deadline that has passed is allowed: the planner flags it.
    deadline: date | None


class GoalService:
    def __init__(self, *, goals: GoalStore, transaction: Transaction) -> None:
        self._goals = goals
        self._transaction = transaction

    def create(self, user_id: uuid.UUID, data: GoalInput) -> Goal:
        """Raises ``InvalidInputError`` or ``EmergencyGoalExistsError``."""
        goal = validated(_fill(Goal(id=uuid.uuid4(), user_id=user_id), data), to_engine_goal)
        self._goals.add(goal)
        self._transaction.commit()
        return goal

    def list_for(self, user_id: uuid.UUID, kind: GoalKind | None = None) -> Sequence[Goal]:
        """The user's goals, or only those of one ``kind``."""
        goals = self._goals.list_for(user_id)
        return goals if kind is None else [goal for goal in goals if goal.kind is kind]

    def get(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> Goal:
        """Raises ``NotFoundError``, also when the goal is another user's."""
        goal = self._goals.get(user_id, goal_id)
        if goal is None:
            raise NotFoundError()
        return goal

    def update(self, user_id: uuid.UUID, goal_id: uuid.UUID, data: GoalInput) -> Goal:
        """Replace every field. Raises ``NotFoundError``, ``InvalidInputError``, or
        ``EmergencyGoalExistsError``."""
        goal = self.get(user_id, goal_id)
        # Check a copy first, so a rejected update never touches the stored goal.
        validated(_fill(Goal(id=goal.id, user_id=user_id), data), to_engine_goal)
        _fill(goal, data)
        self._goals.save()
        self._transaction.commit()
        return goal

    def delete(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> None:
        """Raises ``NotFoundError``."""
        self._goals.delete(self.get(user_id, goal_id))
        self._transaction.commit()


def _fill(goal: Goal, data: GoalInput) -> Goal:
    goal.name = data.name
    goal.kind = data.kind
    goal.target_cents = data.target_cents
    goal.current_cents = data.current_cents
    goal.priority = data.priority
    goal.deadline = data.deadline
    return goal
