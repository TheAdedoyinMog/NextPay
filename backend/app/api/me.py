"""GET /me: the signed-in user. PUT /me/settings: their planning settings."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SettingsServiceDep
from app.api.errors import error_responses
from app.api.mappers import to_settings_input, to_user_response
from app.schemas.user import SettingsRequest, UserResponse

router = APIRouter(tags=["account"])


@router.get("/me", responses=error_responses(401), summary="The signed-in user")
def me(user: CurrentUser) -> UserResponse:
    return to_user_response(user)


@router.put(
    "/me/settings",
    responses=error_responses(401, 422),
    summary="Replace your settings",
    description=(
        "Your time zone decides which day a plan is made for. Changing either setting "
        "makes draft plans out of date."
    ),
)
def replace_settings(
    body: SettingsRequest, user: CurrentUser, settings: SettingsServiceDep
) -> UserResponse:
    return to_user_response(settings.update(user, to_settings_input(body)))
