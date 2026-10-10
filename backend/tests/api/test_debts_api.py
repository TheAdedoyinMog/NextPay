"""/debts rules of its own. What every resource shares is in
test_resource_contract.py; cross-user access is in test_isolation.py."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Debt, Reserve
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


def create(client: TestClient, headers: Headers, **changes: Any) -> Json:
    response = client.post("/debts", json={**CAR_LOAN, **changes}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_a_debt_has_exactly_these_fields(client: TestClient, ada: Headers) -> None:
    assert set(create(client, ada)) == {*CAR_LOAN, "id", "created_at", "updated_at"}


def test_the_smallest_and_largest_values_are_accepted(client: TestClient, ada: Headers) -> None:
    create(client, ada, balance_cents=0, apr_bps=0, minimum_payment_cents=0, due_day=1)
    create(client, ada, balance_cents=100_000_000_000, apr_bps=100_000, due_day=31)


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": "  "}, "name"),
        ({"balance_cents": -1}, "balance_cents"),
        ({"balance_cents": 9000.5}, "balance_cents"),
        ({"balance_cents": 100_000_000_001}, "balance_cents"),
        ({"apr_bps": -1}, "apr_bps"),
        ({"apr_bps": 24.99}, "apr_bps"),
        ({"apr_bps": 100_001}, "apr_bps"),
        ({"minimum_payment_cents": -1}, "minimum_payment_cents"),
        ({"minimum_payment_cents": None}, "minimum_payment_cents"),
        ({"due_day": 0}, "due_day"),
        ({"due_day": 32}, "due_day"),
        ({"due_day": "20"}, "due_day"),
    ],
)
def test_invalid_bodies_are_rejected_on_create_and_replace(
    client: TestClient, ada: Headers, db_session: Session, change: Json, field: str
) -> None:
    loan = create(client, ada)

    for response in (
        client.post("/debts", json={**CAR_LOAN, **change}, headers=ada),
        client.put(f"/debts/{loan['id']}", json={**CAR_LOAN, **change}, headers=ada),
    ):
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "validation_error"
        assert field in response.json()["error"]["message"]

    assert db_session.scalar(select(func.count()).select_from(Debt)) == 1
    assert client.get(f"/debts/{loan['id']}", headers=ada).json() == loan


def test_list_is_ordered_by_name(client: TestClient, ada: Headers) -> None:
    visa = create(client, ada, name="Visa")
    loan = create(client, ada)
    assert client.get("/debts", headers=ada).json() == {"items": [loan, visa]}


def test_delete_releases_the_debts_reserve(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    loan = create(client, ada)
    kept = create(client, ada, name="Visa")
    user_id = uuid.UUID(client.get("/me", headers=ada).json()["id"])
    for debt in (loan, kept):
        db_session.add(
            Reserve(
                user_id=user_id,
                kind=ReserveKind.DEBT,
                debt_id=uuid.UUID(debt["id"]),
                amount_cents=7_500,
            )
        )
    db_session.commit()

    assert client.delete(f"/debts/{loan['id']}", headers=ada).status_code == 204

    assert db_session.scalars(select(Reserve.debt_id)).all() == [uuid.UUID(kept["id"])]
