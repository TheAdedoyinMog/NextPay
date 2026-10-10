"""Storage for bills."""

from sqlalchemy.orm import Session

from app.models import Bill
from app.repositories.owned import UserOwnedRepository


class BillRepository(UserOwnedRepository[Bill]):
    def __init__(self, session: Session) -> None:
        # Most important first, as the planner funds them.
        super().__init__(session, Bill, order_by=(Bill.priority, Bill.first_due_date, Bill.name))
