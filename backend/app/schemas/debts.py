"""Request and response bodies for /debts."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.core.limits import MAX_APR_BPS
from app.schemas.common import DayOfMonth, Name, NonNegativeCents, RequestModel


class DebtRequest(RequestModel):
    """A whole debt: POST creates it, PUT replaces it. Every field is required."""

    name: Name
    balance_cents: NonNegativeCents
    apr_bps: Annotated[
        int,
        Field(
            strict=True,
            ge=0,
            le=MAX_APR_BPS,
            description="Annual rate in basis points: 24.99% is 2499.",
        ),
    ]
    minimum_payment_cents: NonNegativeCents
    due_day: DayOfMonth


class DebtResponse(BaseModel):
    id: uuid.UUID
    name: str
    balance_cents: int
    apr_bps: int
    minimum_payment_cents: int
    due_day: int
    created_at: datetime
    updated_at: datetime


class DebtListResponse(BaseModel):
    items: list[DebtResponse]
