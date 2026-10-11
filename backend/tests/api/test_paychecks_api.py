"""The paycheck timeline and recording actual pay, end to end against PostgreSQL.

The fake clock is at noon UTC on Wednesday, Oct 7, 2026. Cross-user access is in
test_planning_isolation.py.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Paycheck

type Json = dict[str, Any]
type Headers = dict[str, str]

JOB: Json = {
    "name": "Day job",
    "expected_amount_cents": 150_000,
    "schedule": {"type": "biweekly", "anchor_date": "2026-10-02"},
}
FIELDS = {
    "id",
    "income_source_id",
    "income_source_name",
    "income_source_archived",
    "pay_date",
    "expected_amount_cents",
    "actual_amount_cents",
    "amount_cents",
    "plan",
}


def add_source(client: TestClient, headers: Headers, **changes: Any) -> Json:
    response = client.post("/income-sources", json={**JOB, **changes}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def timeline(client: TestClient, headers: Headers, **params: str) -> list[Json]:
    response = client.get("/paychecks", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


def record(client: TestClient, headers: Headers, source: Json, day: str, cents: int | None) -> Any:
    return client.put(
        f"/income-sources/{source['id']}/paychecks/{day}",
        json={"actual_amount_cents": cents},
        headers=headers,
    )


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


# --- the timeline --------------------------------------------------------------


def test_a_user_with_no_income_has_no_paydays(client: TestClient, ada: Headers) -> None:
    assert client.get("/paychecks", headers=ada).json() == {"items": []}


def test_the_timeline_lists_expected_paydays(client: TestClient, ada: Headers) -> None:
    job = add_source(client, ada)

    items = timeline(client, ada)

    assert [item["pay_date"] for item in items] == [
        "2026-10-02",
        "2026-10-16",
        "2026-10-30",
        "2026-11-13",
        "2026-11-27",
    ]
    assert items[0] == {
        "id": None,
        "income_source_id": job["id"],
        "income_source_name": "Day job",
        "income_source_archived": False,
        "pay_date": "2026-10-02",
        "expected_amount_cents": 150_000,
        "actual_amount_cents": None,
        "amount_cents": 150_000,
        "plan": None,
    }


def test_two_jobs_share_one_timeline_within_a_range(client: TestClient, ada: Headers) -> None:
    add_source(client, ada)
    add_source(
        client,
        ada,
        name="Weekend job",
        expected_amount_cents=30_000,
        schedule={"type": "monthly", "day_of_month": 3},  # Saturday Oct 3 pays Friday Oct 2
    )

    items = timeline(client, ada, start="2026-10-01", end="2026-10-20")

    assert [item["pay_date"] for item in items] == ["2026-10-02", "2026-10-02", "2026-10-16"]
    assert sorted(item["income_source_name"] for item in items[:2]) == ["Day job", "Weekend job"]


@pytest.mark.parametrize(
    ("params", "code", "mention"),
    [
        ({"start": "2026-10-02", "end": "2026-10-01"}, "invalid_input", "366 days"),
        ({"start": "2026-01-01", "end": "2027-01-03"}, "invalid_input", "366 days"),
        ({"start": "October"}, "validation_error", "start"),
        ({"end": "2026-13-01"}, "validation_error", "end"),
    ],
)
def test_a_bad_range_is_rejected(
    client: TestClient, ada: Headers, params: dict[str, str], code: str, mention: str
) -> None:
    response = client.get("/paychecks", params=params, headers=ada)
    assert mention in assert_error(response, 422, code)["message"]


# --- recording what arrived ----------------------------------------------------


def test_recording_an_amount_creates_the_paycheck(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    job = add_source(client, ada)

    response = record(client, ada, job, "2026-10-02", 148_250)

    assert response.status_code == 200, response.text
    paycheck = response.json()
    assert set(paycheck) == FIELDS
    assert paycheck["actual_amount_cents"] == paycheck["amount_cents"] == 148_250
    assert paycheck["expected_amount_cents"] == 150_000
    stored = db_session.scalars(select(Paycheck)).one()
    assert str(stored.id) == paycheck["id"]
    assert stored.actual_amount_cents == 148_250
    # The timeline now shows it, and only that payday has a row.
    first, second, *_ = timeline(client, ada)
    assert first == paycheck
    assert second["id"] is None and second["amount_cents"] == 150_000


def test_recording_again_updates_and_null_clears(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    job = add_source(client, ada)
    first = record(client, ada, job, "2026-10-02", 148_250).json()

    zero = record(client, ada, job, "2026-10-02", 0).json()  # unpaid leave
    assert (zero["id"], zero["actual_amount_cents"], zero["amount_cents"]) == (first["id"], 0, 0)

    cleared = record(client, ada, job, "2026-10-02", None).json()
    assert (cleared["id"], cleared["actual_amount_cents"]) == (first["id"], None)
    assert cleared["amount_cents"] == 150_000
    assert db_session.scalar(select(func.count()).select_from(Paycheck)) == 1


@pytest.mark.parametrize("day", ["2026-10-03", "2026-10-09"])
def test_a_date_that_is_not_a_payday_is_rejected(
    client: TestClient, ada: Headers, db_session: Session, day: str
) -> None:
    job = add_source(client, ada)
    error = assert_error(record(client, ada, job, day, 148_250), 422, "invalid_input")
    assert "is not a payday for Day job" in error["message"]
    assert db_session.scalar(select(func.count()).select_from(Paycheck)) == 0


@pytest.mark.parametrize(
    ("body", "mention"),
    [
        ({"actual_amount_cents": -1}, "actual_amount_cents"),
        ({"actual_amount_cents": 1482.5}, "actual_amount_cents"),
        ({"actual_amount_cents": "148250"}, "actual_amount_cents"),
        ({"actual_amount_cents": 100_000_000_001}, "actual_amount_cents"),
        ({}, "actual_amount_cents"),
        ({"actual_amount_cents": 1, "expected_amount_cents": 2}, "expected_amount_cents"),
    ],
)
def test_invalid_bodies_are_rejected(
    client: TestClient, ada: Headers, db_session: Session, body: Json, mention: str
) -> None:
    job = add_source(client, ada)
    response = client.put(
        f"/income-sources/{job['id']}/paychecks/2026-10-02", json=body, headers=ada
    )
    assert mention in assert_error(response, 422, "validation_error")["message"]
    assert db_session.scalar(select(func.count()).select_from(Paycheck)) == 0


def test_a_malformed_date_or_source_id_is_a_validation_error(
    client: TestClient, ada: Headers
) -> None:
    job = add_source(client, ada)
    body = {"actual_amount_cents": 1}
    bad_date = client.put(f"/income-sources/{job['id']}/paychecks/oct-2", json=body, headers=ada)
    assert "pay_date" in assert_error(bad_date, 422, "validation_error")["message"]
    bad_id = client.put("/income-sources/nope/paychecks/2026-10-02", json=body, headers=ada)
    assert "income_source_id" in assert_error(bad_id, 422, "validation_error")["message"]


def test_an_unknown_source_is_not_found(client: TestClient, ada: Headers) -> None:
    response = client.put(
        f"/income-sources/{uuid.uuid4()}/paychecks/2026-10-02",
        json={"actual_amount_cents": 1},
        headers=ada,
    )
    assert_error(response, 404, "not_found")


def test_an_archived_sources_paychecks_stay_in_the_timeline_but_cannot_be_changed(
    client: TestClient, ada: Headers
) -> None:
    job = add_source(client, ada, name="Old job")
    recorded = record(client, ada, job, "2026-10-02", 148_250).json()
    assert client.delete(f"/income-sources/{job['id']}", headers=ada).status_code == 204

    # History remains, marked archived; the paydays it would have had are gone.
    assert timeline(client, ada) == [{**recorded, "income_source_archived": True}]
    assert_error(record(client, ada, job, "2026-10-02", 1), 404, "not_found")
    assert_error(record(client, ada, job, "2026-10-16", 1), 404, "not_found")


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_paycheck_routes_require_a_signed_in_user(
    client: TestClient, ada: Headers, method: str
) -> None:
    job = add_source(client, ada)
    if method == "GET":
        response = client.get("/paychecks")
    else:
        response = client.put(
            f"/income-sources/{job['id']}/paychecks/2026-10-02", json={"actual_amount_cents": 1}
        )
    assert_error(response, 401, "not_authenticated")
    assert timeline(client, ada)[0]["id"] is None
