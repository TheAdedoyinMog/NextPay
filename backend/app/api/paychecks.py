"""Paychecks: the timeline of paydays, and recording what arrived (ADR 0011).

A paycheck is addressed by its income source and pay date, not by an id: it
has no row until something is recorded or planned for it, and the natural key
is what the app knows from the timeline.
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, PaycheckServiceDep
from app.api.errors import error_responses
from app.api.mappers import to_paycheck_list_response, to_paycheck_response
from app.schemas.paychecks import ActualAmountRequest, PaycheckListResponse, PaycheckResponse

router = APIRouter(tags=["paychecks"])


@router.get(
    "/paychecks",
    responses=error_responses(401, 422),
    summary="List your paydays",
    description=(
        "Every payday from `start` to `end`, across your income sources, with what has "
        "been recorded for each. Defaults to a week back from today and two months ahead."
    ),
)
def list_paychecks(
    user: CurrentUser,
    paychecks: PaycheckServiceDep,
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
) -> PaycheckListResponse:
    return to_paycheck_list_response(paychecks.timeline(user, start, end))


@router.put(
    "/income-sources/{income_source_id}/paychecks/{pay_date}",
    responses=error_responses(401, 404, 422),
    summary="Record what a paycheck actually paid",
    description=(
        "`pay_date` must be one of the source's paydays. A draft plan for this paycheck "
        "becomes out of date; a committed plan is final and does not change."
    ),
)
def record_actual_amount(
    income_source_id: uuid.UUID,
    pay_date: date,
    body: ActualAmountRequest,
    user: CurrentUser,
    paychecks: PaycheckServiceDep,
) -> PaycheckResponse:
    return to_paycheck_response(
        paychecks.record_actual(user, income_source_id, pay_date, body.actual_amount_cents)
    )
