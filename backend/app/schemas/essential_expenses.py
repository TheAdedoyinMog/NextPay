"""Request and response bodies for /essential-expenses."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import Name, PositiveCents, RequestModel


class EssentialExpenseRequest(RequestModel):
    """A whole essential expense: POST creates it, PUT replaces it."""

    name: Name
    amount_per_period_cents: PositiveCents


class EssentialExpenseResponse(BaseModel):
    id: uuid.UUID
    name: str
    amount_per_period_cents: int
    created_at: datetime
    updated_at: datetime


class EssentialExpenseListResponse(BaseModel):
    items: list[EssentialExpenseResponse]
