"""Request and response bodies for /bills."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.core.limits import MAX_REPEAT_EVERY_MONTHS
from app.schemas.common import IsoDate, Name, PositiveCents, Priority, RequestModel


class BillRequest(RequestModel):
    """A whole bill: POST creates it, PUT replaces it. Every field is required."""

    name: Name
    amount_cents: PositiveCents
    priority: Priority
    first_due_date: IsoDate
    repeat_every_months: Annotated[
        int | None,
        Field(
            strict=True,
            ge=1,
            le=MAX_REPEAT_EVERY_MONTHS,
            description="1 is monthly, 3 quarterly, 12 yearly. null: due once, on first_due_date.",
        ),
    ]


class BillResponse(BaseModel):
    id: uuid.UUID
    name: str
    amount_cents: int
    priority: int
    first_due_date: date
    repeat_every_months: int | None
    created_at: datetime
    updated_at: datetime


class BillListResponse(BaseModel):
    items: list[BillResponse]
