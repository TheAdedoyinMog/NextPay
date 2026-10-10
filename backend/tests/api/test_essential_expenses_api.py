"""/essential-expenses rules of its own. What every resource shares is in
test_resource_contract.py; cross-user access is in test_isolation.py."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EssentialExpense

type Json = dict[str, Any]
type Headers = dict[str, str]

GROCERIES: Json = {"name": "Groceries", "amount_per_period_cents": 20_000}


def create(client: TestClient, headers: Headers, **changes: Any) -> Json:
    response = client.post("/essential-expenses", json={**GROCERIES, **changes}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_an_essential_expense_has_exactly_these_fields(client: TestClient, ada: Headers) -> None:
    groceries = create(client, ada, name="  Groceries ")
    assert set(groceries) == {*GROCERIES, "id", "created_at", "updated_at"}
    assert groceries["name"] == "Groceries"


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "x" * 101}, "name"),
        ({"amount_per_period_cents": 0}, "amount_per_period_cents"),
        ({"amount_per_period_cents": -1}, "amount_per_period_cents"),
        ({"amount_per_period_cents": 200.5}, "amount_per_period_cents"),
        ({"amount_per_period_cents": "20000"}, "amount_per_period_cents"),
        ({"amount_per_period_cents": 100_000_000_001}, "amount_per_period_cents"),
    ],
)
def test_invalid_bodies_are_rejected_on_create_and_replace(
    client: TestClient, ada: Headers, db_session: Session, change: Json, field: str
) -> None:
    groceries = create(client, ada)
    path = f"/essential-expenses/{groceries['id']}"

    for response in (
        client.post("/essential-expenses", json={**GROCERIES, **change}, headers=ada),
        client.put(path, json={**GROCERIES, **change}, headers=ada),
    ):
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "validation_error"
        assert field in response.json()["error"]["message"]

    assert db_session.scalar(select(func.count()).select_from(EssentialExpense)) == 1
    assert client.get(path, headers=ada).json() == groceries


def test_list_is_ordered_by_name(client: TestClient, ada: Headers) -> None:
    gas = create(client, ada, name="Gas")
    transit = create(client, ada, name="Transit")
    groceries = create(client, ada)
    assert client.get("/essential-expenses", headers=ada).json() == {
        "items": [gas, groceries, transit]
    }
