"""Models and service results to response schemas, and request schemas to
service inputs, field by field.

Explicit on purpose: a new model column (a password hash, say) can only reach
a response if someone adds it here.
"""

from collections.abc import Iterable

from app.models import (
    BalanceSnapshot,
    Bill,
    Debt,
    EssentialExpense,
    Goal,
    IncomeSource,
    PayFrequency,
    User,
)
from app.schemas.auth import TokenResponse
from app.schemas.balances import BalanceSnapshotListResponse, BalanceSnapshotResponse
from app.schemas.bills import BillListResponse, BillRequest, BillResponse
from app.schemas.debts import DebtListResponse, DebtRequest, DebtResponse
from app.schemas.essential_expenses import (
    EssentialExpenseListResponse,
    EssentialExpenseRequest,
    EssentialExpenseResponse,
)
from app.schemas.goals import GoalListResponse, GoalRequest, GoalResponse
from app.schemas.income_sources import (
    BiweeklySchedule,
    IncomeSourceListResponse,
    IncomeSourceRequest,
    IncomeSourceResponse,
    MonthlySchedule,
    SemiMonthlySchedule,
    WeeklySchedule,
)
from app.schemas.user import UserResponse
from app.services.auth import TokenPair
from app.services.bills import BillInput
from app.services.debts import DebtInput
from app.services.essential_expenses import EssentialExpenseInput
from app.services.goals import GoalInput
from app.services.income_sources import IncomeSourceInput

type _Schedule = WeeklySchedule | BiweeklySchedule | SemiMonthlySchedule | MonthlySchedule


def to_token_response(tokens: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token,
    )


def to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id, email=user.email, timezone=user.timezone, created_at=user.created_at
    )


# --- bills ---------------------------------------------------------------------


def to_bill_input(body: BillRequest) -> BillInput:
    return BillInput(
        name=body.name,
        amount_cents=body.amount_cents,
        priority=body.priority,
        first_due_date=body.first_due_date,
        repeat_every_months=body.repeat_every_months,
    )


def to_bill_response(bill: Bill) -> BillResponse:
    return BillResponse(
        id=bill.id,
        name=bill.name,
        amount_cents=bill.amount_cents,
        priority=bill.priority,
        first_due_date=bill.first_due_date,
        repeat_every_months=bill.repeat_every_months,
        created_at=bill.created_at,
        updated_at=bill.updated_at,
    )


def to_bill_list_response(bills: Iterable[Bill]) -> BillListResponse:
    return BillListResponse(items=[to_bill_response(bill) for bill in bills])


# --- essential expenses --------------------------------------------------------


def to_essential_expense_input(body: EssentialExpenseRequest) -> EssentialExpenseInput:
    return EssentialExpenseInput(
        name=body.name, amount_per_period_cents=body.amount_per_period_cents
    )


def to_essential_expense_response(essential: EssentialExpense) -> EssentialExpenseResponse:
    return EssentialExpenseResponse(
        id=essential.id,
        name=essential.name,
        amount_per_period_cents=essential.amount_per_period_cents,
        created_at=essential.created_at,
        updated_at=essential.updated_at,
    )


def to_essential_expense_list_response(
    essentials: Iterable[EssentialExpense],
) -> EssentialExpenseListResponse:
    return EssentialExpenseListResponse(
        items=[to_essential_expense_response(essential) for essential in essentials]
    )


# --- debts ---------------------------------------------------------------------


def to_debt_input(body: DebtRequest) -> DebtInput:
    return DebtInput(
        name=body.name,
        balance_cents=body.balance_cents,
        apr_bps=body.apr_bps,
        minimum_payment_cents=body.minimum_payment_cents,
        due_day=body.due_day,
    )


def to_debt_response(debt: Debt) -> DebtResponse:
    return DebtResponse(
        id=debt.id,
        name=debt.name,
        balance_cents=debt.balance_cents,
        apr_bps=debt.apr_bps,
        minimum_payment_cents=debt.minimum_payment_cents,
        due_day=debt.due_day,
        created_at=debt.created_at,
        updated_at=debt.updated_at,
    )


def to_debt_list_response(debts: Iterable[Debt]) -> DebtListResponse:
    return DebtListResponse(items=[to_debt_response(debt) for debt in debts])


# --- income sources ------------------------------------------------------------


def to_income_source_input(body: IncomeSourceRequest) -> IncomeSourceInput:
    schedule = body.schedule
    if isinstance(schedule, WeeklySchedule | BiweeklySchedule):
        return IncomeSourceInput(
            name=body.name,
            expected_amount_cents=body.expected_amount_cents,
            pay_frequency=PayFrequency(schedule.type),
            anchor_date=schedule.anchor_date,
        )
    if isinstance(schedule, SemiMonthlySchedule):
        return IncomeSourceInput(
            name=body.name,
            expected_amount_cents=body.expected_amount_cents,
            pay_frequency=PayFrequency.SEMI_MONTHLY,
            day_of_month=schedule.first_day_of_month,
            second_day_of_month=schedule.second_day_of_month,
        )
    return IncomeSourceInput(
        name=body.name,
        expected_amount_cents=body.expected_amount_cents,
        pay_frequency=PayFrequency.MONTHLY,
        day_of_month=schedule.day_of_month,
    )


def _to_schedule(source: IncomeSource) -> _Schedule:
    # The table's CHECK guarantees each frequency has its own parameters.
    if source.pay_frequency is PayFrequency.WEEKLY:
        assert source.anchor_date is not None
        return WeeklySchedule(type="weekly", anchor_date=source.anchor_date)
    if source.pay_frequency is PayFrequency.BIWEEKLY:
        assert source.anchor_date is not None
        return BiweeklySchedule(type="biweekly", anchor_date=source.anchor_date)
    assert source.day_of_month is not None
    if source.pay_frequency is PayFrequency.SEMI_MONTHLY:
        assert source.second_day_of_month is not None
        return SemiMonthlySchedule(
            type="semi_monthly",
            first_day_of_month=source.day_of_month,
            second_day_of_month=source.second_day_of_month,
        )
    return MonthlySchedule(type="monthly", day_of_month=source.day_of_month)


def to_income_source_response(source: IncomeSource) -> IncomeSourceResponse:
    return IncomeSourceResponse(
        id=source.id,
        name=source.name,
        expected_amount_cents=source.expected_amount_cents,
        schedule=_to_schedule(source),
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def to_income_source_list_response(sources: Iterable[IncomeSource]) -> IncomeSourceListResponse:
    return IncomeSourceListResponse(items=[to_income_source_response(source) for source in sources])


# --- goals ---------------------------------------------------------------------


def to_goal_input(body: GoalRequest) -> GoalInput:
    return GoalInput(
        name=body.name,
        kind=body.kind,
        target_cents=body.target_cents,
        current_cents=body.current_cents,
        priority=body.priority,
        deadline=body.deadline,
    )


def to_goal_response(goal: Goal) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        name=goal.name,
        kind=goal.kind,
        target_cents=goal.target_cents,
        current_cents=goal.current_cents,
        priority=goal.priority,
        deadline=goal.deadline,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


def to_goal_list_response(goals: Iterable[Goal]) -> GoalListResponse:
    return GoalListResponse(items=[to_goal_response(goal) for goal in goals])


# --- balance snapshots ---------------------------------------------------------


def to_balance_snapshot_response(snapshot: BalanceSnapshot) -> BalanceSnapshotResponse:
    return BalanceSnapshotResponse(
        id=snapshot.id,
        amount_cents=snapshot.amount_cents,
        as_of=snapshot.as_of,
        created_at=snapshot.created_at,
    )


def to_balance_snapshot_list_response(
    snapshots: Iterable[BalanceSnapshot],
) -> BalanceSnapshotListResponse:
    return BalanceSnapshotListResponse(
        items=[to_balance_snapshot_response(snapshot) for snapshot in snapshots]
    )
