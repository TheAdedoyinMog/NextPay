"""/essential-expenses: what the signed-in user needs every pay period (ADR 0010)."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, EssentialExpenseServiceDep
from app.api.errors import error_responses
from app.api.mappers import (
    to_essential_expense_input,
    to_essential_expense_list_response,
    to_essential_expense_response,
)
from app.schemas.essential_expenses import (
    EssentialExpenseListResponse,
    EssentialExpenseRequest,
    EssentialExpenseResponse,
)

router = APIRouter(prefix="/essential-expenses", tags=["essential expenses"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 422),
    summary="Add an essential expense",
)
def create_essential_expense(
    body: EssentialExpenseRequest, user: CurrentUser, essentials: EssentialExpenseServiceDep
) -> EssentialExpenseResponse:
    return to_essential_expense_response(
        essentials.create(user.id, to_essential_expense_input(body))
    )


@router.get("", responses=error_responses(401), summary="List your essential expenses")
def list_essential_expenses(
    user: CurrentUser, essentials: EssentialExpenseServiceDep
) -> EssentialExpenseListResponse:
    return to_essential_expense_list_response(essentials.list_for(user.id))


@router.get(
    "/{essential_expense_id}",
    responses=error_responses(401, 404, 422),
    summary="Get an essential expense",
)
def get_essential_expense(
    essential_expense_id: uuid.UUID, user: CurrentUser, essentials: EssentialExpenseServiceDep
) -> EssentialExpenseResponse:
    return to_essential_expense_response(essentials.get(user.id, essential_expense_id))


@router.put(
    "/{essential_expense_id}",
    responses=error_responses(401, 404, 422),
    summary="Replace an essential expense",
    description="Send the whole expense: every field is replaced.",
)
def replace_essential_expense(
    essential_expense_id: uuid.UUID,
    body: EssentialExpenseRequest,
    user: CurrentUser,
    essentials: EssentialExpenseServiceDep,
) -> EssentialExpenseResponse:
    return to_essential_expense_response(
        essentials.update(user.id, essential_expense_id, to_essential_expense_input(body))
    )


@router.delete(
    "/{essential_expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 404, 422),
    summary="Delete an essential expense",
    description="Past plans keep the expense's name.",
)
def delete_essential_expense(
    essential_expense_id: uuid.UUID, user: CurrentUser, essentials: EssentialExpenseServiceDep
) -> None:
    essentials.delete(user.id, essential_expense_id)
