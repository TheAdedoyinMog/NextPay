"""Storage for income sources."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import IncomeSourceInUseError
from app.models import IncomeSource
from app.repositories.owned import UserOwnedRepository


class IncomeSourceRepository(UserOwnedRepository[IncomeSource]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, IncomeSource, order_by=(IncomeSource.name,))

    def delete(self, row: IncomeSource) -> None:
        """Delete ``row``. Raises ``IncomeSourceInUseError`` if it has paychecks.

        The database decides (paychecks reference their source with RESTRICT),
        so a paycheck recorded while this request runs is still caught.
        """
        try:
            with self._session.begin_nested():
                self._session.delete(row)
        except IntegrityError as error:
            # The only way deleting a row can break integrity: something still points at it.
            raise IncomeSourceInUseError() from error
