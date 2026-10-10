"""Central error handling: the one place errors become HTTP responses.

Services raise ``DomainError`` subclasses and know nothing about HTTP. Request
validation errors and Starlette's own errors (unknown route, wrong method) are
reshaped into the same envelope, so clients parse a single error format.
"""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    EmailUnavailableError,
    InvalidInputError,
    NotFoundError,
)
from app.schemas.errors import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)

# Looked up along each error's class hierarchy, most specific first.
_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    EmailUnavailableError: status.HTTP_409_CONFLICT,
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` for a route: each status code returns the error envelope."""
    return {code: {"model": ErrorResponse} for code in codes}


def status_for(error: DomainError) -> int:
    for cls in type(error).__mro__:
        if cls in _STATUS_BY_ERROR:
            return _STATUS_BY_ERROR[cls]
    logger.warning("no HTTP status mapped for %s; using 400", type(error).__name__)
    return status.HTTP_400_BAD_REQUEST


def error_response(
    status_code: int, code: str, message: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message))
    if status_code == status.HTTP_401_UNAUTHORIZED:
        headers = {"WWW-Authenticate": "Bearer", **(headers or {})}
    return JSONResponse(body.model_dump(), status_code=status_code, headers=headers)


async def _domain_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, DomainError)
    return error_response(status_for(error), error.code, error.detail)


async def _validation_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    # Name the fields, not their values: a rejected password must never be echoed.
    fields = sorted(
        {".".join(str(part) for part in e["loc"][1:]) or str(e["loc"][0]) for e in error.errors()}
    )
    message = "Check these fields: " + ", ".join(fields) if fields else "The request is invalid."
    return error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", message)


async def _http_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    code = {404: "not_found", 405: "method_not_allowed"}.get(error.status_code, "http_error")
    return error_response(error.status_code, code, str(error.detail), error.headers)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
