"""Request and response bodies for /goals. A purchase is a goal of kind "purchase" (ADR 0004)."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.common import (
    IsoDate,
    Name,
    NonNegativeCents,
    PositiveCents,
    Priority,
    RequestModel,
)
from nextpay_engine import GoalKind


class GoalRequest(RequestModel):
    """A whole goal: POST creates it, PUT replaces it. Every field is required."""

    name: Name
    kind: GoalKind
    target_cents: PositiveCents
    current_cents: Annotated[
        NonNegativeCents, Field(description="Saved so far. May exceed the target.")
    ]
    priority: Priority
    deadline: Annotated[IsoDate | None, Field(description="null: no deadline.")]


class GoalResponse(BaseModel):
    id: uuid.UUID
    name: str
    kind: GoalKind
    target_cents: int
    current_cents: int
    priority: int
    deadline: date | None
    created_at: datetime
    updated_at: datetime


class GoalListResponse(BaseModel):
    items: list[GoalResponse]
