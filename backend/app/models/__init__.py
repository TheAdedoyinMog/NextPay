"""SQLAlchemy models: the storage layer. Never returned by the API, never passed to the engine.

Importing this package registers every table on ``Base.metadata`` (Alembic relies on it).
"""

from app.models.balances import BalanceSnapshot
from app.models.bills import Bill, BillPayment
from app.models.goals import Goal
from app.models.income import IncomeSource, Paycheck, PayFrequency
from app.models.plans import Allocation, GoalProjection, PaycheckPlan, PlanStatus
from app.models.reserves import Reserve
from app.models.spending import Debt, EssentialExpense
from app.models.user import RefreshToken, User

__all__ = [
    "Allocation",
    "BalanceSnapshot",
    "Bill",
    "BillPayment",
    "Debt",
    "EssentialExpense",
    "Goal",
    "GoalProjection",
    "IncomeSource",
    "PayFrequency",
    "Paycheck",
    "PaycheckPlan",
    "PlanStatus",
    "RefreshToken",
    "Reserve",
    "User",
]
