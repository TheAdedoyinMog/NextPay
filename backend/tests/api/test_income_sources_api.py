"""/income-sources rules of its own: pay schedules, and deleting a source that
has paychecks. What every resource shares is in test_resource_contract.py;
cross-user access is in test_isolation.py."""

import uuid
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import IncomeSource, Paycheck

type Json = dict[str, Any]
type Headers = dict[str, str]

BIWEEKLY: Json = {"type": "biweekly", "anchor_date": "2026-10-02"}
JOB: Json = {"name": "Day job", "expected_amount_cents": 150_000, "schedule": BIWEEKLY}


def create(client: TestClient, headers: Headers, **changes: Any) -> Json:
    response = client.post("/income-sources", json={**JOB, **changes}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


def test_an_income_source_has_exactly_these_fields(client: TestClient, ada: Headers) -> None:
    assert set(create(client, ada)) == {*JOB, "id", "created_at", "updated_at"}


# --- schedules -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("schedule", "stored"),
    [
        ({"type": "weekly", "anchor_date": "2026-10-02"}, (date(2026, 10, 2), None, None)),
        (BIWEEKLY, (date(2026, 10, 2), None, None)),
        (
            {"type": "semi_monthly", "first_day_of_month": 15, "second_day_of_month": 31},
            (None, 15, 31),
        ),
        ({"type": "monthly", "day_of_month": 31}, (None, 31, None)),
    ],
)
def test_each_schedule_is_stored_and_returned_as_sent(
    client: TestClient, ada: Headers, db_session: Session, schedule: Json, stored: tuple[Any, ...]
) -> None:
    source = create(client, ada, schedule=schedule)

    assert source["schedule"] == schedule
    assert client.get(f"/income-sources/{source['id']}", headers=ada).json() == source
    row = db_session.scalars(select(IncomeSource)).one()
    assert row.pay_frequency.value == schedule["type"]
    assert (row.anchor_date, row.day_of_month, row.second_day_of_month) == stored


def test_replacing_the_schedule_clears_the_old_ones_parameters(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    source = create(client, ada)
    monthly = {"type": "monthly", "day_of_month": 1}

    response = client.put(
        f"/income-sources/{source['id']}", json={**JOB, "schedule": monthly}, headers=ada
    )

    assert response.status_code == 200, response.text
    assert response.json()["schedule"] == monthly
    row = db_session.scalars(select(IncomeSource)).one()
    assert (row.anchor_date, row.day_of_month, row.second_day_of_month) == (None, 1, None)


@pytest.mark.parametrize(
    "schedule",
    [
        None,
        "biweekly",
        {},
        {"anchor_date": "2026-10-02"},  # no type
        {"type": "fortnightly", "anchor_date": "2026-10-02"},
        {"type": "weekly"},
        {"type": "weekly", "anchor_date": "next Friday"},
        {"type": "weekly", "anchor_date": 1_792_000_000},
        # A frequency cannot carry another frequency's parameters.
        {"type": "weekly", "anchor_date": "2026-10-02", "day_of_month": 1},
        {"type": "biweekly", "day_of_month": 15},
        {"type": "monthly", "anchor_date": "2026-10-02"},
        {"type": "monthly", "day_of_month": 15, "second_day_of_month": 30},
        {"type": "monthly", "day_of_month": 0},
        {"type": "monthly", "day_of_month": 32},
        {"type": "monthly", "day_of_month": "15"},
        {"type": "semi_monthly", "first_day_of_month": 1},
        {"type": "semi_monthly", "first_day_of_month": 1, "second_day_of_month": 32},
        {"type": "semi_monthly", "day_of_month": 1, "second_day_of_month": 15},
    ],
)
def test_malformed_schedules_are_rejected_on_create_and_replace(
    client: TestClient, ada: Headers, db_session: Session, schedule: Any
) -> None:
    source = create(client, ada)
    body = {**JOB, "schedule": schedule}

    for response in (
        client.post("/income-sources", json=body, headers=ada),
        client.put(f"/income-sources/{source['id']}", json=body, headers=ada),
    ):
        assert "schedule" in assert_error(response, 422, "validation_error")["message"]

    assert db_session.scalar(select(func.count()).select_from(IncomeSource)) == 1
    assert client.get(f"/income-sources/{source['id']}", headers=ada).json() == source


@pytest.mark.parametrize(("first", "second"), [(1, 31), (15, 15), (20, 5), (10, 16), (25, 31)])
def test_semi_monthly_paydays_too_close_together_are_explained(
    client: TestClient, ada: Headers, db_session: Session, first: int, second: int
) -> None:
    source = create(client, ada)
    schedule = {"type": "semi_monthly", "first_day_of_month": first, "second_day_of_month": second}
    body = {**JOB, "schedule": schedule}

    for response in (
        client.post("/income-sources", json=body, headers=ada),
        client.put(f"/income-sources/{source['id']}", json=body, headers=ada),
    ):
        error = assert_error(response, 422, "invalid_input")
        assert "at least 7 days apart" in error["message"]

    assert db_session.scalar(select(func.count()).select_from(IncomeSource)) == 1
    assert client.get(f"/income-sources/{source['id']}", headers=ada).json() == source


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": ""}, "name"),
        ({"expected_amount_cents": 0}, "expected_amount_cents"),
        ({"expected_amount_cents": -1}, "expected_amount_cents"),
        ({"expected_amount_cents": 1500.0}, "expected_amount_cents"),
        ({"expected_amount_cents": 100_000_000_001}, "expected_amount_cents"),
    ],
)
def test_invalid_bodies_are_rejected(
    client: TestClient, ada: Headers, change: Json, field: str
) -> None:
    response = client.post("/income-sources", json={**JOB, **change}, headers=ada)
    assert field in assert_error(response, 422, "validation_error")["message"]


def test_list_is_ordered_by_name(client: TestClient, ada: Headers) -> None:
    weekend = create(client, ada, name="Weekend job")
    day = create(client, ada)
    assert client.get("/income-sources", headers=ada).json() == {"items": [day, weekend]}


# --- delete --------------------------------------------------------------------


def test_a_source_with_paychecks_cannot_be_deleted(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    source = create(client, ada)
    db_session.add(
        Paycheck(
            user_id=uuid.UUID(client.get("/me", headers=ada).json()["id"]),
            income_source_id=uuid.UUID(source["id"]),
            pay_date=date(2026, 10, 2),
            expected_amount_cents=150_000,
        )
    )
    db_session.commit()

    response = client.delete(f"/income-sources/{source['id']}", headers=ada)

    error = assert_error(response, 409, "income_source_in_use")
    assert "paychecks" in error["message"]
    # Nothing was lost, and the source can still be read and changed.
    assert db_session.scalar(select(func.count()).select_from(Paycheck)) == 1
    assert client.get(f"/income-sources/{source['id']}", headers=ada).json() == source
    renamed = client.put(
        f"/income-sources/{source['id']}", json={**JOB, "name": "Old job"}, headers=ada
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Old job"


def test_paychecks_on_one_source_do_not_block_deleting_another(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    paid = create(client, ada)
    unpaid = create(client, ada, name="Weekend job")
    db_session.add(
        Paycheck(
            user_id=uuid.UUID(client.get("/me", headers=ada).json()["id"]),
            income_source_id=uuid.UUID(paid["id"]),
            pay_date=date(2026, 10, 2),
            expected_amount_cents=150_000,
        )
    )
    db_session.commit()

    assert client.delete(f"/income-sources/{unpaid['id']}", headers=ada).status_code == 204
    assert client.get("/income-sources", headers=ada).json() == {"items": [paid]}
