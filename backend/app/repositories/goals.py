"""Storage for goals, including purchases (ADR 0004)."""

import psycopg
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import EmergencyGoalExistsError
from app.models import Goal
from app.repositories.owned import UserOwnedRepository

_ONE_EMERGENCY = "ix_goals_one_emergency_per_user"


class GoalRepository(UserOwnedRepository[Goal]):
    def __init__(self, session: Session) -> None:
        # Most important first, as the planner funds them.
        super().__init__(session, Goal, order_by=(Goal.priority, Goal.name))

    def add(self, row: Goal) -> Goal:
        """Insert ``row``. Raises ``EmergencyGoalExistsError`` for a second emergency
        goal, including when a concurrent request created the first one."""
        try:
            with self._session.begin_nested():
                self._session.add(row)
        except IntegrityError as error:
            _raise_if_second_emergency(error)
            raise
        return row

    def save(self) -> None:
        """Write pending changes to goals now, so a conflict surfaces here and
        not at commit. Raises ``EmergencyGoalExistsError``; the transaction is
        then rolled back."""
        try:
            self._session.flush()
        except IntegrityError as error:
            _raise_if_second_emergency(error)
            raise


def _raise_if_second_emergency(error: IntegrityError) -> None:
    cause = error.orig
    if isinstance(cause, psycopg.Error) and cause.diag.constraint_name == _ONE_EMERGENCY:
        raise EmergencyGoalExistsError() from error
