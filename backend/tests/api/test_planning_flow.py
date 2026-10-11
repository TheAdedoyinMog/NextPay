"""The whole loop over three paychecks, through the API only (ADR 0003, ADR 0011).

Set up, plan, commit, pay, and plan again, with time moving forward and a fresh
balance entered before each plan, as the app will do it. Every number here can
be checked by hand from the design doc's worked example.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

type Json = dict[str, Any]
type Headers = dict[str, str]
type Clock = Any  # conftest.FakeClock


def sign_in(client: TestClient) -> Headers:
    """A fresh access token: they last 15 minutes and this test spans a month."""
    response = client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "correct horse battery"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def ok(response: Any, status: int = 200) -> Json:
    assert response.status_code == status, response.text
    return dict(response.json())


def funded(plan: Json) -> dict[str, int]:
    return {line["name"]: line["funded_cents"] for line in plan["allocations"]}


def set_aside(client: TestClient, headers: Headers, world: dict[str, Json]) -> dict[str, int]:
    """What the API says is reserved for the rent, the car loan and the camera."""
    paths = {"rent": "/bills", "car": "/debts", "camera": "/goals"}
    return {
        name: ok(client.get(f"{path}/{world[name]['id']}", headers=headers))["reserved_cents"]
        for name, path in paths.items()
    }


def test_three_paychecks_from_setup_to_paid_bills(
    client: TestClient, ada: Headers, worked_example: Any, clock: Clock
) -> None:
    # --- Friday Oct 2: payday. Ada sets everything up and enters her balance. ---
    clock.now = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    ada = sign_in(client)
    world = worked_example(ada)
    job, rent, car, camera = world["job"], world["rent"], world["car"], world["camera"]
    ok(client.post("/balance-snapshots", json={"amount_cents": 50_000}, headers=ada), 201)

    upcoming = ok(client.get("/paychecks", headers=ada))["items"]
    assert [p["pay_date"] for p in upcoming[:3]] == ["2026-10-02", "2026-10-16", "2026-10-30"]
    assert upcoming[0]["plan"] is None

    first = ok(
        client.post(
            "/plans", json={"income_source_id": job["id"], "pay_date": "2026-10-02"}, headers=ada
        ),
        201,
    )
    assert funded(first) == {
        "Rent": 40_000,
        "Groceries": 20_000,
        "Car loan": 7_500,
        "Camera": 6_667,
    }
    # $500 on hand + $1,500 paycheck - $741.67 planned.
    assert first["safe_to_spend_cents"] == 125_833
    assert first["as_of"] == "2026-10-02"

    assert set_aside(client, ada, world) == {"rent": 0, "car": 0, "camera": 0}
    committed = ok(client.post(f"/plans/{first['id']}/commit", headers=ada))
    assert committed["status"] == "committed"
    assert set_aside(client, ada, world) == {"rent": 40_000, "car": 7_500, "camera": 6_667}
    assert ok(client.get(f"/goals/{camera['id']}", headers=ada))["current_cents"] == 6_667

    # --- Friday Oct 16: the second paycheck arrives, $20 short. ---
    clock.now = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
    ada = sign_in(client)
    # She spent $200 on groceries and $300 freely: $500 + $1,500 - $500.
    ok(client.post("/balance-snapshots", json={"amount_cents": 150_000}, headers=ada), 201)
    ok(
        client.put(
            f"/income-sources/{job['id']}/paychecks/2026-10-16",
            json={"actual_amount_cents": 148_000},
            headers=ada,
        )
    )

    second = ok(
        client.post(
            "/plans", json={"income_source_id": job["id"], "pay_date": "2026-10-16"}, headers=ada
        ),
        201,
    )
    rent_line = second["allocations"][0]
    # The first paycheck's $400 is already set aside, so this one carries the rest.
    assert (rent_line["set_aside_cents"], rent_line["funded_cents"]) == (40_000, 40_000)
    assert rent_line["explanation"] == (
        "We reserved $400 toward Rent because the $800 bill is due Oct 20; with $400 already "
        "set aside, the rest is due before your next paycheck."
    )
    assert funded(second) == {
        "Rent": 40_000,
        "Groceries": 20_000,
        "Car loan": 7_500,
        "Camera": 6_667,
    }
    assert second["paycheck_amount_cents"] == 148_000
    # $1,500 on hand + $1,480 - $541.67 already reserved - $741.67 planned.
    assert second["safe_to_spend_cents"] == 150_000 + 148_000 - 54_167 - 74_167
    ok(client.post(f"/plans/{second['id']}/commit", headers=ada))
    assert set_aside(client, ada, world) == {"rent": 80_000, "car": 15_000, "camera": 13_334}

    # --- Monday Oct 19: rent and the car payment go out. ---
    clock.now = datetime(2026, 10, 19, 18, 0, tzinfo=UTC)
    ada = sign_in(client)
    rent_payment = ok(client.post(f"/bills/{rent['id']}/payments", json={}, headers=ada), 201)
    assert (rent_payment["amount_cents"], rent_payment["paid_on"], rent_payment["due_date"]) == (
        80_000,
        "2026-10-19",
        "2026-10-20",
    )
    assert set_aside(client, ada, world) == {"rent": 0, "car": 15_000, "camera": 13_334}
    car_payment = ok(client.post(f"/debts/{car['id']}/payments", json={}, headers=ada), 201)
    assert car_payment["amount_cents"] == 15_000
    assert set_aside(client, ada, world) == {"rent": 0, "car": 0, "camera": 13_334}
    assert ok(client.get(f"/debts/{car['id']}", headers=ada))["balance_cents"] == 885_000

    # --- Friday Oct 30: the third paycheck. Both reserves were drawn down to $0,
    # so November's rent and car payment start again from nothing. ---
    clock.now = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
    ada = sign_in(client)
    # $1,500 + $1,480 - $200 groceries - $800 rent - $150 car - $280 spent freely.
    ok(client.post("/balance-snapshots", json={"amount_cents": 155_000}, headers=ada), 201)

    third = ok(
        client.post(
            "/plans", json={"income_source_id": job["id"], "pay_date": "2026-10-30"}, headers=ada
        ),
        201,
    )
    rent_line, _, car_line, camera_line = third["allocations"]
    assert (rent_line["due_date"], rent_line["set_aside_cents"]) == ("2026-11-20", 0)
    assert (rent_line["paychecks"], rent_line["funded_cents"]) == (2, 40_000)
    assert (car_line["due_date"], car_line["set_aside_cents"], car_line["funded_cents"]) == (
        "2026-11-20",
        0,
        7_500,
    )
    # Two paychecks' worth of camera money is saved, and still set aside.
    assert (camera_line["set_aside_cents"], camera_line["paychecks"]) == (13_334, 28)
    assert camera_line["funded_cents"] == 6_667
    # $1,550 on hand + $1,500 - $133.34 reserved for the camera - $741.67 planned.
    assert third["safe_to_spend_cents"] == 155_000 + 150_000 - 13_334 - 74_167
    assert third["goal_projections"][0]["status"] == "on_track"

    # The timeline tells the whole story.
    history = ok(client.get("/paychecks", params={"start": "2026-10-01"}, headers=ada))["items"]
    assert [(p["pay_date"], p["plan"] and p["plan"]["status"]) for p in history[:4]] == [
        ("2026-10-02", "committed"),
        ("2026-10-16", "committed"),
        ("2026-10-30", "draft"),
        ("2026-11-13", None),
    ]
    assert history[1]["actual_amount_cents"] == 148_000
    assert ok(client.get(f"/bills/{rent['id']}/payments", headers=ada))["items"] == [rent_payment]
