"""Request and response bodies for /income-sources.

A pay schedule is one of four shapes, told apart by ``type``, so each frequency
can only be sent with its own parameters.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schemas.common import DayOfMonth, IsoDate, Name, PositiveCents, RequestModel

AnchorDate = Annotated[IsoDate, Field(description="Any real payday, past or future.")]


class WeeklySchedule(RequestModel):
    type: Literal["weekly"]
    anchor_date: AnchorDate


class BiweeklySchedule(RequestModel):
    type: Literal["biweekly"]
    anchor_date: AnchorDate


class SemiMonthlySchedule(RequestModel):
    """Two paydays a month, at least 7 days apart in every month."""

    type: Literal["semi_monthly"]
    first_day_of_month: DayOfMonth
    second_day_of_month: DayOfMonth


class MonthlySchedule(RequestModel):
    type: Literal["monthly"]
    day_of_month: DayOfMonth


Schedule = Annotated[
    WeeklySchedule | BiweeklySchedule | SemiMonthlySchedule | MonthlySchedule,
    Field(discriminator="type"),
]


class IncomeSourceRequest(RequestModel):
    """A whole income source: POST creates it, PUT replaces it."""

    name: Name
    expected_amount_cents: PositiveCents
    schedule: Schedule


class IncomeSourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    expected_amount_cents: int
    schedule: Schedule
    created_at: datetime
    updated_at: datetime


class IncomeSourceListResponse(BaseModel):
    items: list[IncomeSourceResponse]
