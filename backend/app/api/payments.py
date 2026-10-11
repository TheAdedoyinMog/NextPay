"""Payments toward bills and debts (ADR 0003, ADR 0011)."""

import uuid

from fastapi import APIRouter, status

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
    responses=error_responses(401, 404, 422),
    summary="Record a bill payment",
    description=(
        "Send `{}` to mark the bill paid in full today. The money set aside for the bill "
        "goes down by the amount paid, never below $0. Your balance is not changed: enter "
        "a new one when you next plan."
    ),
)
def pay_bill(
    bill_id: uuid.UUID, body: BillPaymentRequest, user: CurrentUser, payments: PaymentServiceDep
) -> BillPaymentResponse:
    return to_bill_payment_response(payments.pay_bill(user, bill_id, to_bill_payment_input(body)))


@router.get(
    "/bills/{bill_id}/payments",
    responses=error_responses(401, 404, 422),
    summary="List a bill's payments, newest first",
)
def list_bill_payments(
    bill_id: uuid.UUID, user: CurrentUser, payments: PaymentServiceDep
) -> BillPaymentListResponse:
    return to_bill_payment_list_response(payments.list_bill_payments(user.id, bill_id))


@router.post(
    "/debts/{debt_id}/payments",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 404, 422),
    summary="Record a debt payment",
    description=(
        "Send `{}` to record this month's minimum, paid today. The debt's balance and the "
        "money set aside for it both go down by the amount paid, never below $0."
    ),
)
def pay_debt(
    debt_id: uuid.UUID, body: DebtPaymentRequest, user: CurrentUser, payments: PaymentServiceDep
) -> DebtPaymentResponse:
    return to_debt_payment_response(payments.pay_debt(user, debt_id, to_debt_payment_input(body)))


@router.get(
    "/debts/{debt_id}/payments",
    responses=error_responses(401, 404, 422),
    summary="List a debt's payments, newest first",
)
def list_debt_payments(
    debt_id: uuid.UUID, user: CurrentUser, payments: PaymentServiceDep
) -> DebtPaymentListResponse:
    return to_debt_payment_list_response(payments.list_debt_payments(user.id, debt_id))
