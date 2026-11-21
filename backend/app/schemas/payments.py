"""Request and response bodies for bill and debt payments.

Unlike the resources, a payment is an event, and every field of the request is
optional: left out (or null), each takes the obvious value, so "mark as paid"
is a POST of ``{}``. A payment is undone with a POST to its ``/undo``, which
keeps it as history (ADR 0017).
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.common import IsoDate, PositiveCents, RequestModel


class BillPaymentRequest(RequestModel):
    id: Annotated[
        uuid.UUID | None,
        Field(
            description=(
                "A new id the client makes for this payment, so a retry can't record it twice: "
                "a payment with this id for the same bill is returned as it is (200) and nothing "
                "changes. Used for anything else: 409 `payment_id_conflict`. Left out: the "
                "server makes one, and a retry records a second payment."
            )
        ),
    ] = None
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
    undone_at: datetime | None = Field(
        description=(
            "When the payment was undone; it then counts for nothing. Undone payments are "
            "left out of payment lists, so this is set only on the reply to an undo, or to "
            "a retry of the original payment."
        )
    )
    can_undo: bool = Field(
        description=(
            "Whether POST .../undo would undo it: not once undone, and not once a plan was "
            "committed after it (ADR 0017)."
        )
    )


class BillPaymentListResponse(BaseModel):
    items: list[BillPaymentResponse] = Field(description="Newest first.")


class DebtPaymentRequest(RequestModel):
    id: Annotated[
        uuid.UUID | None,
        Field(
            description=(
                "A new id the client makes for this payment, so a retry can't record it twice: "
                "a payment with this id for the same debt is returned as it is (200) and nothing "
                "changes. Used for anything else: 409 `payment_id_conflict`. Left out: the "
                "server makes one, and a retry records a second payment."
            )
        ),
    ] = None
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
    undone_at: datetime | None = Field(
        description=(
            "When the payment was undone; it then counts for nothing. Undone payments are "
            "left out of payment lists, so this is set only on the reply to an undo, or to "
            "a retry of the original payment."
        )
    )
    can_undo: bool = Field(
        description=(
            "Whether POST .../undo would undo it: not once undone, and not once a plan was "
            "committed after it (ADR 0017)."
        )
    )


class DebtPaymentListResponse(BaseModel):
    items: list[DebtPaymentResponse] = Field(description="Newest first.")
