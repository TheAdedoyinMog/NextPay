"""POST /plans and GET /plans/{id}, end to end against PostgreSQL.

The setup is the design doc's worked example (the ``worked_example`` fixture). The
fake clock is at noon UTC on Oct 7, 2026. Committing is in test_plan_commit_api.py;
cross-user access is in test_planning_isolation.py.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Allocation, GoalProjection, Paycheck, PaycheckPlan, PlanStatus

type Json = dict[str, Any]
type Headers = dict[str, str]

PAYDAY = "2026-10-02"


def post(client: TestClient, headers: Headers, path: str, body: Json) -> Json:
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def plan(client: TestClient, headers: Headers, source: Json, pay_date: str = PAYDAY) -> Any:
    return client.post(
        "/plans", json={"income_source_id": source["id"], "pay_date": pay_date}, headers=headers
    )


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


# --- generating ----------------------------------------------------------------


def test_the_worked_example_end_to_end(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)

    response = plan(client, ada, world["job"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert {line["name"]: line["funded_cents"] for line in body["allocations"]} == {
        "Rent": 40_000,
        "Groceries": 20_000,
        "Car loan": 7_500,
        "Camera": 6_667,
    }
    assert body["safe_to_spend_cents"] == 75_833
    assert body["summary"] == "Safe to Spend is $758.33: what's left after everything above."
    assert (body["version"], body["status"], body["committed_at"]) == (1, "draft", None)
    assert (body["as_of"], body["next_pay_date"]) == ("2026-10-07", "2026-10-16")
    assert (body["paycheck_amount_cents"], body["available_balance_cents"]) == (150_000, 0)
    assert (body["balance_as_of"], body["reserve_deficit_cents"]) == (None, 0)
    assert body["engine_version"] == client.get("/health").json()["engine_version"]


def test_a_plan_has_exactly_these_fields(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    body = plan(client, ada, world["job"]).json()

    assert set(body) == {
        "id",
        "version",
        "status",
        "committed_at",
        "engine_version",
        "as_of",
        "paycheck",
        "next_pay_date",
        "paycheck_amount_cents",
        "available_balance_cents",
        "balance_as_of",
        "safe_to_spend_cents",
        "reserve_deficit_cents",
        "summary",
        "allocations",
        "goal_projections",
        "created_at",
    }
    assert body["paycheck"] == {
        "id": body["paycheck"]["id"],
        "income_source_id": world["job"]["id"],
        "income_source_name": "Day job",
        "income_source_archived": False,
        "pay_date": PAYDAY,
        "expected_amount_cents": 150_000,
        "actual_amount_cents": None,
        "amount_cents": 150_000,
        "plan": {
            "id": body["id"],
            "version": 1,
            "status": "draft",
            "safe_to_spend_cents": 75_833,
        },
    }
    assert body["allocations"][0] == {
        "position": 0,
        "tier": "bill",
        "target_id": world["rent"]["id"],
        "name": "Rent",
        "requested_cents": 40_000,
        "funded_cents": 40_000,
        "shortfall_cents": 0,
        "reason": "bill_due",
        "total_cents": 80_000,
        "set_aside_cents": 0,
        "due_date": "2026-10-20",
        "paychecks": 2,
        "days_covered": None,
        "days_in_period": None,
        "share_bps": None,
        "explanation": (
            "We reserved $400 toward Rent because the $800 bill is due Oct 20 and is split "
            "across the 2 paychecks before then."
        ),
    }
    assert [line["target_id"] for line in body["allocations"]] == [
        world[name]["id"] for name in ("rent", "groceries", "car", "camera")
    ]
    assert body["goal_projections"] == [
        {
            "goal_id": world["camera"]["id"],
            "name": "Camera",
            "deadline": "2027-11-20",
            "contribution_cents": 6_667,
            "still_needed_cents": 193_333,
            "projected_date": "2027-11-12",
            "status": "on_track",
            "suggested_deadline": None,
            "explanation": (
                "At $66.67 a paycheck, Camera will be reached by Nov 12, 2027, "
                "ahead of its deadline of Nov 20, 2027."
            ),
        }
    ]


def test_the_plan_is_stored_with_its_lines(
    client: TestClient, ada: Headers, db_session: Session, worked_example: Any
) -> None:
    world = worked_example(ada)
    body = plan(client, ada, world["job"]).json()

    stored = db_session.scalars(select(PaycheckPlan)).one()
    assert (str(stored.id), stored.status) == (body["id"], PlanStatus.DRAFT)
    assert len(stored.input_hash) == 64
    assert db_session.scalar(select(func.count()).select_from(Allocation)) == 4
    assert db_session.scalar(select(func.count()).select_from(GoalProjection)) == 1
    assert db_session.scalar(select(func.count()).select_from(Paycheck)) == 1


def test_get_returns_the_same_plan(client: TestClient, ada: Headers, worked_example: Any) -> None:
    world = worked_example(ada)
    body = plan(client, ada, world["job"]).json()

    response = client.get(f"/plans/{body['id']}", headers=ada)

    assert response.status_code == 200
    assert response.json() == body


def test_planning_again_with_nothing_changed_returns_the_same_draft_with_200(
    client: TestClient, ada: Headers, db_session: Session, worked_example: Any
) -> None:
    world = worked_example(ada)
    first = plan(client, ada, world["job"]).json()

    again = plan(client, ada, world["job"])

    assert again.status_code == 200
    assert again.json() == first
    assert db_session.scalar(select(func.count()).select_from(PaycheckPlan)) == 1


def test_a_change_makes_a_new_version_and_the_old_one_is_superseded(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    first = plan(client, ada, world["job"]).json()
    rent = world["rent"]
    read_only = {"id", "reserved_cents", "created_at", "updated_at"}
    changed = {name: rent[name] for name in rent if name not in read_only}
    replaced = client.put(
        f"/bills/{rent['id']}", json={**changed, "amount_cents": 90_000}, headers=ada
    )
    assert replaced.status_code == 200, replaced.text

    second = plan(client, ada, world["job"])

    assert second.status_code == 201
    assert (second.json()["version"], second.json()["status"]) == (2, "draft")
    assert second.json()["allocations"][0]["funded_cents"] == 45_000
    old = client.get(f"/plans/{first['id']}", headers=ada).json()
    assert (old["status"], old["allocations"][0]["funded_cents"]) == ("superseded", 40_000)
    # The paycheck now points at the new draft.
    assert second.json()["paycheck"]["plan"]["id"] == second.json()["id"]


def test_the_latest_balance_and_the_actual_amount_are_used(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    balance = post(client, ada, "/balance-snapshots", {"amount_cents": 25_000})
    recorded = client.put(
        f"/income-sources/{world['job']['id']}/paychecks/{PAYDAY}",
        json={"actual_amount_cents": 140_000},
        headers=ada,
    )
    assert recorded.status_code == 200

    body = plan(client, ada, world["job"]).json()

    assert (body["available_balance_cents"], body["balance_as_of"]) == (25_000, balance["as_of"])
    assert body["paycheck_amount_cents"] == 140_000
    assert body["paycheck"]["actual_amount_cents"] == 140_000
    assert body["safe_to_spend_cents"] == 75_833 + 25_000 - 10_000


def test_the_timeline_shows_each_paychecks_current_plan(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    body = plan(client, ada, world["job"]).json()

    first, second, *_ = client.get("/paychecks", headers=ada).json()["items"]

    assert first == body["paycheck"]
    assert (second["id"], second["plan"]) == (None, None)


def test_a_later_paycheck_can_be_planned_ahead(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    body = plan(client, ada, world["job"], "2026-10-16").json()
    # One paycheck is left before rent is due on Oct 20, so it carries all of it.
    assert body["allocations"][0]["funded_cents"] == 80_000
    assert body["allocations"][0]["paychecks"] == 1
    assert body["next_pay_date"] == "2026-10-30"


def test_settings_decide_the_day_and_the_goal_share(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    trip = {
        "name": "Trip",
        "kind": "savings",
        "target_cents": 500_000,
        "current_cents": 0,
        "priority": 3,
        "deadline": None,
    }
    post(client, ada, "/goals", trip)
    before = plan(client, ada, world["job"]).json()
    assert before["allocations"][-1]["share_bps"] == 2000

    settings = {"timezone": "Pacific/Kiritimati", "no_deadline_goal_share_bps": 5000}
    assert client.put("/me/settings", json=settings, headers=ada).status_code == 200
    after = plan(client, ada, world["job"]).json()

    # Noon UTC on Oct 7 is already Oct 8 on Kiritimati (UTC+14).
    assert (before["as_of"], after["as_of"]) == ("2026-10-07", "2026-10-08")
    assert after["version"] == 2
    trip_line = after["allocations"][-1]
    assert (trip_line["name"], trip_line["share_bps"]) == ("Trip", 5000)
    assert trip_line["funded_cents"] > before["allocations"][-1]["funded_cents"]


# --- what cannot be planned ----------------------------------------------------


def test_a_committed_paycheck_cannot_be_planned_again(
    client: TestClient, ada: Headers, db_session: Session, worked_example: Any
) -> None:
    world = worked_example(ada)
    plan(client, ada, world["job"])
    stored = db_session.scalars(select(PaycheckPlan)).one()
    stored.status = PlanStatus.COMMITTED
    stored.committed_at = stored.created_at
    db_session.commit()

    error = assert_error(plan(client, ada, world["job"]), 409, "paycheck_already_committed")
    assert "already has a committed plan" in error["message"]
    assert db_session.scalar(select(func.count()).select_from(PaycheckPlan)) == 1


def test_a_date_that_is_not_a_payday_is_rejected(
    client: TestClient, ada: Headers, db_session: Session, worked_example: Any
) -> None:
    world = worked_example(ada)
    error = assert_error(plan(client, ada, world["job"], "2026-10-03"), 422, "invalid_input")
    assert "2026-10-03 is not a payday for Day job" in error["message"]
    assert db_session.scalar(select(func.count()).select_from(Paycheck)) == 0


def test_unknown_and_archived_sources_are_not_found(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    assert_error(plan(client, ada, {"id": str(uuid.uuid4())}), 404, "not_found")

    plan(client, ada, world["job"])  # gives the source a paycheck, so deleting archives it
    assert client.delete(f"/income-sources/{world['job']['id']}", headers=ada).status_code == 204
    assert_error(plan(client, ada, world["job"]), 404, "not_found")
    assert_error(plan(client, ada, world["job"], "2026-10-16"), 404, "not_found")


def test_an_archived_sources_plan_can_still_be_read(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    body = plan(client, ada, world["job"]).json()
    client.delete(f"/income-sources/{world['job']['id']}", headers=ada)

    read = client.get(f"/plans/{body['id']}", headers=ada).json()

    assert read["paycheck"]["income_source_archived"] is True
    assert read == {**body, "paycheck": {**body["paycheck"], "income_source_archived": True}}


def test_a_plan_outlives_the_bill_and_goal_it_mentions(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    body = plan(client, ada, world["job"]).json()
    assert client.delete(f"/bills/{world['rent']['id']}", headers=ada).status_code == 204
    assert client.delete(f"/goals/{world['camera']['id']}", headers=ada).status_code == 204

    read = client.get(f"/plans/{body['id']}", headers=ada).json()

    assert [line["target_id"] for line in read["allocations"]] == [
        None,
        world["groceries"]["id"],
        world["car"]["id"],
        None,
    ]
    assert read["goal_projections"][0]["goal_id"] is None
    # Every name, number, and sentence is unchanged.
    for before, after in zip(body["allocations"], read["allocations"], strict=True):
        assert {**before, "target_id": None} == {**after, "target_id": None}
    assert read["goal_projections"][0]["explanation"] == body["goal_projections"][0]["explanation"]
    assert read["summary"] == body["summary"]


@pytest.mark.parametrize(
    ("body", "mention"),
    [
        ({"pay_date": PAYDAY}, "income_source_id"),
        ({"income_source_id": str(uuid.uuid4())}, "pay_date"),
        ({"income_source_id": "nope", "pay_date": PAYDAY}, "income_source_id"),
        ({"income_source_id": str(uuid.uuid4()), "pay_date": "Friday"}, "pay_date"),
        ({"income_source_id": str(uuid.uuid4()), "pay_date": 1_791_000_000}, "pay_date"),
        (
            {"income_source_id": str(uuid.uuid4()), "pay_date": PAYDAY, "as_of": "2020-01-01"},
            "as_of",
        ),
    ],
)
def test_invalid_bodies_are_rejected(
    client: TestClient, ada: Headers, body: Json, mention: str
) -> None:
    response = client.post("/plans", json=body, headers=ada)
    assert mention in assert_error(response, 422, "validation_error")["message"]


def test_an_unknown_plan_is_not_found_and_a_malformed_id_is_invalid(
    client: TestClient, ada: Headers
) -> None:
    assert_error(client.get(f"/plans/{uuid.uuid4()}", headers=ada), 404, "not_found")
    malformed = client.get("/plans/first", headers=ada)
    assert "plan_id" in assert_error(malformed, 422, "validation_error")["message"]


def test_plan_routes_require_a_signed_in_user(
    client: TestClient, ada: Headers, db_session: Session, worked_example: Any
) -> None:
    world = worked_example(ada)
    body = plan(client, ada, world["job"]).json()

    assert_error(client.get(f"/plans/{body['id']}"), 401, "not_authenticated")
    stranger = client.post(
        "/plans", json={"income_source_id": world["job"]["id"], "pay_date": PAYDAY}
    )
    assert_error(stranger, 401, "not_authenticated")
    assert db_session.scalar(select(func.count()).select_from(PaycheckPlan)) == 1
