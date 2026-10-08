from dataclasses import replace
from datetime import date

import pytest

from nextpay_engine.domain import (
    Bill,
    Debt,
    EssentialExpense,
    Goal,
    GoalKind,
    IncomeSource,
    Reserve,
    ReserveKind,
)
from nextpay_engine.money import Money
from nextpay_engine.pay_schedules import Biweekly
from nextpay_engine.recurrence import EveryNMonths
from nextpay_engine.state import FinancialState

JOB = IncomeSource("job", "Job", Biweekly(date(2026, 10, 2)), Money(150_000))
RENT = Bill("rent", "Rent", Money(80_000), EveryNMonths(date(2026, 1, 1)), priority=1)
GROCERIES = EssentialExpense("groceries", "Groceries", Money(20_000))
CAR = Debt("car", "Car", Money(900_000), 699, Money(15_000), due_day=20)
EMERGENCY = Goal("ef", "Emergency fund", GoalKind.EMERGENCY, Money(100_000), Money(0), 1)
CAMERA = Goal("camera", "Camera", GoalKind.PURCHASE, Money(200_000), Money(0), 2)

STATE = FinancialState(
    available_balance=Money(50_000),
    income_sources=(JOB,),
    bills=(RENT,),
    essentials=(GROCERIES,),
    debts=(CAR,),
    goals=(EMERGENCY, CAMERA),
    reserves=(
        Reserve(ReserveKind.BILL, "rent", Money(40_000)),
        Reserve(ReserveKind.BILL, "rent", Money(5_000)),
        Reserve(ReserveKind.GOAL, "camera", Money(10_000)),
        Reserve(ReserveKind.DEBT, "car", Money(7_500)),
    ),
)


def test_empty_state_needs_only_a_balance() -> None:
    state = FinancialState(available_balance=Money.zero())
    assert state.total_reserved() == Money.zero()
    assert state.emergency_goal is None


def test_balance_may_be_negative() -> None:
    assert replace(STATE, available_balance=Money(-500)).available_balance == Money(-500)


def test_balance_must_be_money() -> None:
    with pytest.raises(TypeError):
        replace(STATE, available_balance=500)


@pytest.mark.parametrize(
    "field", ["income_sources", "bills", "essentials", "debts", "goals", "reserves"]
)
def test_collections_must_be_tuples(field: str) -> None:
    with pytest.raises(TypeError, match=field):
        replace(STATE, **{field: list(getattr(STATE, field))})


@pytest.mark.parametrize(
    ("field", "duplicate"),
    [
        ("income_sources", JOB),
        ("bills", RENT),
        ("essentials", GROCERIES),
        ("debts", CAR),
        ("goals", CAMERA),
    ],
)
def test_ids_must_be_unique_per_kind(field: str, duplicate: object) -> None:
    with pytest.raises(ValueError, match="unique"):
        replace(STATE, **{field: (*getattr(STATE, field), duplicate)})


def test_same_id_across_kinds_is_allowed() -> None:
    goal = replace(CAMERA, id="rent")
    assert replace(STATE, goals=(EMERGENCY, goal), reserves=()).goals[1].id == "rent"


def test_at_most_one_emergency_goal() -> None:
    second = replace(EMERGENCY, id="ef2")
    with pytest.raises(ValueError, match="emergency"):
        replace(STATE, goals=(EMERGENCY, second))


def test_no_deadline_goal_share_defaults_to_20_percent() -> None:
    assert STATE.no_deadline_goal_share_bps == 2000
    assert replace(STATE, no_deadline_goal_share_bps=0).no_deadline_goal_share_bps == 0
    assert replace(STATE, no_deadline_goal_share_bps=10_000).no_deadline_goal_share_bps == 10_000


@pytest.mark.parametrize("share", [-1, 10_001, True, 20.0])
def test_no_deadline_goal_share_must_be_basis_points(share: object) -> None:
    with pytest.raises(ValueError, match="no_deadline_goal_share_bps"):
        replace(STATE, no_deadline_goal_share_bps=share)


@pytest.mark.parametrize(
    "reserve",
    [
        Reserve(ReserveKind.BILL, "camera", Money(1)),  # a goal id, not a bill id
        Reserve(ReserveKind.GOAL, "gone", Money(1)),
        Reserve(ReserveKind.DEBT, "rent", Money(1)),
    ],
)
def test_reserves_must_point_at_existing_targets(reserve: Reserve) -> None:
    with pytest.raises(ValueError, match="unknown"):
        replace(STATE, reserves=(reserve,))


def test_reserved_for_sums_per_target() -> None:
    assert STATE.reserved_for(ReserveKind.BILL, "rent") == Money(45_000)
    assert STATE.reserved_for(ReserveKind.GOAL, "camera") == Money(10_000)
    assert STATE.reserved_for(ReserveKind.GOAL, "ef") == Money.zero()
    assert STATE.reserved_for(ReserveKind.GOAL, "rent") == Money.zero()


def test_total_reserved() -> None:
    assert STATE.total_reserved() == Money(62_500)


def test_emergency_goal() -> None:
    assert STATE.emergency_goal is EMERGENCY
    assert replace(STATE, goals=(CAMERA,), reserves=()).emergency_goal is None


def test_income_source_lookup() -> None:
    assert STATE.income_source("job") is JOB
    with pytest.raises(ValueError, match="unknown income source"):
        STATE.income_source("other")
