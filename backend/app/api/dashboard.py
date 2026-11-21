"""GET /dashboard: the home screen in one request (ADR 0015)."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DashboardServiceDep
from app.api.errors import error_responses
from app.api.mappers import to_dashboard_response
from app.schemas.dashboard import DashboardResponse

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard",
    responses=error_responses(401),
    summary="What the home screen shows",
    description=(
        "Today in your time zone, the current and next paydays with their plans, Safe to "
        "Spend from the newest committed plan, and your latest balance."
    ),
)
def dashboard(user: CurrentUser, dashboards: DashboardServiceDep) -> DashboardResponse:
    return to_dashboard_response(dashboards.for_user(user))
