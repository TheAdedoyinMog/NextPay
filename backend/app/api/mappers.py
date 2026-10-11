"""Models and service results to response schemas, and request schemas to
service inputs, field by field.

Explicit on purpose: a new model column (a password hash, say) can only reach
a response if someone adds it here.
"""

import uuid
from collections.abc import Iterable, Mapping

from app.models import (
    BalanceSnapshot,
    Bill,
    BillPayment,
    Debt,
    DebtPayment,
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
from app.schemas.paychecks import PaycheckListResponse, PaycheckResponse, PlanSummaryResponse
from app.schemas.payments import (
    BillPaymentListResponse,
    BillPaymentRequest,
    BillPaymentResponse,
    DebtPaymentListResponse,
    DebtPaymentRequest,
    DebtPaymentResponse,
)
from app.schemas.plans import AllocationResponse, GoalProjectionResponse, PlanResponse
from app.schemas.user import SettingsRequest, UserResponse
from app.services.auth import TokenPair
from app.services.bills import BillInput
from app.services.debts import DebtInput
from app.services.essential_expenses import EssentialExpenseInput
from app.services.goals import GoalInput
from app.services.income_sources import IncomeSourceInput
from app.services.paychecks import PaycheckEntry
from app.services.payments import BillPaymentInput, DebtPaymentInput
from app.services.plan_records import ExplainedAllocation, ExplainedProjection, PlanDetails
from app.services.settings import SettingsInput

# Cents set aside for each bill, debt, or goal, by its id; a missing id has none.
type Reserved = Mapping[uuid.UUID, int]

type _Schedule = WeeklySchedule | BiweeklySchedule | SemiMonthlySchedule | MonthlySchedule


def to_token_response(tokens: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token,
    )


def to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        timezone=user.timezone,
        no_deadline_goal_share_bps=user.no_deadline_goal_share_bps,
        created_at=user.created_at,
    )


def to_settings_input(body: SettingsRequest) -> SettingsInput:
    return SettingsInput(
        timezone=body.timezone, no_deadline_goal_share_bps=body.no_deadline_goal_share_bps
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


def to_bill_response(bill: Bill, reserved: Reserved) -> BillResponse:
    return BillResponse(
        id=bill.id,
        name=bill.name,
        amount_cents=bill.amount_cents,
        priority=bill.priority,
        first_due_date=bill.first_due_date,
        repeat_every_months=bill.repeat_every_months,
        reserved_cents=reserved.get(bill.id, 0),
        created_at=bill.created_at,
        updated_at=bill.updated_at,
    )


def to_bill_list_response(bills: Iterable[Bill], reserved: Reserved) -> BillListResponse:
    return BillListResponse(items=[to_bill_response(bill, reserved) for bill in bills])


def to_bill_payment_input(body: BillPaymentRequest) -> BillPaymentInput:
    return BillPaymentInput(
        amount_cents=body.amount_cents, paid_on=body.paid_on, due_date=body.due_date
    )


def to_bill_payment_response(payment: BillPayment) -> BillPaymentResponse:
    return BillPaymentResponse(
        id=payment.id,
        bill_id=payment.bill_id,
        due_date=payment.due_date,
        paid_on=payment.paid_on,
        amount_cents=payment.amount_cents,
        created_at=payment.created_at,
    )


def to_bill_payment_list_response(payments: Iterable[BillPayment]) -> BillPaymentListResponse:
    return BillPaymentListResponse(
        items=[to_bill_payment_response(payment) for payment in payments]
    )


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


def to_debt_response(debt: Debt, reserved: Reserved) -> DebtResponse:
    return DebtResponse(
        id=debt.id,
        name=debt.name,
        balance_cents=debt.balance_cents,
        apr_bps=debt.apr_bps,
        minimum_payment_cents=debt.minimum_payment_cents,
        due_day=debt.due_day,
        reserved_cents=reserved.get(debt.id, 0),
        created_at=debt.created_at,
        updated_at=debt.updated_at,
    )


def to_debt_list_response(debts: Iterable[Debt], reserved: Reserved) -> DebtListResponse:
    return DebtListResponse(items=[to_debt_response(debt, reserved) for debt in debts])


def to_debt_payment_input(body: DebtPaymentRequest) -> DebtPaymentInput:
    return DebtPaymentInput(amount_cents=body.amount_cents, paid_on=body.paid_on)


def to_debt_payment_response(payment: DebtPayment) -> DebtPaymentResponse:
    return DebtPaymentResponse(
        id=payment.id,
        debt_id=payment.debt_id,
        paid_on=payment.paid_on,
        amount_cents=payment.amount_cents,
        created_at=payment.created_at,
    )


def to_debt_payment_list_response(payments: Iterable[DebtPayment]) -> DebtPaymentListResponse:
    return DebtPaymentListResponse(
        items=[to_debt_payment_response(payment) for payment in payments]
    )


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


# --- paychecks -----------------------------------------------------------------


def to_paycheck_response(entry: PaycheckEntry) -> PaycheckResponse:
    paycheck, plan = entry.paycheck, entry.plan
    actual = None if paycheck is None else paycheck.actual_amount_cents
    summary = (
        None
        if plan is None
        else PlanSummaryResponse(
            id=plan.id,
            version=plan.version,
            status=plan.status,
            safe_to_spend_cents=plan.safe_to_spend_cents,
        )
    )
    return PaycheckResponse(
        plan=summary,
        id=None if paycheck is None else paycheck.id,
        income_source_id=entry.source.id,
        income_source_name=entry.source.name,
        income_source_archived=entry.source.archived_at is not None,
        pay_date=entry.pay_date,
        expected_amount_cents=entry.expected_amount_cents,
        actual_amount_cents=actual,
        amount_cents=entry.expected_amount_cents if actual is None else actual,
    )


def to_paycheck_list_response(entries: Iterable[PaycheckEntry]) -> PaycheckListResponse:
    return PaycheckListResponse(items=[to_paycheck_response(entry) for entry in entries])


# --- plans ---------------------------------------------------------------------


def to_plan_response(details: PlanDetails) -> PlanResponse:
    plan = details.plan
    return PlanResponse(
        id=plan.id,
        version=plan.version,
        status=plan.status,
        committed_at=plan.committed_at,
        engine_version=plan.engine_version,
        as_of=plan.as_of,
        paycheck=to_paycheck_response(
            PaycheckEntry(
                details.source,
                details.paycheck.pay_date,
                details.paycheck.expected_amount_cents,
                details.paycheck,
                plan,
            )
        ),
        next_pay_date=plan.next_pay_date,
        paycheck_amount_cents=plan.paycheck_amount_cents,
        available_balance_cents=plan.available_balance_cents,
        balance_as_of=plan.balance_as_of,
        safe_to_spend_cents=plan.safe_to_spend_cents,
        reserve_deficit_cents=plan.reserve_deficit_cents,
        summary=details.summary,
        allocations=[_to_allocation_response(line) for line in details.allocations],
        goal_projections=[_to_projection_response(line) for line in details.projections],
        created_at=plan.created_at,
    )


def _to_allocation_response(line: ExplainedAllocation) -> AllocationResponse:
    row = line.row
    return AllocationResponse(
        position=row.position,
        tier=row.tier,
        target_id=line.target_id,
        name=row.name,
        requested_cents=row.requested_cents,
        funded_cents=row.funded_cents,
        shortfall_cents=row.requested_cents - row.funded_cents,
        reason=row.reason,
        total_cents=row.total_cents,
        set_aside_cents=row.set_aside_cents,
        due_date=row.due_date,
        paychecks=row.paychecks,
        days_covered=row.days_covered,
        days_in_period=row.days_in_period,
        share_bps=row.share_bps,
        explanation=line.explanation,
    )


def _to_projection_response(line: ExplainedProjection) -> GoalProjectionResponse:
    row = line.row
    return GoalProjectionResponse(
        goal_id=row.goal_id,
        name=row.name,
        deadline=row.deadline,
        contribution_cents=row.contribution_cents,
        still_needed_cents=row.still_needed_cents,
        projected_date=row.projected_date,
        status=row.status,
        suggested_deadline=line.suggested_deadline,
        explanation=line.explanation,
    )


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


def to_goal_response(goal: Goal, reserved: Reserved) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        name=goal.name,
        kind=goal.kind,
        target_cents=goal.target_cents,
        current_cents=goal.current_cents,
        priority=goal.priority,
        deadline=goal.deadline,
        reserved_cents=reserved.get(goal.id, 0),
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


def to_goal_list_response(goals: Iterable[Goal], reserved: Reserved) -> GoalListResponse:
    return GoalListResponse(items=[to_goal_response(goal, reserved) for goal in goals])


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
