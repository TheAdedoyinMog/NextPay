"""Adding to, drawing down, and capping a reserve, with the in-memory fake store."""

import uuid
from typing import Any

import pytest

from app.services.reserves import (
    ReserveService,
    add_to_reserve,
    cap_reserve,
    draw_down_reserve,
)
from nextpay_engine import ReserveKind

USER = uuid.uuid4()
OTHER_USER = uuid.uuid4()

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any

KINDS = [
    (ReserveKind.BILL, "bill_id"),
    (ReserveKind.GOAL, "goal_id"),
    (ReserveKind.DEBT, "debt_id"),
]


def test_amounts_are_reported_per_target_for_one_kind_and_one_user(reserves: Fake) -> None:
    rent, phone, camera, loan = (uuid.uuid4() for _ in range(4))
    add_to_reserve(reserves, USER, ReserveKind.BILL, rent, 40_000)
    add_to_reserve(reserves, USER, ReserveKind.BILL, phone, 3_000)
    add_to_reserve(reserves, USER, ReserveKind.GOAL, camera, 6_667)
    add_to_reserve(reserves, USER, ReserveKind.DEBT, loan, 7_500)
    add_to_reserve(reserves, OTHER_USER, ReserveKind.BILL, rent, 999)
    draw_down_reserve(reserves, USER, ReserveKind.BILL, phone, 3_000)
    service = ReserveService(reserves=reserves)

    # A reserve drawn down to $0 is still reported, as 0.
    assert service.amounts(USER, ReserveKind.BILL) == {rent: 40_000, phone: 0}
    assert service.amounts(USER, ReserveKind.GOAL) == {camera: 6_667}
    assert service.amounts(USER, ReserveKind.DEBT) == {loan: 7_500}
    assert service.amounts(OTHER_USER, ReserveKind.BILL) == {rent: 999}
    assert service.amounts(OTHER_USER, ReserveKind.GOAL) == {}
    assert service.amounts(uuid.uuid4(), ReserveKind.BILL) == {}


@pytest.mark.parametrize(("kind", "column"), KINDS)
def test_the_first_amount_creates_the_reserve_for_its_kind_of_target(
    reserves: Fake, kind: ReserveKind, column: str
) -> None:
    target = uuid.uuid4()

    reserve = add_to_reserve(reserves, USER, kind, target, 40_000)

    assert reserves.rows == {reserve.id: reserve}
    assert (reserve.user_id, reserve.kind, reserve.amount_cents) == (USER, kind, 40_000)
    set_columns = {name for _, name in KINDS if getattr(reserve, name) is not None}
    assert set_columns == {column} and getattr(reserve, column) == target


def test_later_amounts_add_to_the_same_reserve(reserves: Fake) -> None:
    rent, phone = uuid.uuid4(), uuid.uuid4()
    first = add_to_reserve(reserves, USER, ReserveKind.BILL, rent, 40_000)
    add_to_reserve(reserves, USER, ReserveKind.BILL, phone, 3_000)

    again = add_to_reserve(reserves, USER, ReserveKind.BILL, rent, 40_000)

    assert again is first and first.amount_cents == 80_000
    assert len(reserves.rows) == 2


def test_a_reserve_belongs_to_one_user(reserves: Fake) -> None:
    target = uuid.uuid4()
    mine = add_to_reserve(reserves, USER, ReserveKind.GOAL, target, 500)
    theirs = add_to_reserve(reserves, OTHER_USER, ReserveKind.GOAL, target, 900)
    assert mine is not theirs
    assert draw_down_reserve(reserves, OTHER_USER, ReserveKind.GOAL, target, 100) == 100
    assert (mine.amount_cents, theirs.amount_cents) == (500, 800)


@pytest.mark.parametrize(
    ("paid", "drawn", "left"),
    [(30_000, 30_000, 10_000), (40_000, 40_000, 0), (55_000, 40_000, 0)],
)
def test_drawing_down_takes_what_was_paid_but_never_goes_below_zero(
    reserves: Fake, paid: int, drawn: int, left: int
) -> None:
    rent = uuid.uuid4()
    reserve = add_to_reserve(reserves, USER, ReserveKind.BILL, rent, 40_000)

    assert draw_down_reserve(reserves, USER, ReserveKind.BILL, rent, paid) == drawn

    assert reserve.amount_cents == left


def test_drawing_down_a_target_with_no_reserve_does_nothing(reserves: Fake) -> None:
    assert draw_down_reserve(reserves, USER, ReserveKind.DEBT, uuid.uuid4(), 15_000) == 0
    assert reserves.rows == {}


@pytest.mark.parametrize(
    ("cap", "left"), [(25_000, 25_000), (0, 0), (40_000, 40_000), (99_000, 40_000)]
)
def test_capping_lowers_a_reserve_and_never_raises_it(reserves: Fake, cap: int, left: int) -> None:
    camera = uuid.uuid4()
    reserve = add_to_reserve(reserves, USER, ReserveKind.GOAL, camera, 40_000)

    cap_reserve(reserves, USER, ReserveKind.GOAL, camera, cap)

    assert reserve.amount_cents == left


def test_capping_a_target_with_no_reserve_does_nothing(reserves: Fake) -> None:
    cap_reserve(reserves, USER, ReserveKind.GOAL, uuid.uuid4(), 0)
    assert reserves.rows == {}
