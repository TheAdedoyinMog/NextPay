"""The signed-in user, as the API shows them, and the settings they can change."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.common import RequestModel


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    timezone: str
    no_deadline_goal_share_bps: int
    created_at: datetime


class SettingsRequest(RequestModel):
    """All of a user's settings: PUT replaces them. Every field is required."""

    timezone: Annotated[
        str,
        Field(
            min_length=1,
            max_length=64,
            description='IANA time zone, e.g. "America/New_York". Decides what "today" is.',
        ),
    ]
    no_deadline_goal_share_bps: Annotated[
        int,
        Field(
            strict=True,
            ge=0,
            le=10_000,
            description=(
                "Share of what is left after everything else that goes to goals without "
                "a deadline, in basis points: 2000 is 20%."
            ),
        ),
    ]
