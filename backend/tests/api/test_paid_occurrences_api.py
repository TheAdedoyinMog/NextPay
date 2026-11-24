"""A minimum paid early is not reserved again by the next plan (ADR 0018), end to end
against PostgreSQL.

This is the iPhone test, step by step and with the same numbers. The app plans only the
current paycheck (the newest payday on or before today), so the test moves an income
source's anchor to make two consecutive paydays current in turn. The fake clock is at
noon UTC on Sunday, Nov 22, 2026.

- $2,000 every two weeks, anchored Friday Nov 13: paydays Nov 13 and Nov 27, so the
  current one is Nov 13.
- A $3,000 car loan with a $150 minimum due on the 2nd.
- Anchored Nov 6 instead: paydays Nov 6, Nov 20 and Dec 4, so the current one is Nov 20.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

type Json = dict[str, Any]
type Headers = dict[str, str]

JOB: Json = {
    "name": "Job",
    "expected_amount_cents": 200_000,
    "schedule": {"type": "biweekly", "anchor_date": "2026-11-13"},
}
CAR_LOAN: Json = {
    "name": "Car loan",
    "balance_cents": 300_000,
    "apr_bps": 699,
    "minimum_payment_cents": 15_000,
    "due_day": 2,
}


def ok(response: Any, status: int = 200) -> Json:
    assert response.status_code == status, response.text
    return dict(response.json())


def plan(client: TestClient, headers: Headers, source: Json, pay_date: str) -> Json:
    response = client.post(
        "/plans", json={"income_source_id": source["id"], "pay_date": pay_date}, headers=headers
    )
    assert response.status_code in (200, 201), response.text
    return dict(response.json())


def car_line(body: Json) -> Json:
    (line,) = (a for a in body["allocations"] if a["tier"] == "debt_minimum")
    return dict(line)


def anchor(client: TestClient, headers: Headers, source: Json, day: str) -> None:
    body = {**JOB, "schedule": {"type": "biweekly", "anchor_date": day}}
    ok(client.put(f"/income-sources/{source['id']}", json=body, headers=headers))


def test_the_early_payment_is_skipped_by_the_next_plan_and_undo_brings_it_back(
    client: TestClient, sign_up: Callable[[str], Headers], clock: Any
) -> None:
    clock.now = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
    ada = sign_up("ada@example.com")  # after the clock moves, so its token is fresh
    job = ok(client.post("/income-sources", json=JOB, headers=ada), 201)
    loan = ok(client.post("/debts", json=CAR_LOAN, headers=ada), 201)
    ok(client.post("/balance-snapshots", json={"amount_cents": 50_000}, headers=ada), 201)

    # 1. Nov 13: $75 toward the Dec 2 minimum, over Nov 13 and Nov 27.
    assert ok(client.get("/dashboard", headers=ada))["current_paycheck"]["pay_date"] == (
        "2026-11-13"
    )
    first = plan(client, ada, job, "2026-11-13")
    assert (car_line(first)["funded_cents"], car_line(first)["due_date"]) == (7_500, "2026-12-02")
    assert first["safe_to_spend_cents"] == 242_500
    ok(client.post(f"/plans/{first['id']}/commit", headers=ada))

    # 2. Mark paid on that line, today: the Dec 2 minimum, paid early.
    payment = ok(
        client.post(f"/debts/{loan['id']}/payments", json={"due_date": "2026-12-02"}, headers=ada),
        201,
    )
    assert (payment["amount_cents"], payment["paid_on"]) == (15_000, "2026-11-22")
    safe = ok(client.get("/dashboard", headers=ada))["safe_to_spend"]
    assert (safe["safe_to_spend_cents"], safe["paid_beyond_reserves_cents"]) == (235_000, 7_500)

    # 3. Move the anchor so Nov 20 is current, and plan it: Dec 2 is skipped.
    anchor(client, ada, job, "2026-11-06")
    assert ok(client.get("/dashboard", headers=ada))["current_paycheck"]["pay_date"] == (
        "2026-11-20"
    )
    second = plan(client, ada, job, "2026-11-20")
    car = car_line(second)
    assert (car["funded_cents"], car["due_date"], car["paychecks"]) == (3_750, "2027-01-02", 4)
    assert car["explanation"] == (
        "We reserved $37.50 toward Car loan because the $150 minimum payment is due "
        "Jan 2, 2027 and is split across the 4 paychecks before then. "
        "The Dec 2 minimum payment was already paid on Nov 22."
    )
    assert second["safe_to_spend_cents"] == 246_250

    # 4. Back to Nov 13, undo the payment, then to Nov 20 again: its draft is out of date,
    # and planning again reserves for Dec 2 as if it had never been paid.
    anchor(client, ada, job, "2026-11-13")
    ok(client.post(f"/debts/{loan['id']}/payments/{payment['id']}/undo", headers=ada))
    assert ok(client.get("/dashboard", headers=ada))["safe_to_spend"]["safe_to_spend_cents"] == (
        242_500
    )
    anchor(client, ada, job, "2026-11-06")
    assert ok(client.get(f"/plans/{second['id']}", headers=ada))["is_out_of_date"]
    third = plan(client, ada, job, "2026-11-20")
    car = car_line(third)
    assert (car["funded_cents"], car["due_date"]) == (7_500, "2026-12-02")
    assert car["explanation"] == (
        "We reserved $75 toward Car loan because the $150 minimum payment is due Dec 2; "
        "with $75 already set aside, the rest is due before your next paycheck."
    )
    assert third["safe_to_spend_cents"] == 235_000
