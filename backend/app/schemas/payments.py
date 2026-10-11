"""Request and response bodies for bill and debt payments.

Unlike the resources, a payment is an event, and every field of the request is
optional: left out (or null), each takes the obvious value, so "mark as paid"
is a POST of ``{}``.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.common import IsoDate, PositiveCents, RequestModel


class BillPaymentRequest(RequestModel):
    amount_cents: Annotated[
        PositiveCents | None, Field(description="Left out: the bill's full amount.")
    ] = None
    paid_on: Annotated[IsoDate | None, Field(description="Left out: today, in your time zone.")] = (
        None
    )
    due_date: Annotated[
        IsoDate | None,
        Field(
            description=(
                "Which occurrence this pays; it must be one of the bill's due dates. "
                "Left out: the due date closest to paid_on."
            )
        ),
    ] = None


class BillPaymentResponse(BaseModel):
    id: uuid.UUID
    bill_id: uuid.UUID
    due_date: date
    paid_on: date
    amount_cents: int
    created_at: datetime


class BillPaymentListResponse(BaseModel):
    items: list[BillPaymentResponse] = Field(description="Newest first.")


class DebtPaymentRequest(RequestModel):
    amount_cents: Annotated[
        PositiveCents | None,
        Field(description="Left out: the minimum payment, or the whole balance if that is less."),
    ] = None
    paid_on: Annotated[IsoDate | None, Field(description="Left out: today, in your time zone.")] = (
        None
    )


class DebtPaymentResponse(BaseModel):
    id: uuid.UUID
    debt_id: uuid.UUID
    paid_on: date
    amount_cents: int
    created_at: datetime


class DebtPaymentListResponse(BaseModel):
    items: list[DebtPaymentResponse] = Field(description="Newest first.")
