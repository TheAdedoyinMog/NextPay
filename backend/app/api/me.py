"""GET /me: the signed-in user. The first route behind get_current_user."""

from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.api.mappers import to_user_response
from app.schemas.errors import ErrorResponse
from app.schemas.user import UserResponse

router = APIRouter(tags=["account"])

_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {401: {"model": ErrorResponse}}


@router.get("/me", responses=_UNAUTHORIZED, summary="The signed-in user")
def me(user: CurrentUser) -> UserResponse:
    return to_user_response(user)
