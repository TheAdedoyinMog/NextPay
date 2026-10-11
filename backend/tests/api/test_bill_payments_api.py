"""POST and GET /bills/{id}/payments, end to end against PostgreSQL.

The fake clock is at noon UTC on Wednesday, Oct 7, 2026. Cross-user access is in
test_planning_isolation.py.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BillPayment, Reserve
from nextpay_engine import ReserveKind

type Json = dict[str, Any]
type Headers = dict[str, str]

RENT: Json = {
    "name": "Rent",
    "amount_cents": 80_000,
    "priority": 1,
    "first_due_date": "2026-10-20",
    "repeat_every_months": 1,
}


def add_bill(client: TestClient, headers: Headers, **changes: Any) -> Json:
    response = client.post("/bills", json={**RENT, **changes}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def set_aside(
    session: Session, client: TestClient, headers: Headers, bill: Json, cents: int
) -> None:
    session.add(
        Reserve(
            user_id=uuid.UUID(client.get("/me", headers=headers).json()["id"]),
            kind=ReserveKind.BILL,
            bill_id=uuid.UUID(bill["id"]),
            amount_cents=cents,
        )
    )
    session.commit()


def reserved(session: Session, bill: Json) -> int | None:
    session.expire_all()
    return session.scalar(
        select(Reserve.amount_cents).where(Reserve.bill_id == uuid.UUID(bill["id"]))
    )


def pay(client: TestClient, headers: Headers, bill: Json, **body: Any) -> Any:
    return client.post(f"/bills/{bill['id']}/payments", json=body, headers=headers)


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


def test_marking_a_bill_paid_takes_an_empty_body(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    rent = add_bill(client, ada)
    set_aside(db_session, client, ada, rent, 80_000)

    response = pay(client, ada, rent)

    assert response.status_code == 201, response.text
    payment = response.json()
    assert set(payment) == {"id", "bill_id", "due_date", "paid_on", "amount_cents", "created_at"}
    assert payment["bill_id"] == rent["id"]
    assert (payment["amount_cents"], payment["paid_on"], payment["due_date"]) == (
        80_000,
        "2026-10-07",
        "2026-10-20",
    )
    assert reserved(db_session, rent) == 0
    assert client.get(f"/bills/{rent['id']}/payments", headers=ada).json() == {"items": [payment]}
    # The bill itself is unchanged.
    assert client.get(f"/bills/{rent['id']}", headers=ada).json() == rent


def test_nulls_mean_the_same_as_leaving_a_field_out(client: TestClient, ada: Headers) -> None:
    rent = add_bill(client, ada)
    payment = pay(client, ada, rent, amount_cents=None, paid_on=None, due_date=None).json()
    assert (payment["amount_cents"], payment["paid_on"]) == (80_000, "2026-10-07")


@pytest.mark.parametrize(
    ("was_reserved", "paid", "left"),
    [(80_000, 30_000, 50_000), (40_000, 80_000, 0), (80_000, 100_000, 0)],
)
def test_the_reserve_goes_down_by_what_was_paid_but_not_below_zero(
    client: TestClient, ada: Headers, db_session: Session, was_reserved: int, paid: int, left: int
) -> None:
    rent, phone = add_bill(client, ada), add_bill(client, ada, name="Phone", amount_cents=6_000)
    set_aside(db_session, client, ada, rent, was_reserved)
    set_aside(db_session, client, ada, phone, 6_000)

    assert pay(client, ada, rent, amount_cents=paid).status_code == 201

    assert reserved(db_session, rent) == left
    assert reserved(db_session, phone) == 6_000


def test_paying_a_bill_with_nothing_set_aside_creates_no_reserve(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    rent = add_bill(client, ada)
    assert pay(client, ada, rent).status_code == 201
    assert reserved(db_session, rent) is None


@pytest.mark.parametrize(
    ("body", "due"),
    [
        ({"paid_on": "2026-10-15"}, "2026-10-20"),  # early
        ({"paid_on": "2026-10-24"}, "2026-10-20"),  # late
        ({"paid_on": "2026-11-19"}, "2026-11-20"),
        ({"paid_on": "2026-12-02", "due_date": "2026-10-20"}, "2026-10-20"),  # catching up
    ],
)
def test_a_payment_is_matched_to_a_due_date(
    client: TestClient, ada: Headers, body: Json, due: str
) -> None:
    rent = add_bill(client, ada)
    payment = pay(client, ada, rent, **body).json()
    assert (payment["paid_on"], payment["due_date"]) == (body["paid_on"], due)


def test_a_named_due_date_must_be_one_of_the_bills(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    rent = add_bill(client, ada)
    set_aside(db_session, client, ada, rent, 80_000)

    error = assert_error(pay(client, ada, rent, due_date="2026-10-21"), 422, "invalid_input")

    assert "2026-10-21 is not a due date of Rent" in error["message"]
    assert reserved(db_session, rent) == 80_000
    assert db_session.scalar(select(func.count()).select_from(BillPayment)) == 0


@pytest.mark.parametrize(
    ("body", "mention"),
    [
        ({"amount_cents": 0}, "amount_cents"),
        ({"amount_cents": -100}, "amount_cents"),
        ({"amount_cents": 800.5}, "amount_cents"),
        ({"amount_cents": "80000"}, "amount_cents"),
        ({"amount_cents": 100_000_000_001}, "amount_cents"),
        ({"paid_on": "yesterday"}, "paid_on"),
        ({"paid_on": 1_791_000_000}, "paid_on"),
        ({"due_date": "2026-02-30"}, "due_date"),
        ({"bill_id": str(uuid.uuid4())}, "bill_id"),
    ],
)
def test_invalid_bodies_are_rejected(
    client: TestClient, ada: Headers, db_session: Session, body: Json, mention: str
) -> None:
    rent = add_bill(client, ada)
    error = assert_error(pay(client, ada, rent, **body), 422, "validation_error")
    assert mention in error["message"]
    assert db_session.scalar(select(func.count()).select_from(BillPayment)) == 0


def test_a_body_is_required_even_when_empty(client: TestClient, ada: Headers) -> None:
    rent = add_bill(client, ada)
    response = client.post(f"/bills/{rent['id']}/payments", headers=ada)
    assert_error(response, 422, "validation_error")


def test_payments_are_listed_newest_first_per_bill(client: TestClient, ada: Headers) -> None:
    rent, phone = add_bill(client, ada), add_bill(client, ada, name="Phone", amount_cents=6_000)
    assert client.get(f"/bills/{rent['id']}/payments", headers=ada).json() == {"items": []}
    october = pay(client, ada, rent, paid_on="2026-10-19").json()
    pay(client, ada, phone, paid_on="2026-10-25")
    november = pay(client, ada, rent, paid_on="2026-11-20").json()

    listed = client.get(f"/bills/{rent['id']}/payments", headers=ada).json()

    assert listed == {"items": [november, october]}


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_an_unknown_bill_is_not_found_and_a_malformed_id_is_invalid(
    client: TestClient, ada: Headers, method: str
) -> None:
    body = {} if method == "POST" else None
    missing = client.request(method, f"/bills/{uuid.uuid4()}/payments", json=body, headers=ada)
    assert_error(missing, 404, "not_found")
    malformed = client.request(method, "/bills/rent/payments", json=body, headers=ada)
    assert "bill_id" in assert_error(malformed, 422, "validation_error")["message"]


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_payment_routes_require_a_signed_in_user(
    client: TestClient, ada: Headers, db_session: Session, method: str
) -> None:
    rent = add_bill(client, ada)
    body = {} if method == "POST" else None
    response = client.request(method, f"/bills/{rent['id']}/payments", json=body)
    assert_error(response, 401, "not_authenticated")
    assert db_session.scalar(select(func.count()).select_from(BillPayment)) == 0
