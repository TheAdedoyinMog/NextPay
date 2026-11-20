"""The one error shape every response uses: ``{"error": {"code": ..., "message": ...}}``."""

from typing import Annotated

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    fields: Annotated[
        dict[str, str] | None,
        Field(
            description=(
                "Validation errors only: each rejected field's dotted path, as in `message`, "
                "with what was wrong. Never contains the submitted value."
            )
        ),
    ] = None


class ErrorResponse(BaseModel):
    error: ErrorBody
