"""Repositories: the only code that queries the database. One class per aggregate."""

from app.repositories.balances import BalanceSnapshotRepository
from app.repositories.bills import BillRepository
from app.repositories.goals import GoalRepository
from app.repositories.income_sources import IncomeSourceRepository
from app.repositories.owned import UserOwnedRepository
from app.repositories.paychecks import PaycheckRepository
from app.repositories.payments import BillPaymentRepository, DebtPaymentRepository
from app.repositories.plans import PlanRepository
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.reserves import ReserveRepository
from app.repositories.spending import DebtRepository, EssentialExpenseRepository
from app.repositories.users import UserRepository

__all__ = [
    "BalanceSnapshotRepository",
    "BillPaymentRepository",
    "BillRepository",
    "DebtPaymentRepository",
    "DebtRepository",
    "EssentialExpenseRepository",
    "GoalRepository",
    "IncomeSourceRepository",
    "PaycheckRepository",
    "PlanRepository",
    "RefreshTokenRepository",
    "ReserveRepository",
    "UserOwnedRepository",
    "UserRepository",
]
