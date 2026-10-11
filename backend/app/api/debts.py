"""/debts: the signed-in user's debts (ADR 0010)."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DebtServiceDep, ReserveServiceDep
from app.api.errors import error_responses
from app.api.mappers import to_debt_input, to_debt_list_response, to_debt_response
from app.schemas.debts import DebtListResponse, DebtRequest, DebtResponse
from nextpay_engine import ReserveKind

router = APIRouter(prefix="/debts", tags=["debts"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 422),
    summary="Add a debt",
)
def create_debt(body: DebtRequest, user: CurrentUser, debts: DebtServiceDep) -> DebtResponse:
    # A new debt has nothing set aside yet.
    return to_debt_response(debts.create(user.id, to_debt_input(body)), {})


@router.get("", responses=error_responses(401), summary="List your debts")
def list_debts(
    user: CurrentUser, debts: DebtServiceDep, reserves: ReserveServiceDep
) -> DebtListResponse:
    return to_debt_list_response(
        debts.list_for(user.id), reserves.amounts(user.id, ReserveKind.DEBT)
    )


@router.get("/{debt_id}", responses=error_responses(401, 404, 422), summary="Get a debt")
def get_debt(
    debt_id: uuid.UUID, user: CurrentUser, debts: DebtServiceDep, reserves: ReserveServiceDep
) -> DebtResponse:
    return to_debt_response(
        debts.get(user.id, debt_id), reserves.amounts(user.id, ReserveKind.DEBT)
    )


@router.put(
    "/{debt_id}",
    responses=error_responses(401, 404, 422),
    summary="Replace a debt",
    description="Send the whole debt: every field is replaced.",
)
def replace_debt(
    debt_id: uuid.UUID,
    body: DebtRequest,
    user: CurrentUser,
    debts: DebtServiceDep,
    reserves: ReserveServiceDep,
) -> DebtResponse:
    return to_debt_response(
        debts.update(user.id, debt_id, to_debt_input(body)),
        reserves.amounts(user.id, ReserveKind.DEBT),
    )


@router.delete(
    "/{debt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 404, 422),
    summary="Delete a debt",
    description="Releases any money reserved for the debt. Past plans keep its name.",
)
def delete_debt(debt_id: uuid.UUID, user: CurrentUser, debts: DebtServiceDep) -> None:
    debts.delete(user.id, debt_id)
