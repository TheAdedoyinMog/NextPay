"""NextPay planning engine.

Pure and deterministic: no database, no network, no clock. The same inputs
always produce the same plan. See docs/adr/0002-engine-as-separate-package.md.
"""

from nextpay_engine.domain import (
    Bill,
    Debt,
    EssentialExpense,
    Goal,
    GoalKind,
    IncomeSource,
    Paycheck,
    Reserve,
    ReserveKind,
    paycheck_timeline,
)
from nextpay_engine.explanations import explain_allocation, explain_plan, explain_projection
from nextpay_engine.money import Money
from nextpay_engine.pay_schedules import Biweekly, Monthly, PaySchedule, SemiMonthly, Weekly
from nextpay_engine.planning import (
    Allocation,
    Basis,
    GoalProjection,
    GoalStatus,
    PlanResult,
    Reason,
    Tier,
    plan_paycheck,
)
from nextpay_engine.recurrence import BillRecurrence, EveryNMonths, OneTime
from nextpay_engine.state import FinancialState

ENGINE_VERSION = "0.2.0"

__all__ = [
    "ENGINE_VERSION",
    "Allocation",
    "Basis",
    "Bill",
    "BillRecurrence",
    "Biweekly",
    "Debt",
    "EssentialExpense",
    "EveryNMonths",
    "FinancialState",
    "Goal",
    "GoalKind",
    "GoalProjection",
    "GoalStatus",
    "IncomeSource",
    "Money",
    "Monthly",
    "OneTime",
    "PaySchedule",
    "Paycheck",
    "PlanResult",
    "Reason",
    "Reserve",
    "ReserveKind",
    "SemiMonthly",
    "Tier",
    "Weekly",
    "explain_allocation",
    "explain_plan",
    "explain_projection",
    "paycheck_timeline",
    "plan_paycheck",
]
