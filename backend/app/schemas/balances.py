"""Request and response bodies for /balance-snapshots."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.common import RequestModel, SignedCents


class BalanceSnapshotRequest(RequestModel):
    amount_cents: Annotated[
        SignedCents, Field(description="What you have right now. Negative when overdrawn.")
    ]


class BalanceSnapshotResponse(BaseModel):
    id: uuid.UUID
    amount_cents: int
    as_of: datetime
    created_at: datetime


class BalanceSnapshotListResponse(BaseModel):
    items: list[BalanceSnapshotResponse] = Field(description="Newest first.")
