"""/income-sources: the signed-in user's jobs and other regular income (ADR 0005, 0010, 0011)."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, IncomeSourceServiceDep
from app.api.errors import error_responses
from app.api.mappers import (
    to_income_source_input,
    to_income_source_list_response,
    to_income_source_response,
)
from app.schemas.income_sources import (
    IncomeSourceListResponse,
    IncomeSourceRequest,
    IncomeSourceResponse,
)

router = APIRouter(prefix="/income-sources", tags=["income sources"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 422),
    summary="Add an income source",
)
def create_income_source(
    body: IncomeSourceRequest, user: CurrentUser, income_sources: IncomeSourceServiceDep
) -> IncomeSourceResponse:
    return to_income_source_response(income_sources.create(user.id, to_income_source_input(body)))


@router.get("", responses=error_responses(401), summary="List your income sources")
def list_income_sources(
    user: CurrentUser, income_sources: IncomeSourceServiceDep
) -> IncomeSourceListResponse:
    return to_income_source_list_response(income_sources.list_for(user.id))


@router.get(
    "/{income_source_id}",
    responses=error_responses(401, 404, 422),
    summary="Get an income source",
)
def get_income_source(
    income_source_id: uuid.UUID, user: CurrentUser, income_sources: IncomeSourceServiceDep
) -> IncomeSourceResponse:
    return to_income_source_response(income_sources.get(user.id, income_source_id))


@router.put(
    "/{income_source_id}",
    responses=error_responses(401, 404, 422),
    summary="Replace an income source",
    description="Send the whole income source: every field, and the whole schedule, is replaced.",
)
def replace_income_source(
    income_source_id: uuid.UUID,
    body: IncomeSourceRequest,
    user: CurrentUser,
    income_sources: IncomeSourceServiceDep,
) -> IncomeSourceResponse:
    return to_income_source_response(
        income_sources.update(user.id, income_source_id, to_income_source_input(body))
    )


@router.delete(
    "/{income_source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 404, 422),
    summary="Delete an income source",
    description=(
        "A source that has paychecks is archived instead of deleted: it stops paying and "
        "can no longer be read or planned for, but its paychecks and plans stay as history."
    ),
)
def delete_income_source(
    income_source_id: uuid.UUID, user: CurrentUser, income_sources: IncomeSourceServiceDep
) -> None:
    income_sources.delete(user.id, income_source_id)
