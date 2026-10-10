"""POST /auth/register, /auth/login, /auth/refresh, /auth/logout (ADR 0009)."""

from typing import Any

from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep
from app.api.mappers import to_token_response
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.errors import ErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse} for code in codes}


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    responses=_errors(409, 422),
    summary="Create an account and sign in",
)
def register(body: RegisterRequest, auth: AuthServiceDep) -> TokenResponse:
    return to_token_response(auth.register(body.email, body.password.get_secret_value()))


@router.post("/login", responses=_errors(401, 422), summary="Sign in")
def login(body: LoginRequest, auth: AuthServiceDep) -> TokenResponse:
    return to_token_response(auth.login(body.email, body.password.get_secret_value()))


@router.post(
    "/refresh",
    responses=_errors(401, 422),
    summary="Swap a refresh token for a new token pair",
    description=(
        "Each refresh token works once. Presenting one again ends the whole session, "
        "so clients must not refresh concurrently."
    ),
)
def refresh(body: RefreshRequest, auth: AuthServiceDep) -> TokenResponse:
    return to_token_response(auth.refresh(body.refresh_token.get_secret_value()))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_errors(422),
    summary="End this session",
    description="Always succeeds, so it can't be used to test whether a token is valid.",
)
def logout(body: LogoutRequest, auth: AuthServiceDep) -> None:
    auth.logout(body.refresh_token.get_secret_value())
