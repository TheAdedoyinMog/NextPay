"""/plans: what to do with one paycheck (ADR 0003, ADR 0011)."""

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, PlanServiceDep
from app.api.errors import error_responses
from app.api.mappers import to_plan_response
from app.schemas.plans import PlanRequest, PlanResponse

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": PlanResponse, "description": "Nothing changed: the current draft."},
        **error_responses(401, 404, 409, 422),
    },
    summary="Plan a paycheck",
    description=(
        "Makes a draft plan for one paycheck, as of today in your time zone, from your "
        "current details and latest balance (the balance before this paycheck). Planning "
        "the same paycheck again replaces the draft with a new version; if nothing has "
        "changed, the same draft comes back with 200. A paycheck whose plan is committed "
        "cannot be planned again: 409 `paycheck_already_committed`."
    ),
)
def create_plan(
    body: PlanRequest, user: CurrentUser, plans: PlanServiceDep, response: Response
) -> PlanResponse:
    details, created = plans.generate(user, body.income_source_id, body.pay_date)
    if not created:
        response.status_code = status.HTTP_200_OK
    return to_plan_response(details)


@router.get("/{plan_id}", responses=error_responses(401, 404, 422), summary="Get a plan")
def get_plan(plan_id: uuid.UUID, user: CurrentUser, plans: PlanServiceDep) -> PlanResponse:
    return to_plan_response(plans.get(user, plan_id))


@router.post(
    "/{plan_id}/commit",
    responses=error_responses(401, 404, 409, 422),
    summary="Commit a plan",
    description=(
        "Accepts a draft: what it put toward bills, debts and goals is set aside, so it "
        "is never counted as spendable again, and each goal's progress grows by its share. "
        "A committed plan is final. Committing it again changes nothing and returns it. "
        "409 `plan_out_of_date` if your details changed since the plan was made (generate "
        "a new one), `plan_superseded` if a newer draft replaced it, and "
        "`paycheck_already_committed` if another plan for the paycheck is committed."
    ),
)
def commit_plan(plan_id: uuid.UUID, user: CurrentUser, plans: PlanServiceDep) -> PlanResponse:
    return to_plan_response(plans.commit(user, plan_id))
