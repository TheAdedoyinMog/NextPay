"""/bills end to end against PostgreSQL. Cross-user access is in test_isolation.py."""

import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Bill, BillPayment, Reserve
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
FIELDS = {*RENT, "id", "created_at", "updated_at"}


@pytest.fixture
def ada(sign_up: Callable[[str], Headers]) -> Headers:
    return sign_up("ada@example.com")


def create(client: TestClient, headers: Headers, **changes: Any) -> Json:
    response = client.post("/bills", json={**RENT, **changes}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


# --- create --------------------------------------------------------------------


def test_create_returns_the_bill_and_stores_it_for_the_user(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    bill = create(client, ada)

    assert set(bill) == FIELDS
    assert {name: bill[name] for name in RENT} == RENT

    stored = db_session.scalars(select(Bill)).one()
    assert str(stored.id) == bill["id"]
    assert str(stored.user_id) == client.get("/me", headers=ada).json()["id"]
    assert (stored.amount_cents, stored.first_due_date) == (80_000, date(2026, 10, 20))


def test_create_trims_the_name(client: TestClient, ada: Headers) -> None:
    assert create(client, ada, name="  Rent  ")["name"] == "Rent"


def test_a_one_time_bill_has_a_null_repeat(client: TestClient, ada: Headers) -> None:
    assert create(client, ada, repeat_every_months=None)["repeat_every_months"] is None


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "x" * 101}, "name"),
        ({"name": "Re\u0000nt"}, "name"),
        ({"name": 5}, "name"),
        ({"amount_cents": 0}, "amount_cents"),
        ({"amount_cents": -100}, "amount_cents"),
        ({"amount_cents": 800.0}, "amount_cents"),
        ({"amount_cents": 800.5}, "amount_cents"),
        ({"amount_cents": "80000"}, "amount_cents"),
        ({"amount_cents": True}, "amount_cents"),
        ({"amount_cents": None}, "amount_cents"),
        ({"amount_cents": 100_000_000_001}, "amount_cents"),
        ({"amount_cents": 10**30}, "amount_cents"),
        ({"priority": 0}, "priority"),
        ({"priority": 1001}, "priority"),
        ({"priority": "1"}, "priority"),
        ({"first_due_date": "20 Oct 2026"}, "first_due_date"),
        ({"first_due_date": "2026-02-30"}, "first_due_date"),
        ({"first_due_date": 1_792_000_000}, "first_due_date"),
        ({"first_due_date": None}, "first_due_date"),
        ({"repeat_every_months": 0}, "repeat_every_months"),
        ({"repeat_every_months": 121}, "repeat_every_months"),
        ({"repeat_every_months": 1.5}, "repeat_every_months"),
        ({"paid": True}, "paid"),
        ({"id": str(uuid.uuid4())}, "id"),
    ],
)
def test_create_rejects_invalid_bodies(
    client: TestClient, ada: Headers, db_session: Session, change: Json, field: str
) -> None:
    response = client.post("/bills", json={**RENT, **change}, headers=ada)
    error = assert_error(response, 422, "validation_error")
    assert field in error["message"]
    assert db_session.scalar(select(func.count()).select_from(Bill)) == 0


@pytest.mark.parametrize("field", sorted(RENT))
def test_create_requires_every_field(client: TestClient, ada: Headers, field: str) -> None:
    body = {name: value for name, value in RENT.items() if name != field}
    error = assert_error(client.post("/bills", json=body, headers=ada), 422, "validation_error")
    assert field in error["message"]


def test_the_largest_allowed_values_are_accepted(client: TestClient, ada: Headers) -> None:
    bill = create(
        client,
        ada,
        name="x" * 100,
        amount_cents=100_000_000_000,
        priority=1000,
        repeat_every_months=120,
    )
    assert bill["amount_cents"] == 100_000_000_000


# --- list and get --------------------------------------------------------------


def test_list_is_empty_for_a_new_user(client: TestClient, ada: Headers) -> None:
    response = client.get("/bills", headers=ada)
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_list_orders_by_priority_then_due_date(client: TestClient, ada: Headers) -> None:
    phone = create(client, ada, name="Phone", priority=2, first_due_date="2026-10-05")
    water = create(client, ada, name="Water", priority=1, first_due_date="2026-10-25")
    rent = create(client, ada, name="Rent", priority=1, first_due_date="2026-10-20")

    assert client.get("/bills", headers=ada).json() == {"items": [rent, water, phone]}


def test_get_returns_the_bill(client: TestClient, ada: Headers) -> None:
    bill = create(client, ada)
    response = client.get(f"/bills/{bill['id']}", headers=ada)
    assert response.status_code == 200
    assert response.json() == bill


# --- replace -------------------------------------------------------------------


def test_put_replaces_every_field(client: TestClient, ada: Headers) -> None:
    bill = create(client, ada)
    new = {
        "name": "Car insurance",
        "amount_cents": 45_000,
        "priority": 2,
        "first_due_date": "2027-01-15",
        "repeat_every_months": None,
    }

    response = client.put(f"/bills/{bill['id']}", json=new, headers=ada)

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated == {**bill, **new, "updated_at": updated["updated_at"]}
    assert client.get(f"/bills/{bill['id']}", headers=ada).json() == updated


def test_put_needs_the_whole_bill(client: TestClient, ada: Headers) -> None:
    bill = create(client, ada)
    response = client.put(f"/bills/{bill['id']}", json={"amount_cents": 90_000}, headers=ada)
    assert_error(response, 422, "validation_error")
    assert client.get(f"/bills/{bill['id']}", headers=ada).json() == bill


def test_a_rejected_put_leaves_the_bill_unchanged(client: TestClient, ada: Headers) -> None:
    bill = create(client, ada)
    response = client.put(
        f"/bills/{bill['id']}", json={**RENT, "name": "Changed", "amount_cents": 0}, headers=ada
    )
    assert_error(response, 422, "validation_error")
    assert client.get(f"/bills/{bill['id']}", headers=ada).json() == bill


# --- delete --------------------------------------------------------------------


def test_delete_removes_the_bill(client: TestClient, ada: Headers) -> None:
    bill = create(client, ada)
    other = create(client, ada, name="Phone")

    response = client.delete(f"/bills/{bill['id']}", headers=ada)

    assert response.status_code == 204
    assert response.content == b""
    assert_error(client.get(f"/bills/{bill['id']}", headers=ada), 404, "not_found")
    assert client.get("/bills", headers=ada).json() == {"items": [other]}


def test_delete_takes_the_bills_payments_and_releases_its_reserve(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    bill = create(client, ada)
    kept = create(client, ada, name="Phone")
    user_id = uuid.UUID(client.get("/me", headers=ada).json()["id"])
    for target in (bill, kept):
        bill_id = uuid.UUID(target["id"])
        db_session.add(
            BillPayment(
                user_id=user_id,
                bill_id=bill_id,
                due_date=date(2026, 10, 20),
                paid_on=date(2026, 10, 19),
                amount_cents=80_000,
            )
        )
        db_session.add(
            Reserve(user_id=user_id, kind=ReserveKind.BILL, bill_id=bill_id, amount_cents=40_000)
        )
    db_session.commit()

    assert client.delete(f"/bills/{bill['id']}", headers=ada).status_code == 204

    # Only the other bill's payment and reserve are left.
    assert db_session.scalars(select(BillPayment.bill_id)).all() == [uuid.UUID(kept["id"])]
    assert db_session.scalars(select(Reserve.bill_id)).all() == [uuid.UUID(kept["id"])]


# --- not found, and not signed in ----------------------------------------------


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_an_unknown_bill_is_not_found(client: TestClient, ada: Headers, method: str) -> None:
    create(client, ada)
    body = RENT if method == "PUT" else None
    response = client.request(method, f"/bills/{uuid.uuid4()}", json=body, headers=ada)
    assert assert_error(response, 404, "not_found") == {
        "code": "not_found",
        "message": "Not found.",
    }


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_a_malformed_id_is_a_validation_error(
    client: TestClient, ada: Headers, method: str
) -> None:
    body = RENT if method == "PUT" else None
    response = client.request(method, "/bills/not-a-uuid", json=body, headers=ada)
    assert "bill_id" in assert_error(response, 422, "validation_error")["message"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/bills"),
        ("GET", "/bills"),
        ("GET", "/bills/{id}"),
        ("PUT", "/bills/{id}"),
        ("DELETE", "/bills/{id}"),
    ],
)
def test_every_route_requires_a_signed_in_user(
    client: TestClient, ada: Headers, db_session: Session, method: str, path: str
) -> None:
    bill = create(client, ada)
    body = RENT if method in {"POST", "PUT"} else None

    response = client.request(method, path.format(id=bill["id"]), json=body)

    assert_error(response, 401, "not_authenticated")
    assert response.headers["www-authenticate"] == "Bearer"
    assert db_session.scalar(select(func.count()).select_from(Bill)) == 1
    assert client.get(f"/bills/{bill['id']}", headers=ada).json() == bill


def test_sign_in_is_checked_before_the_body(client: TestClient) -> None:
    # An invalid body from a stranger says nothing about what a valid one looks like.
    assert_error(client.post("/bills", json={"nonsense": True}), 401, "not_authenticated")
