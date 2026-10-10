"""/balance-snapshots: the signed-in user's balance over time (ADR 0010).

Append-only, so there is no route to change or delete a snapshot: a new
balance is a new snapshot.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import BalanceSnapshotServiceDep, CurrentUser
from app.api.errors import error_responses
from app.api.mappers import to_balance_snapshot_list_response, to_balance_snapshot_response
from app.core.limits import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.schemas.balances import (
    BalanceSnapshotListResponse,
    BalanceSnapshotRequest,
    BalanceSnapshotResponse,
)

router = APIRouter(prefix="/balance-snapshots", tags=["balance snapshots"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 422),
    summary="Record your current balance",
    description="The server stamps the time. The newest snapshot is your current balance.",
)
def create_balance_snapshot(
    body: BalanceSnapshotRequest, user: CurrentUser, snapshots: BalanceSnapshotServiceDep
) -> BalanceSnapshotResponse:
    return to_balance_snapshot_response(snapshots.create(user.id, body.amount_cents))


@router.get("", responses=error_responses(401, 422), summary="List your balances, newest first")
def list_balance_snapshots(
    user: CurrentUser,
    snapshots: BalanceSnapshotServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> BalanceSnapshotListResponse:
    return to_balance_snapshot_list_response(snapshots.list_for(user.id, limit))
