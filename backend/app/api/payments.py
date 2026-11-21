"""Payments toward bills and debts, and undoing them (ADR 0003, ADR 0011, ADR 0017)."""

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, PaymentServiceDep
from app.api.errors import error_responses
from app.api.mappers import (
    to_bill_payment_input,
    to_bill_payment_list_response,
    to_bill_payment_response,
    to_debt_payment_input,
    to_debt_payment_list_response,
    to_debt_payment_response,
)
from app.schemas.payments import (
    BillPaymentListResponse,
    BillPaymentRequest,
    BillPaymentResponse,
    DebtPaymentListResponse,
    DebtPaymentRequest,
    DebtPaymentResponse,
)

router = APIRouter(tags=["payments"])


@router.post(
    "/bills/{bill_id}/payments",
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": BillPaymentResponse, "description": "A retry: the payment with this id."},
        **error_responses(401, 404, 409, 422),
    },
    summary="Record a bill payment",
    description=(
        "Send `{}` to mark the bill paid in full today. The money set aside for the bill "
        "goes down by the amount paid, never below $0. Your balance is not changed: enter "
        "a new one when you next plan. Send an `id` you made so a retry can't pay twice."
    ),
)
def pay_bill(
    bill_id: uuid.UUID,
    body: BillPaymentRequest,
    user: CurrentUser,
    payments: PaymentServiceDep,
    response: Response,
) -> BillPaymentResponse:
    payment, created = payments.pay_bill(user, bill_id, to_bill_payment_input(body))
    if not created:
        response.status_code = status.HTTP_200_OK
    return to_bill_payment_response(payment, payments.latest_commit(user.id))


@router.get(
    "/bills/{bill_id}/payments",
    responses=error_responses(401, 404, 422),
    summary="List a bill's payments, newest first",
)
def list_bill_payments(
    bill_id: uuid.UUID, user: CurrentUser, payments: PaymentServiceDep
) -> BillPaymentListResponse:
    return to_bill_payment_list_response(
        payments.list_bill_payments(user.id, bill_id), payments.latest_commit(user.id)
    )


_UNDO_DESCRIPTION = (
    "Puts back what the payment took from the money set aside{debt}, and marks it undone: it "
    "drops out of the payment list and no longer lowers Safe to Spend. The payment is kept as "
    "history. Undoing it again changes nothing and returns it, so a retry is harmless. Only "
    "until a plan is committed after the payment: then 409 `payment_undo_too_late`. To pay "
    "again, record a new payment with a new id."
)


@router.post(
    "/bills/{bill_id}/payments/{payment_id}/undo",
    responses=error_responses(401, 404, 409, 422),
    summary="Undo a bill payment",
    description=_UNDO_DESCRIPTION.format(debt=""),
)
def undo_bill_payment(
    bill_id: uuid.UUID, payment_id: uuid.UUID, user: CurrentUser, payments: PaymentServiceDep
) -> BillPaymentResponse:
    payment = payments.undo_bill_payment(user, bill_id, payment_id)
    return to_bill_payment_response(payment, payments.latest_commit(user.id))


@router.post(
    "/debts/{debt_id}/payments",
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": DebtPaymentResponse, "description": "A retry: the payment with this id."},
        **error_responses(401, 404, 409, 422),
    },
    summary="Record a debt payment",
    description=(
        "Send `{}` to record this month's minimum, paid today. The debt's balance and the "
        "money set aside for it both go down by the amount paid, never below $0. Send an "
        "`id` you made so a retry can't pay twice."
    ),
)
def pay_debt(
    debt_id: uuid.UUID,
    body: DebtPaymentRequest,
    user: CurrentUser,
    payments: PaymentServiceDep,
    response: Response,
) -> DebtPaymentResponse:
    payment, created = payments.pay_debt(user, debt_id, to_debt_payment_input(body))
    if not created:
        response.status_code = status.HTTP_200_OK
    return to_debt_payment_response(payment, payments.latest_commit(user.id))


@router.get(
    "/debts/{debt_id}/payments",
    responses=error_responses(401, 404, 422),
    summary="List a debt's payments, newest first",
)
def list_debt_payments(
    debt_id: uuid.UUID, user: CurrentUser, payments: PaymentServiceDep
) -> DebtPaymentListResponse:
    return to_debt_payment_list_response(
        payments.list_debt_payments(user.id, debt_id), payments.latest_commit(user.id)
    )


@router.post(
    "/debts/{debt_id}/payments/{payment_id}/undo",
    responses=error_responses(401, 404, 409, 422),
    summary="Undo a debt payment",
    description=_UNDO_DESCRIPTION.format(
        debt=" and what it took off the debt's balance (only what was owed, if it paid more)"
    ),
)
def undo_debt_payment(
    debt_id: uuid.UUID, payment_id: uuid.UUID, user: CurrentUser, payments: PaymentServiceDep
) -> DebtPaymentResponse:
    payment = payments.undo_debt_payment(user, debt_id, payment_id)
    return to_debt_payment_response(payment, payments.latest_commit(user.id))
