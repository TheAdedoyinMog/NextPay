"""POST /plans/{id}/commit, end to end against PostgreSQL (ADR 0003, ADR 0011).

The setup is the design doc's worked example (the ``worked_example`` fixture).
Cross-user access is in test_planning_isolation.py.
"""

import uuid
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaycheckPlan, PlanStatus, Reserve
from nextpay_engine import ReserveKind

type Json = dict[str, Any]
type Headers = dict[str, str]
type Clock = Any  # conftest.FakeClock

PAYDAY = "2026-10-02"


def draft(client: TestClient, headers: Headers, source: Json, pay_date: str = PAYDAY) -> Json:
    response = client.post(
        "/plans", json={"income_source_id": source["id"], "pay_date": pay_date}, headers=headers
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def commit(client: TestClient, headers: Headers, plan: Json) -> Any:
    return client.post(f"/plans/{plan['id']}/commit", headers=headers)


def reserves(session: Session) -> dict[tuple[ReserveKind, str], int]:
    session.expire_all()
    return {
        (row.kind, str(row.bill_id or row.debt_id or row.goal_id)): row.amount_cents
        for row in session.scalars(select(Reserve))
    }


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


def test_committing_sets_aside_what_the_plan_funded(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session, clock: Clock
) -> None:
    world = worked_example(ada)
    plan = draft(client, ada, world["job"])
    clock.advance(timedelta(minutes=5))

    response = commit(client, ada, plan)

    assert response.status_code == 200, response.text
    committed = response.json()
    assert (committed["status"], committed["committed_at"]) == ("committed", "2026-10-07T12:05:00Z")
    assert committed["paycheck"]["plan"]["status"] == "committed"
    # Nothing about the plan itself changes.
    unchanged = {"status", "committed_at", "paycheck"}
    assert {k: v for k, v in committed.items() if k not in unchanged} == {
        k: v for k, v in plan.items() if k not in unchanged
    }
    assert client.get(f"/plans/{plan['id']}", headers=ada).json() == committed

    # Rent, the car minimum and the camera are set aside; groceries are not.
    assert reserves(db_session) == {
        (ReserveKind.BILL, world["rent"]["id"]): 40_000,
        (ReserveKind.DEBT, world["car"]["id"]): 7_500,
        (ReserveKind.GOAL, world["camera"]["id"]): 6_667,
    }
    camera = client.get(f"/goals/{world['camera']['id']}", headers=ada).json()
    assert camera["current_cents"] == 6_667
    car = client.get(f"/debts/{world['car']['id']}", headers=ada).json()
    assert car["balance_cents"] == 900_000


def test_committing_twice_returns_the_plan_and_reserves_nothing_more(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session, clock: Clock
) -> None:
    world = worked_example(ada)
    plan = draft(client, ada, world["job"])
    first = commit(client, ada, plan).json()
    after_first = reserves(db_session)
    clock.advance(timedelta(minutes=5))

    again = commit(client, ada, plan)

    assert again.status_code == 200
    assert again.json() == first
    assert reserves(db_session) == after_first
    assert (
        client.get(f"/goals/{world['camera']['id']}", headers=ada).json()["current_cents"] == 6_667
    )


def test_a_committed_paycheck_cannot_be_planned_again(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    plan = draft(client, ada, world["job"])
    commit(client, ada, plan)

    response = client.post(
        "/plans", json={"income_source_id": world["job"]["id"], "pay_date": PAYDAY}, headers=ada
    )

    assert_error(response, 409, "paycheck_already_committed")
    assert db_session.scalars(select(PaycheckPlan.status)).all() == [PlanStatus.COMMITTED]
    # Recording what actually arrived is still allowed, and changes nothing committed.
    recorded = client.put(
        f"/income-sources/{world['job']['id']}/paychecks/{PAYDAY}",
        json={"actual_amount_cents": 140_000},
        headers=ada,
    )
    assert recorded.status_code == 200
    assert recorded.json()["plan"]["status"] == "committed"
    after = client.get(f"/plans/{plan['id']}", headers=ada).json()
    assert (after["paycheck_amount_cents"], after["safe_to_spend_cents"]) == (150_000, 75_833)


def test_a_draft_is_out_of_date_after_a_change_and_nothing_is_reserved(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    plan = draft(client, ada, world["job"])
    balance = client.post("/balance-snapshots", json={"amount_cents": 25_000}, headers=ada)
    assert balance.status_code == 201

    error = assert_error(commit(client, ada, plan), 409, "plan_out_of_date")

    assert "Generate a new plan" in error["message"]
    assert reserves(db_session) == {}
    assert client.get(f"/plans/{plan['id']}", headers=ada).json()["status"] == "draft"
    assert client.get(f"/goals/{world['camera']['id']}", headers=ada).json()["current_cents"] == 0

    # Planning again supersedes the stale draft, and the new one commits.
    fresh = draft(client, ada, world["job"])
    assert (fresh["version"], fresh["available_balance_cents"]) == (2, 25_000)
    assert_error(commit(client, ada, plan), 409, "plan_superseded")
    assert commit(client, ada, fresh).json()["status"] == "committed"
    assert reserves(db_session)[ReserveKind.BILL, world["rent"]["id"]] == 40_000


def test_deleting_a_target_makes_the_draft_out_of_date(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    plan = draft(client, ada, world["job"])
    assert client.delete(f"/goals/{world['camera']['id']}", headers=ada).status_code == 204

    assert_error(commit(client, ada, plan), 409, "plan_out_of_date")
    assert reserves(db_session) == {}


def test_archiving_the_income_source_makes_its_draft_out_of_date(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    plan = draft(client, ada, world["job"])
    assert client.delete(f"/income-sources/{world['job']['id']}", headers=ada).status_code == 204

    assert_error(commit(client, ada, plan), 409, "plan_out_of_date")
    assert reserves(db_session) == {}


def test_paychecks_are_committed_in_turn_each_seeing_the_last_ones_reserves(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    first = draft(client, ada, world["job"])
    second = draft(client, ada, world["job"], "2026-10-16")
    assert commit(client, ada, first).status_code == 200

    # The second draft was made before the first paycheck set $400 of rent aside.
    assert_error(commit(client, ada, second), 409, "plan_out_of_date")

    replanned = draft(client, ada, world["job"], "2026-10-16")
    rent = replanned["allocations"][0]
    assert (rent["set_aside_cents"], rent["funded_cents"], rent["paychecks"]) == (40_000, 40_000, 1)
    assert "with $400 already set aside" in rent["explanation"]
    assert commit(client, ada, replanned).status_code == 200
    assert reserves(db_session) == {
        (ReserveKind.BILL, world["rent"]["id"]): 80_000,
        (ReserveKind.DEBT, world["car"]["id"]): 15_000,
        (ReserveKind.GOAL, world["camera"]["id"]): 6_667
        + replanned["allocations"][3]["funded_cents"],
    }


def test_the_database_refuses_a_second_committed_plan_even_if_one_slips_through(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    plan = draft(client, ada, world["job"])
    commit(client, ada, plan)
    committed = db_session.scalars(select(PaycheckPlan)).one()
    # A second draft for the paycheck cannot be made through the API, so add one directly.
    stray = PaycheckPlan(
        user_id=committed.user_id,
        paycheck_id=committed.paycheck_id,
        version=2,
        status=PlanStatus.DRAFT,
        engine_version=committed.engine_version,
        input_hash=committed.input_hash,
        as_of=committed.as_of,
        next_pay_date=committed.next_pay_date,
        paycheck_amount_cents=150_000,
        available_balance_cents=0,
        safe_to_spend_cents=75_833,
        reserve_deficit_cents=0,
    )
    db_session.add(stray)
    db_session.commit()
    before = reserves(db_session)

    response = client.post(f"/plans/{stray.id}/commit", headers=ada)

    assert_error(response, 409, "paycheck_already_committed")
    assert reserves(db_session) == before
    statuses = db_session.scalars(select(PaycheckPlan.status).order_by(PaycheckPlan.version)).all()
    assert statuses == [PlanStatus.COMMITTED, PlanStatus.DRAFT]


def test_an_unknown_plan_is_not_found_and_a_malformed_id_is_invalid(
    client: TestClient, ada: Headers
) -> None:
    assert_error(client.post(f"/plans/{uuid.uuid4()}/commit", headers=ada), 404, "not_found")
    malformed = client.post("/plans/first/commit", headers=ada)
    assert "plan_id" in assert_error(malformed, 422, "validation_error")["message"]


def test_commit_requires_a_signed_in_user(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    plan = draft(client, ada, world["job"])

    assert_error(client.post(f"/plans/{plan['id']}/commit"), 401, "not_authenticated")

    assert reserves(db_session) == {}
    assert client.get(f"/plans/{plan['id']}", headers=ada).json()["status"] == "draft"
