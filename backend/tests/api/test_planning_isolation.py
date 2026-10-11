"""No user can plan with, read, commit, or pay against another user's data (ADR 0006, 0011).

test_isolation.py covers the resource routes. These are the planning routes:
each one is called by Bob against something of Ada's, and must answer exactly
like the same call against an id that does not exist, and change nothing.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import BillPayment, DebtPayment, Paycheck, PaycheckPlan, PlanStatus, Reserve

type Json = dict[str, Any]
type Headers = dict[str, str]

PAYDAY = "2026-10-02"

# (name, method, path, body). {job}, {rent}, {car} and {plan} are ids of Ada's.
ROUTES: list[tuple[str, str, str, Json | None]] = [
    ("plan a paycheck", "POST", "/plans", {"income_source_id": "{job}", "pay_date": PAYDAY}),
    ("read a plan", "GET", "/plans/{plan}", None),
    ("commit a plan", "POST", "/plans/{plan}/commit", None),
    (
        "record actual pay",
        "PUT",
        "/income-sources/{job}/paychecks/" + PAYDAY,
        {"actual_amount_cents": 1},
    ),
    ("pay a bill", "POST", "/bills/{rent}/payments", {}),
    ("list a bill's payments", "GET", "/bills/{rent}/payments", None),
    ("pay a debt", "POST", "/debts/{car}/payments", {}),
    ("list a debt's payments", "GET", "/debts/{car}/payments", None),
]


@pytest.fixture
def adas(client: TestClient, ada: Headers, worked_example: Any) -> dict[str, str]:
    """Ada's worked example with a draft plan; the ids the routes above need."""
    world = worked_example(ada)
    plan = client.post(
        "/plans", json={"income_source_id": world["job"]["id"], "pay_date": PAYDAY}, headers=ada
    )
    assert plan.status_code == 201, plan.text
    return {
        "job": world["job"]["id"],
        "rent": world["rent"]["id"],
        "car": world["car"]["id"],
        "plan": plan.json()["id"],
    }


def fill(template: Any, ids: dict[str, str]) -> Any:
    if isinstance(template, str):
        return template.format(**ids)
    if isinstance(template, dict):
        return {key: fill(value, ids) for key, value in template.items()}
    return template


def snapshot(session: Session) -> dict[str, Any]:
    """Everything a planning route could have changed."""
    session.expire_all()
    return {
        "plans": session.execute(
            select(PaycheckPlan.id, PaycheckPlan.status, PaycheckPlan.version)
        ).all(),
        "paychecks": session.execute(select(Paycheck.id, Paycheck.actual_amount_cents)).all(),
        "reserves": session.scalar(select(func.count()).select_from(Reserve)),
        "bill_payments": session.scalar(select(func.count()).select_from(BillPayment)),
        "debt_payments": session.scalar(select(func.count()).select_from(DebtPayment)),
    }


@pytest.mark.parametrize(("name", "method", "path", "body"), ROUTES, ids=[r[0] for r in ROUTES])
def test_another_users_data_answers_like_data_that_does_not_exist(
    client: TestClient,
    ada: Headers,
    bob: Headers,
    adas: dict[str, str],
    db_session: Session,
    name: str,
    method: str,
    path: str,
    body: Json | None,
) -> None:
    before = snapshot(db_session)
    nobodys = dict.fromkeys(adas, str(uuid.uuid4()))

    response = client.request(method, fill(path, adas), json=fill(body, adas), headers=bob)
    missing = client.request(method, fill(path, nobodys), json=fill(body, nobodys), headers=bob)

    assert response.status_code == missing.status_code == 404, response.text
    assert response.json() == missing.json()
    assert response.json()["error"]["code"] == "not_found"
    assert snapshot(db_session) == before
    # Ada can still use it herself.
    assert client.request(method, fill(path, adas), json=fill(body, adas), headers=ada).is_success


def test_every_planning_route_is_in_the_table() -> None:
    planning = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method, operation in operations.items()
        # /health has no tags.
        if set(operation.get("tags", [])) & {"plans", "paychecks", "payments"}
    }
    assert len(planning) == 9
    covered = {
        (method, path.replace("{job}", "{income_source_id}").replace(PAYDAY, "{pay_date}"))
        for _, method, path, _ in ROUTES
    }
    covered = {
        (
            method,
            path.replace("{plan}", "{plan_id}")
            .replace("{rent}", "{bill_id}")
            .replace("{car}", "{debt_id}"),
        )
        for method, path in covered
    }
    # GET /paychecks takes no id; test_the_timeline_is_each_users_own covers it.
    assert planning - covered == {("GET", "/paychecks")}
    assert covered <= planning


def test_the_timeline_is_each_users_own(
    client: TestClient, ada: Headers, bob: Headers, adas: dict[str, str]
) -> None:
    assert client.get("/paychecks", headers=bob).json() == {"items": []}
    assert len(client.get("/paychecks", headers=ada).json()["items"]) == 5


def test_a_users_plan_is_built_from_their_own_data_only(
    client: TestClient, ada: Headers, bob: Headers, adas: dict[str, str], db_session: Session
) -> None:
    # Ada commits, so she has bills, a debt, a goal, reserves and a balance.
    assert client.post(f"/plans/{adas['plan']}/commit", headers=ada).status_code == 200
    client.post("/balance-snapshots", json={"amount_cents": 999_999}, headers=ada)
    job = client.post(
        "/income-sources",
        json={
            "name": "Bob's job",
            "expected_amount_cents": 100_000,
            "schedule": {"type": "biweekly", "anchor_date": PAYDAY},
        },
        headers=bob,
    ).json()

    plan = client.post(
        "/plans", json={"income_source_id": job["id"], "pay_date": PAYDAY}, headers=bob
    )

    assert plan.status_code == 201, plan.text
    body = plan.json()
    # None of Ada's bills, reserves, or balance: Bob keeps his whole paycheck.
    assert (body["allocations"], body["goal_projections"]) == ([], [])
    assert (body["available_balance_cents"], body["safe_to_spend_cents"]) == (0, 100_000)
    assert client.post(f"/plans/{body['id']}/commit", headers=bob).status_code == 200
    owners = db_session.scalars(select(Reserve.user_id).distinct()).all()
    assert len(owners) == 1  # only Ada has reserves
    statuses = db_session.scalars(select(PaycheckPlan.status)).all()
    assert statuses == [PlanStatus.COMMITTED, PlanStatus.COMMITTED]
