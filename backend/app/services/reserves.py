"""Changing what is set aside for a bill, goal, or debt (ADR 0003, ADR 0011).

Committing a plan adds to reserves; recording a payment draws one down. A
reserve never goes below $0. Callers hold the user's lock, so two changes to
one reserve cannot interleave.
"""

import uuid
from collections.abc import Sequence
from typing import Protocol

from app.models import Reserve
from nextpay_engine import ReserveKind

_TARGET_COLUMN = {
    ReserveKind.BILL: "bill_id",
    ReserveKind.GOAL: "goal_id",
    ReserveKind.DEBT: "debt_id",
}


class ReserveListing(Protocol):
    def list_for(self, user_id: uuid.UUID) -> Sequence[Reserve]: ...


class ReserveService:
    """Reading what is set aside, for showing it next to a bill, debt, or goal."""

    def __init__(self, *, reserves: ReserveListing) -> None:
        self._reserves = reserves

    def amounts(self, user_id: uuid.UUID, kind: ReserveKind) -> dict[uuid.UUID, int]:
        """Cents set aside for each of ``user_id``'s targets of one kind, by target id.

        A target that is missing has nothing set aside.
        """
        column = _TARGET_COLUMN[kind]
        return {
            getattr(reserve, column): reserve.amount_cents
            for reserve in self._reserves.list_for(user_id)
            if reserve.kind is kind
        }


class ReserveStore(Protocol):
    def find(
        self, user_id: uuid.UUID, kind: ReserveKind, target_id: uuid.UUID
    ) -> Reserve | None: ...
    def add(self, row: Reserve) -> Reserve: ...


def add_to_reserve(
    reserves: ReserveStore, user_id: uuid.UUID, kind: ReserveKind, target_id: uuid.UUID, cents: int
) -> Reserve:
    """Set ``cents`` more aside for one target, creating its reserve if it has none."""
    reserve = reserves.find(user_id, kind, target_id)
    if reserve is None:
        reserve = Reserve(id=uuid.uuid4(), user_id=user_id, kind=kind, amount_cents=cents)
        setattr(reserve, _TARGET_COLUMN[kind], target_id)
        return reserves.add(reserve)
    reserve.amount_cents += cents
    return reserve


def draw_down_reserve(
    reserves: ReserveStore, user_id: uuid.UUID, kind: ReserveKind, target_id: uuid.UUID, cents: int
) -> int:
    """Take up to ``cents`` out of one target's reserve; returns how much came out.

    Paying more than was set aside empties the reserve and stops there.
    """
    reserve = reserves.find(user_id, kind, target_id)
    if reserve is None:
        return 0
    drawn = min(cents, reserve.amount_cents)
    reserve.amount_cents -= drawn
    return drawn


def cap_reserve(
    reserves: ReserveStore, user_id: uuid.UUID, kind: ReserveKind, target_id: uuid.UUID, cents: int
) -> None:
    """Make sure no more than ``cents`` is set aside for one target."""
    reserve = reserves.find(user_id, kind, target_id)
    if reserve is not None and reserve.amount_cents > cents:
        reserve.amount_cents = cents
