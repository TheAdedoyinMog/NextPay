"""/balance-snapshots rules of its own: append-only, stamped by the server, newest
first. What every resource shares is in test_resource_contract.py; cross-user
access is in test_isolation.py."""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BalanceSnapshot

type Json = dict[str, Any]
type Headers = dict[str, str]
type Clock = Any  # conftest.FakeClock


def record(client: TestClient, headers: Headers, amount_cents: int) -> Json:
    response = client.post(
        "/balance-snapshots", json={"amount_cents": amount_cents}, headers=headers
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


def test_a_snapshot_is_stamped_with_the_servers_time(
    client: TestClient, ada: Headers, clock: Clock
) -> None:
    snapshot = record(client, ada, 123_456)
    assert set(snapshot) == {"id", "amount_cents", "as_of", "created_at"}
    assert snapshot["amount_cents"] == 123_456
    assert snapshot["as_of"] == "2026-10-07T12:00:00Z"


@pytest.mark.parametrize("amount_cents", [0, -25_000, 100_000_000_000, -100_000_000_000])
def test_zero_overdrawn_and_the_largest_balances_are_accepted(
    client: TestClient, ada: Headers, amount_cents: int
) -> None:
    assert record(client, ada, amount_cents)["amount_cents"] == amount_cents


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"amount_cents": 1234.5}, "amount_cents"),
        ({"amount_cents": "1234"}, "amount_cents"),
        ({"amount_cents": None}, "amount_cents"),
        ({"amount_cents": True}, "amount_cents"),
        ({"amount_cents": 100_000_000_001}, "amount_cents"),
        ({"amount_cents": -100_000_000_001}, "amount_cents"),
        # The server decides when; a client cannot backdate a balance.
        ({"amount_cents": 100, "as_of": "2020-01-01T00:00:00Z"}, "as_of"),
    ],
)
def test_invalid_bodies_are_rejected(
    client: TestClient, ada: Headers, db_session: Session, body: Json, field: str
) -> None:
    response = client.post("/balance-snapshots", json=body, headers=ada)
    assert field in assert_error(response, 422, "validation_error")["message"]
    assert db_session.scalar(select(func.count()).select_from(BalanceSnapshot)) == 0


def test_list_is_newest_first_so_the_first_is_the_current_balance(
    client: TestClient, ada: Headers, clock: Clock
) -> None:
    # Minutes apart, not days: the access token lasts 15 minutes.
    first = record(client, ada, 50_000)
    clock.advance(timedelta(minutes=2))
    second = record(client, ada, -2_000)
    clock.advance(timedelta(minutes=2))
    third = record(client, ada, 148_000)

    assert first["as_of"] < second["as_of"] < third["as_of"]
    assert client.get("/balance-snapshots", headers=ada).json() == {"items": [third, second, first]}


def test_limit_caps_the_list(client: TestClient, ada: Headers, clock: Clock) -> None:
    for cents in range(1, 61):
        record(client, ada, cents)
        clock.advance(timedelta(seconds=1))

    def amounts(**params: int) -> list[int]:
        response = client.get("/balance-snapshots", params=params, headers=ada)
        assert response.status_code == 200, response.text
        return [item["amount_cents"] for item in response.json()["items"]]

    assert amounts(limit=2) == [60, 59]
    assert amounts() == list(range(60, 10, -1))  # 50 by default
    assert amounts(limit=100) == list(range(60, 0, -1))


@pytest.mark.parametrize("limit", ["0", "-1", "101", "ten"])
def test_a_limit_out_of_range_is_a_validation_error(
    client: TestClient, ada: Headers, limit: str
) -> None:
    response = client.get("/balance-snapshots", params={"limit": limit}, headers=ada)
    assert "limit" in assert_error(response, 422, "validation_error")["message"]


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
def test_a_snapshot_cannot_be_read_alone_changed_or_deleted(
    client: TestClient, ada: Headers, db_session: Session, method: str
) -> None:
    snapshot = record(client, ada, 50_000)
    body = {"amount_cents": 1} if method in {"PUT", "PATCH"} else None

    # Append-only: there is no route for one snapshot, and none to change the collection.
    by_id = client.request(method, f"/balance-snapshots/{snapshot['id']}", json=body, headers=ada)
    assert_error(by_id, 404, "not_found")
    if method != "GET":
        whole = client.request(method, "/balance-snapshots", json=body, headers=ada)
        assert_error(whole, 405, "method_not_allowed")

    assert client.get("/balance-snapshots", headers=ada).json() == {"items": [snapshot]}
    assert db_session.scalars(select(BalanceSnapshot.id)).all() == [uuid.UUID(snapshot["id"])]
