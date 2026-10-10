"""/bills: the signed-in user's bills (ADR 0010)."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import BillServiceDep, CurrentUser
from app.api.errors import error_responses
from app.api.mappers import to_bill_input, to_bill_list_response, to_bill_response
from app.schemas.bills import BillListResponse, BillRequest, BillResponse

router = APIRouter(prefix="/bills", tags=["bills"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 422),
    summary="Add a bill",
)
def create_bill(body: BillRequest, user: CurrentUser, bills: BillServiceDep) -> BillResponse:
    return to_bill_response(bills.create(user.id, to_bill_input(body)))


@router.get("", responses=error_responses(401), summary="List your bills")
def list_bills(user: CurrentUser, bills: BillServiceDep) -> BillListResponse:
    return to_bill_list_response(bills.list_for(user.id))


@router.get("/{bill_id}", responses=error_responses(401, 404, 422), summary="Get a bill")
def get_bill(bill_id: uuid.UUID, user: CurrentUser, bills: BillServiceDep) -> BillResponse:
    return to_bill_response(bills.get(user.id, bill_id))


@router.put(
    "/{bill_id}",
    responses=error_responses(401, 404, 422),
    summary="Replace a bill",
    description="Send the whole bill: every field is replaced.",
)
def replace_bill(
    bill_id: uuid.UUID, body: BillRequest, user: CurrentUser, bills: BillServiceDep
) -> BillResponse:
    return to_bill_response(bills.update(user.id, bill_id, to_bill_input(body)))


@router.delete(
    "/{bill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 404, 422),
    summary="Delete a bill",
    description=(
        "Also deletes the bill's recorded payments and releases any money reserved for it. "
        "Past plans keep the bill's name."
    ),
)
def delete_bill(bill_id: uuid.UUID, user: CurrentUser, bills: BillServiceDep) -> None:
    bills.delete(user.id, bill_id)
