"""Request and response bodies for /plans.

Every amount comes with the facts behind it (the engine's ``Basis``) and a
sentence built from those facts, so the app can show the sentence as it is or
write its own from the reason code.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models import PlanStatus
from app.schemas.common import IsoDate, RequestModel
from app.schemas.paychecks import PaycheckResponse
from nextpay_engine import GoalStatus, Reason, Tier


class PlanRequest(RequestModel):
    """Which paycheck to plan: a paycheck is named by its income source and pay date."""

    income_source_id: uuid.UUID
    pay_date: IsoDate = Field(description="One of the source's paydays; see GET /paychecks.")


class AllocationResponse(BaseModel):
    """One line of a plan: what a target asked for from this paycheck, and what it got."""

    position: int = Field(description="Order in the waterfall, from 0.")
    tier: Tier
    target_id: uuid.UUID | None = Field(
        description="The bill, essential expense, debt, or goal; null once it is deleted."
    )
    name: str
    requested_cents: int
    funded_cents: int
    shortfall_cents: int
    reason: Reason
    total_cents: int = Field(
        description="The bill amount, debt minimum, essential's amount per period, or goal target."
    )
    set_aside_cents: int = Field(
        description="Already reserved for the bill or debt, or the goal's progress."
    )
    due_date: date | None
    paychecks: int | None = Field(
        description="The paychecks the need is split across, this one included."
    )
    days_covered: int | None
    days_in_period: int | None
    share_bps: int | None
    explanation: str


class GoalProjectionResponse(BaseModel):
    """When a goal would be reached if this paycheck's contribution repeated every paycheck."""

    goal_id: uuid.UUID | None = Field(description="null once the goal is deleted.")
    name: str
    deadline: date | None
    contribution_cents: int
    still_needed_cents: int
    projected_date: date | None
    status: GoalStatus
    suggested_deadline: date | None = Field(
        description="A date to offer when the goal is behind or its deadline has passed."
    )
    explanation: str


class PlanResponse(BaseModel):
    id: uuid.UUID
    version: int = Field(description="1, 2, 3... for this paycheck.")
    status: PlanStatus
    committed_at: datetime | None
    engine_version: str
    as_of: date = Field(description="The day the plan was made for, in your time zone.")
    paycheck: PaycheckResponse
    next_pay_date: date
    paycheck_amount_cents: int = Field(description="The paycheck amount this plan used.")
    available_balance_cents: int = Field(
        description="Your balance before this paycheck, as this plan used it."
    )
    balance_as_of: datetime | None = Field(
        description="When that balance was entered; null if you had entered none ($0)."
    )
    safe_to_spend_cents: int
    reserve_deficit_cents: int = Field(
        description="How far what is set aside exceeds the money on hand; normally 0."
    )
    summary: str
    allocations: list[AllocationResponse]
    goal_projections: list[GoalProjectionResponse]
    created_at: datetime
