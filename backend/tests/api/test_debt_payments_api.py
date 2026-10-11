"""POST and GET /debts/{id}/payments, and a goal's reserve following its progress
down, end to end against PostgreSQL.

The fake clock is at noon UTC on Wednesday, Oct 7, 2026. Cross-user access is in
test_planning_isolation.py.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DebtPayment, Reserve
from nextpay_engine import ReserveKind

type Json = dict[str, Any]
type Headers = dict[str, str]

CAR_LOAN: Json = {
    "name": "Car loan",
    "balance_cents": 900_000,
    "apr_bps": 699,
    "minimum_payment_cents": 15_000,
    "due_day": 20,
}
CAMERA: Json = {
    "name": "Camera",
    "kind": "purchase",
    "target_cents": 200_000,
    "current_cents": 40_000,
    "priority": 2,
    "deadline": None,
}


def add(client: TestClient, headers: Headers, path: str, body: Json, **changes: Any) -> Json:
    response = client.post(path, json={**body, **changes}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def set_aside(
    session: Session, client: TestClient, headers: Headers, kind: ReserveKind, row: Json, cents: int
) -> None:
    column = "debt_id" if kind is ReserveKind.DEBT else "goal_id"
    session.add(
        Reserve(
            user_id=uuid.UUID(client.get("/me", headers=headers).json()["id"]),
            kind=kind,
            amount_cents=cents,
            **{column: uuid.UUID(row["id"])},
        )
    )
    session.commit()


def reserved(session: Session, row: Json) -> int | None:
    session.expire_all()
    target = uuid.UUID(row["id"])
    return session.scalar(
        select(Reserve.amount_cents).where(
            (Reserve.debt_id == target) | (Reserve.goal_id == target)
        )
    )


def pay(client: TestClient, headers: Headers, debt: Json, **body: Any) -> Any:
    return client.post(f"/debts/{debt['id']}/payments", json=body, headers=headers)


def balance(client: TestClient, headers: Headers, debt: Json) -> int:
    return int(client.get(f"/debts/{debt['id']}", headers=headers).json()["balance_cents"])


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


# --- debt payments -------------------------------------------------------------


def test_recording_the_minimum_takes_an_empty_body(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    loan = add(client, ada, "/debts", CAR_LOAN)
    set_aside(db_session, client, ada, ReserveKind.DEBT, loan, 15_000)

    response = pay(client, ada, loan)

    assert response.status_code == 201, response.text
    payment = response.json()
    assert set(payment) == {"id", "debt_id", "paid_on", "amount_cents", "created_at"}
    assert (payment["debt_id"], payment["amount_cents"]) == (loan["id"], 15_000)
    assert payment["paid_on"] == "2026-10-07"
    assert balance(client, ada, loan) == 885_000
    assert reserved(db_session, loan) == 0
    assert client.get(f"/debts/{loan['id']}/payments", headers=ada).json() == {"items": [payment]}


@pytest.mark.parametrize(
    ("was_reserved", "paid", "balance_left", "reserve_left"),
    [
        (15_000, 50_000, 850_000, 0),
        (15_000, 10_000, 890_000, 5_000),
        (15_000, 950_000, 0, 0),
    ],
)
def test_the_balance_and_the_reserve_go_down_but_not_below_zero(
    client: TestClient,
    ada: Headers,
    db_session: Session,
    was_reserved: int,
    paid: int,
    balance_left: int,
    reserve_left: int,
) -> None:
    loan = add(client, ada, "/debts", CAR_LOAN)
    card = add(client, ada, "/debts", CAR_LOAN, name="Visa")
    set_aside(db_session, client, ada, ReserveKind.DEBT, loan, was_reserved)
    set_aside(db_session, client, ada, ReserveKind.DEBT, card, 3_500)

    assert pay(client, ada, loan, amount_cents=paid, paid_on="2026-09-19").status_code == 201

    assert (balance(client, ada, loan), reserved(db_session, loan)) == (balance_left, reserve_left)
    assert (balance(client, ada, card), reserved(db_session, card)) == (900_000, 3_500)


def test_with_nothing_owed_the_amount_must_be_given(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    paid_off = add(client, ada, "/debts", CAR_LOAN, balance_cents=0)
    error = assert_error(pay(client, ada, paid_off), 422, "invalid_input")
    assert "more than $0" in error["message"]
    assert db_session.scalar(select(func.count()).select_from(DebtPayment)) == 0


@pytest.mark.parametrize(
    ("body", "mention"),
    [
        ({"amount_cents": 0}, "amount_cents"),
        ({"amount_cents": 150.5}, "amount_cents"),
        ({"amount_cents": 100_000_000_001}, "amount_cents"),
        ({"paid_on": "last week"}, "paid_on"),
        ({"due_date": "2026-10-20"}, "due_date"),  # a debt payment has no occurrence
    ],
)
def test_invalid_bodies_are_rejected(
    client: TestClient, ada: Headers, db_session: Session, body: Json, mention: str
) -> None:
    loan = add(client, ada, "/debts", CAR_LOAN)
    error = assert_error(pay(client, ada, loan, **body), 422, "validation_error")
    assert mention in error["message"]
    assert balance(client, ada, loan) == 900_000
    assert db_session.scalar(select(func.count()).select_from(DebtPayment)) == 0


def test_payments_are_listed_newest_first_per_debt(client: TestClient, ada: Headers) -> None:
    loan = add(client, ada, "/debts", CAR_LOAN)
    card = add(client, ada, "/debts", CAR_LOAN, name="Visa")
    september = pay(client, ada, loan, paid_on="2026-09-20").json()
    pay(client, ada, card, paid_on="2026-10-01")
    october = pay(client, ada, loan, paid_on="2026-10-20").json()

    listed = client.get(f"/debts/{loan['id']}/payments", headers=ada).json()

    assert listed == {"items": [october, september]}
    assert balance(client, ada, loan) == 870_000


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_an_unknown_debt_is_not_found_and_a_malformed_id_is_invalid(
    client: TestClient, ada: Headers, method: str
) -> None:
    body = {} if method == "POST" else None
    missing = client.request(method, f"/debts/{uuid.uuid4()}/payments", json=body, headers=ada)
    assert_error(missing, 404, "not_found")
    malformed = client.request(method, "/debts/car/payments", json=body, headers=ada)
    assert "debt_id" in assert_error(malformed, 422, "validation_error")["message"]


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_payment_routes_require_a_signed_in_user(
    client: TestClient, ada: Headers, method: str
) -> None:
    loan = add(client, ada, "/debts", CAR_LOAN)
    body = {} if method == "POST" else None
    response = client.request(method, f"/debts/{loan['id']}/payments", json=body)
    assert_error(response, 401, "not_authenticated")
    assert balance(client, ada, loan) == 900_000


# --- a goal's reserve follows its progress down --------------------------------


@pytest.mark.parametrize(
    ("saved", "reserve_left"), [(10_000, 10_000), (0, 0), (40_000, 40_000), (90_000, 40_000)]
)
def test_lowering_a_goals_progress_lowers_its_reserve_to_match(
    client: TestClient, ada: Headers, db_session: Session, saved: int, reserve_left: int
) -> None:
    camera = add(client, ada, "/goals", CAMERA)
    trip = add(client, ada, "/goals", CAMERA, name="Trip", kind="savings")
    set_aside(db_session, client, ada, ReserveKind.GOAL, camera, 40_000)
    set_aside(db_session, client, ada, ReserveKind.GOAL, trip, 40_000)

    response = client.put(
        f"/goals/{camera['id']}", json={**CAMERA, "current_cents": saved}, headers=ada
    )

    assert response.status_code == 200, response.text
    assert response.json()["current_cents"] == saved
    assert reserved(db_session, camera) == reserve_left
    assert reserved(db_session, trip) == 40_000


def test_changing_a_goal_with_nothing_set_aside_creates_no_reserve(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    camera = add(client, ada, "/goals", CAMERA)
    client.put(f"/goals/{camera['id']}", json={**CAMERA, "current_cents": 90_000}, headers=ada)
    assert reserved(db_session, camera) is None
