"""Field types shared by the resource schemas.

Integers are strict: JSON ``12.0``, ``"12"`` and ``true`` are not amounts.
Dates are ISO 8601 strings only, never timestamps.
"""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.core.limits import MAX_CENTS, MAX_NAME_LENGTH, MAX_PRIORITY


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _require_date_string(value: object) -> object:
    # A plain date only ever comes from our own code building a response; JSON has none.
    if isinstance(value, str) or type(value) is date:
        return value
    raise ValueError("must be a date string such as 2026-10-20")


# Trimmed, not blank, and free of control characters (PostgreSQL rejects NUL).
Name = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_NAME_LENGTH,
        pattern=r"^[^\x00-\x1f\x7f]*$",
    ),
]
PositiveCents = Annotated[int, Field(strict=True, gt=0, le=MAX_CENTS)]
NonNegativeCents = Annotated[int, Field(strict=True, ge=0, le=MAX_CENTS)]
# Negative when overdrawn.
SignedCents = Annotated[int, Field(strict=True, ge=-MAX_CENTS, le=MAX_CENTS)]
DayOfMonth = Annotated[
    int, Field(strict=True, ge=1, le=31, description="Past a month's end means its last day.")
]
# 1 is the most important.
Priority = Annotated[int, Field(strict=True, ge=1, le=MAX_PRIORITY)]
IsoDate = Annotated[date, BeforeValidator(_require_date_string)]
