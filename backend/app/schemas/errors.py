"""The one error shape every response uses: ``{"error": {"code": ..., "message": ...}}``."""

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
