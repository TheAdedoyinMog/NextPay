"""Request and response bodies for paychecks."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field

from app.models import PlanStatus
from app.schemas.common import NonNegativeCents, RequestModel


class ActualAmountRequest(RequestModel):
    actual_amount_cents: Annotated[
        NonNegativeCents | None,
        Field(description="What actually arrived; 0 is allowed. null: not recorded (clears it)."),
    ]


class PlanSummaryResponse(BaseModel):
    """A paycheck's plan that counts: its committed plan, or else its current draft."""

    id: uuid.UUID
    version: int
    status: PlanStatus
    safe_to_spend_cents: int


class PaycheckResponse(BaseModel):
    """One payday of one income source. A paycheck is named by its source and pay date."""

    id: uuid.UUID | None = Field(
        description="null until something is recorded or planned for this payday."
    )
    income_source_id: uuid.UUID
    income_source_name: str
    income_source_archived: bool
    pay_date: date
    expected_amount_cents: int
    actual_amount_cents: int | None
    amount_cents: int = Field(
        description="The amount a plan uses: the actual amount once recorded, else the expected."
    )
    plan: PlanSummaryResponse | None = Field(description="null until this paycheck is planned.")


class PaycheckListResponse(BaseModel):
    items: list[PaycheckResponse] = Field(description="By pay date.")
