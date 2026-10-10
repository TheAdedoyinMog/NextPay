"""Storage for essential expenses and debts."""

from sqlalchemy.orm import Session

from app.models import Debt, EssentialExpense
from app.repositories.owned import UserOwnedRepository


class EssentialExpenseRepository(UserOwnedRepository[EssentialExpense]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, EssentialExpense, order_by=(EssentialExpense.name,))


class DebtRepository(UserOwnedRepository[Debt]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Debt, order_by=(Debt.name,))
