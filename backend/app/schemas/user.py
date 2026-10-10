"""The signed-in user, as the API shows them."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    timezone: str
    created_at: datetime
