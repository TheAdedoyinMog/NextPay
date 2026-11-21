"""The response for GET /dashboard: what the home screen shows."""

import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.schemas.balances import BalanceSnapshotResponse
from app.schemas.paychecks import PaycheckResponse


class SafeToSpendResponse(BaseModel):
    """From the newest committed plan for a payday on or before today, kept current
    as payments are recorded (ADR 0003, ADR 0016)."""

    plan_id: uuid.UUID
    pay_date: date
    income_source_name: str
    safe_to_spend_cents: int = Field(
        description=(
            "The plan's Safe to Spend, less what payments since its commit paid beyond what"
            " was set aside for them. Never below 0."
        )
    )
    reserve_deficit_cents: int = Field(
        description=(
            "How far what is set aside exceeds the money on hand, including payments beyond"
            " their reserves that Safe to Spend could not cover; normally 0."
        )
    )
    paid_beyond_reserves_cents: int = Field(
        description="What payments since the plan's commit paid beyond what was set aside."
    )


class DashboardResponse(BaseModel):
    today: date = Field(description="Today in your time zone.")
    current_paycheck: PaycheckResponse | None = Field(
        description="The newest payday on or before today; null before your first."
    )
    next_paycheck: PaycheckResponse | None = Field(description="The first payday after today.")
    safe_to_spend: SafeToSpendResponse | None = Field(
        description="null until a plan for a payday on or before today is committed."
    )
    balance: BalanceSnapshotResponse | None = Field(
        description="Your latest balance; null if you have entered none."
    )
