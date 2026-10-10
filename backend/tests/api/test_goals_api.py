"""/goals rules of its own: kinds, the single emergency goal, and what deleting
a goal releases. What every resource shares is in test_resource_contract.py;
cross-user access is in test_isolation.py."""

import uuid
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Allocation,
    Goal,
    GoalProjection,
    IncomeSource,
    Paycheck,
    PaycheckPlan,
    PayFrequency,
    PlanStatus,
    Reserve,
)
from nextpay_engine import GoalStatus, Reason, ReserveKind, Tier

type Json = dict[str, Any]
type Headers = dict[str, str]

CAMERA: Json = {
    "name": "Camera",
    "kind": "purchase",
    "target_cents": 200_000,
    "current_cents": 0,
    "priority": 2,
    "deadline": "2027-12-01",
}
EMERGENCY: Json = {
    "name": "Emergency fund",
    "kind": "emergency",
    "target_cents": 100_000,
    "current_cents": 0,
    "priority": 1,
    "deadline": None,
}


def create(client: TestClient, headers: Headers, body: Json = CAMERA, **changes: Any) -> Json:
    response = client.post("/goals", json={**body, **changes}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


def test_a_goal_has_exactly_these_fields(client: TestClient, ada: Headers) -> None:
    assert set(create(client, ada)) == {*CAMERA, "id", "created_at", "updated_at"}


@pytest.mark.parametrize("kind", ["emergency", "savings", "purchase"])
def test_every_kind_can_be_created(client: TestClient, ada: Headers, kind: str) -> None:
    assert create(client, ada, kind=kind)["kind"] == kind


@pytest.mark.parametrize(
    "change",
    [
        {"deadline": None},
        {"deadline": "2020-01-01"},  # already passed: the planner flags it
        {"current_cents": 250_000},  # more than the target
        {"current_cents": 30_000},  # some already saved
    ],
)
def test_these_goals_are_valid(client: TestClient, ada: Headers, change: Json) -> None:
    goal = create(client, ada, **change)
    assert {name: goal[name] for name in change} == change


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": ""}, "name"),
        ({"kind": "holiday"}, "kind"),
        ({"kind": None}, "kind"),
        ({"target_cents": 0}, "target_cents"),
        ({"target_cents": 2000.5}, "target_cents"),
        ({"target_cents": 100_000_000_001}, "target_cents"),
        ({"current_cents": -1}, "current_cents"),
        ({"current_cents": None}, "current_cents"),
        ({"priority": 0}, "priority"),
        ({"priority": 1001}, "priority"),
        ({"deadline": "December 2027"}, "deadline"),
        ({"deadline": 1_800_000_000}, "deadline"),
        ({"reserved_cents": 500}, "reserved_cents"),
    ],
)
def test_invalid_bodies_are_rejected_on_create_and_replace(
    client: TestClient, ada: Headers, db_session: Session, change: Json, field: str
) -> None:
    camera = create(client, ada)

    for response in (
        client.post("/goals", json={**CAMERA, **change}, headers=ada),
        client.put(f"/goals/{camera['id']}", json={**CAMERA, **change}, headers=ada),
    ):
        assert field in assert_error(response, 422, "validation_error")["message"]

    assert db_session.scalar(select(func.count()).select_from(Goal)) == 1
    assert client.get(f"/goals/{camera['id']}", headers=ada).json() == camera


# --- list ----------------------------------------------------------------------


def test_list_is_ordered_by_priority_then_name(client: TestClient, ada: Headers) -> None:
    trip = create(client, ada, name="Trip", kind="savings", priority=2)
    camera = create(client, ada)
    fund = create(client, ada, EMERGENCY)
    assert client.get("/goals", headers=ada).json() == {"items": [fund, camera, trip]}


def test_list_can_be_narrowed_to_one_kind(client: TestClient, ada: Headers) -> None:
    camera = create(client, ada)
    laptop = create(client, ada, name="Laptop", priority=1)
    create(client, ada, name="Trip", kind="savings")
    fund = create(client, ada, EMERGENCY)

    def of_kind(kind: str) -> Any:
        return client.get("/goals", params={"kind": kind}, headers=ada).json()

    assert of_kind("purchase") == {"items": [laptop, camera]}
    assert of_kind("emergency") == {"items": [fund]}
    assert len(client.get("/goals", headers=ada).json()["items"]) == 4


def test_an_unknown_kind_filter_is_a_validation_error(client: TestClient, ada: Headers) -> None:
    response = client.get("/goals", params={"kind": "holiday"}, headers=ada)
    assert "kind" in assert_error(response, 422, "validation_error")["message"]


# --- one emergency goal per user -----------------------------------------------


def test_a_second_emergency_goal_is_a_conflict(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    fund = create(client, ada, EMERGENCY)

    response = client.post("/goals", json={**EMERGENCY, "name": "Another"}, headers=ada)

    error = assert_error(response, 409, "emergency_goal_exists")
    assert "already have an emergency fund" in error["message"]
    assert client.get("/goals", headers=ada).json() == {"items": [fund]}
    # The request failed cleanly: the next one works.
    create(client, ada)
    assert db_session.scalar(select(func.count()).select_from(Goal)) == 2


def test_a_goal_cannot_be_turned_into_a_second_emergency_goal(
    client: TestClient, ada: Headers
) -> None:
    create(client, ada, EMERGENCY)
    camera = create(client, ada)

    response = client.put(
        f"/goals/{camera['id']}", json={**CAMERA, "kind": "emergency"}, headers=ada
    )

    assert_error(response, 409, "emergency_goal_exists")
    assert client.get(f"/goals/{camera['id']}", headers=ada).json() == camera


def test_the_emergency_goal_can_be_changed_and_replaced(client: TestClient, ada: Headers) -> None:
    fund = create(client, ada, EMERGENCY)
    path = f"/goals/{fund['id']}"

    raised = client.put(path, json={**EMERGENCY, "target_cents": 300_000}, headers=ada)
    assert raised.status_code == 200 and raised.json()["target_cents"] == 300_000

    # Once it is no longer the emergency goal, another goal can be.
    assert client.put(path, json={**EMERGENCY, "kind": "savings"}, headers=ada).status_code == 200
    create(client, ada, EMERGENCY, name="New fund")


def test_each_user_has_their_own_emergency_goal(
    client: TestClient, ada: Headers, bob: Headers
) -> None:
    create(client, ada, EMERGENCY)
    create(client, bob, EMERGENCY)


# --- delete: releasing the reserve (ADR 0003, ADR 0010) ------------------------


def seed_committed_plan(session: Session, user_id: uuid.UUID, goals: list[Json]) -> None:
    """A reserve for each goal, and one plan that funded and projected each of them."""
    source = IncomeSource(
        user_id=user_id,
        name="Day job",
        expected_amount_cents=150_000,
        pay_frequency=PayFrequency.BIWEEKLY,
        anchor_date=date(2026, 10, 2),
    )
    session.add(source)
    session.flush()
    paycheck = Paycheck(
        user_id=user_id,
        income_source_id=source.id,
        pay_date=date(2026, 10, 2),
        expected_amount_cents=150_000,
    )
    session.add(paycheck)
    session.flush()
    plan = PaycheckPlan(
        user_id=user_id,
        paycheck_id=paycheck.id,
        version=1,
        status=PlanStatus.DRAFT,
        engine_version="0.2.0",
        input_hash="a" * 64,
        as_of=date(2026, 10, 2),
        next_pay_date=date(2026, 10, 16),
        paycheck_amount_cents=150_000,
        available_balance_cents=0,
        safe_to_spend_cents=100_000,
        reserve_deficit_cents=0,
    )
    session.add(plan)
    session.flush()
    for position, goal in enumerate(goals):
        goal_id = uuid.UUID(goal["id"])
        session.add_all(
            [
                Reserve(
                    user_id=user_id, kind=ReserveKind.GOAL, goal_id=goal_id, amount_cents=24_000
                ),
                Allocation(
                    user_id=user_id,
                    plan_id=plan.id,
                    position=position,
                    tier=Tier.GOAL,
                    goal_id=goal_id,
                    requested_cents=6_667,
                    funded_cents=6_667,
                    reason=Reason.GOAL_DEADLINE,
                    name=goal["name"],
                    total_cents=200_000,
                    set_aside_cents=0,
                ),
                GoalProjection(
                    user_id=user_id,
                    plan_id=plan.id,
                    position=position,
                    goal_id=goal_id,
                    name=goal["name"],
                    contribution_cents=6_667,
                    still_needed_cents=193_333,
                    status=GoalStatus.ON_TRACK,
                ),
            ]
        )
    session.commit()


def test_deleting_a_goal_releases_its_reserve_and_keeps_plan_history(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    camera = create(client, ada, current_cents=24_000)
    trip = create(client, ada, name="Trip", kind="savings")
    user_id = uuid.UUID(client.get("/me", headers=ada).json()["id"])
    seed_committed_plan(db_session, user_id, [camera, trip])
    trip_id = uuid.UUID(trip["id"])

    assert client.delete(f"/goals/{camera['id']}", headers=ada).status_code == 204

    # Released: the camera's reserve is gone, so nothing subtracts it from Safe
    # to Spend any more. The other goal's reserve is untouched.
    assert db_session.scalars(select(Reserve.goal_id)).all() == [trip_id]
    # History survives: the plan still names the camera, without the link.
    allocations = db_session.execute(
        select(Allocation.name, Allocation.goal_id, Allocation.funded_cents).order_by(
            Allocation.position
        )
    ).all()
    assert allocations == [("Camera", None, 6_667), ("Trip", trip_id, 6_667)]
    projections = db_session.execute(
        select(GoalProjection.name, GoalProjection.goal_id).order_by(GoalProjection.position)
    ).all()
    assert projections == [("Camera", None), ("Trip", trip_id)]
    assert client.get("/goals", headers=ada).json() == {"items": [trip]}
