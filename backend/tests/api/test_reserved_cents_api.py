"""`reserved_cents` on bills, debts and goals: what is set aside, as the API shows it.

The setup is the design doc's worked example (the ``worked_example`` fixture).
Everything here is read through the API, never from the reserves table.
"""

from typing import Any

from fastapi.testclient import TestClient

type Json = dict[str, Any]
type Headers = dict[str, str]

PAYDAY = "2026-10-02"
ROUTES = {"rent": "/bills", "car": "/debts", "camera": "/goals"}


def commit_first_paycheck(client: TestClient, headers: Headers, world: dict[str, Json]) -> None:
    plan = client.post(
        "/plans", json={"income_source_id": world["job"]["id"], "pay_date": PAYDAY}, headers=headers
    )
    assert plan.status_code == 201, plan.text
    assert client.post(f"/plans/{plan.json()['id']}/commit", headers=headers).status_code == 200


def reserved(client: TestClient, headers: Headers, world: dict[str, Json]) -> dict[str, int]:
    """Rent's, the car loan's and the camera's reserved_cents, read one by one."""
    return {
        name: client.get(f"{path}/{world[name]['id']}", headers=headers).json()["reserved_cents"]
        for name, path in ROUTES.items()
    }


def test_nothing_is_set_aside_until_a_plan_is_committed(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    assert {name: world[name]["reserved_cents"] for name in ROUTES} == dict.fromkeys(ROUTES, 0)

    # A draft sets nothing aside.
    client.post(
        "/plans", json={"income_source_id": world["job"]["id"], "pay_date": PAYDAY}, headers=ada
    )
    assert reserved(client, ada, world) == {"rent": 0, "car": 0, "camera": 0}


def test_committing_shows_what_each_target_has_set_aside(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    commit_first_paycheck(client, ada, world)

    assert reserved(client, ada, world) == {"rent": 40_000, "car": 7_500, "camera": 6_667}
    # Lists agree with the single reads.
    for name, path in ROUTES.items():
        (item,) = client.get(path, headers=ada).json()["items"]
        assert (item["id"], item["reserved_cents"]) == (
            world[name]["id"],
            reserved(client, ada, world)[name],
        )
    # Essentials are money to spend, not to hold, so they have no such field.
    (groceries,) = client.get("/essential-expenses", headers=ada).json()["items"]
    assert "reserved_cents" not in groceries


def test_each_target_shows_only_its_own_reserve(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    phone = client.post(
        "/bills",
        json={
            "name": "Phone",
            "amount_cents": 6_000,
            "priority": 2,
            "first_due_date": "2026-10-25",
            "repeat_every_months": 1,
        },
        headers=ada,
    ).json()
    commit_first_paycheck(client, ada, world)

    listed = {
        bill["name"]: bill["reserved_cents"]
        for bill in client.get("/bills", headers=ada).json()["items"]
    }
    # Phone is due Oct 25, after the Oct 16 paycheck, so it is split across two.
    assert listed == {"Rent": 40_000, "Phone": 3_000}
    assert client.get(f"/bills/{phone['id']}", headers=ada).json()["reserved_cents"] == 3_000


def test_paying_shows_the_reserve_drawn_down(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    commit_first_paycheck(client, ada, world)

    part = client.post(
        f"/bills/{world['rent']['id']}/payments", json={"amount_cents": 25_000}, headers=ada
    )
    assert part.status_code == 201
    assert reserved(client, ada, world) == {"rent": 15_000, "car": 7_500, "camera": 6_667}

    assert (
        client.post(f"/bills/{world['rent']['id']}/payments", json={}, headers=ada).status_code
        == 201
    )
    assert (
        client.post(f"/debts/{world['car']['id']}/payments", json={}, headers=ada).status_code
        == 201
    )
    assert reserved(client, ada, world) == {"rent": 0, "car": 0, "camera": 6_667}


def test_replacing_a_bill_or_debt_keeps_and_returns_its_reserve(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    commit_first_paycheck(client, ada, world)
    read_only = {"id", "reserved_cents", "created_at", "updated_at"}

    for name, path, change in (
        ("rent", "/bills", {"amount_cents": 85_000}),
        ("car", "/debts", {"minimum_payment_cents": 16_000}),
    ):
        body = {key: value for key, value in world[name].items() if key not in read_only}
        response = client.put(f"{path}/{world[name]['id']}", json={**body, **change}, headers=ada)
        assert response.status_code == 200, response.text
        assert response.json()["reserved_cents"] == reserved(client, ada, world)[name]

    assert reserved(client, ada, world) == {"rent": 40_000, "car": 7_500, "camera": 6_667}


def test_lowering_a_goals_progress_returns_the_lowered_reserve(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    commit_first_paycheck(client, ada, world)
    camera = client.get(f"/goals/{world['camera']['id']}", headers=ada).json()
    assert (camera["current_cents"], camera["reserved_cents"]) == (6_667, 6_667)
    body = {
        k: v
        for k, v in camera.items()
        if k not in {"id", "reserved_cents", "created_at", "updated_at"}
    }

    lowered = client.put(
        f"/goals/{camera['id']}", json={**body, "current_cents": 2_000}, headers=ada
    )
    assert (lowered.json()["current_cents"], lowered.json()["reserved_cents"]) == (2_000, 2_000)

    raised = client.put(
        f"/goals/{camera['id']}", json={**body, "current_cents": 9_000}, headers=ada
    )
    assert (raised.json()["current_cents"], raised.json()["reserved_cents"]) == (9_000, 2_000)


def test_reserved_cents_cannot_be_set_by_the_client(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    read_only = {"id", "created_at", "updated_at"}
    for name, path in ROUTES.items():
        body = {key: value for key, value in world[name].items() if key not in read_only}
        response = client.put(
            f"{path}/{world[name]['id']}", json={**body, "reserved_cents": 99_999}, headers=ada
        )
        assert response.status_code == 422, response.text
        assert "reserved_cents" in response.json()["error"]["message"]
    assert reserved(client, ada, world) == {"rent": 0, "car": 0, "camera": 0}


def test_another_users_reserves_never_show_on_yours(
    client: TestClient, ada: Headers, bob: Headers, worked_example: Any
) -> None:
    adas, bobs = worked_example(ada), worked_example(bob)
    commit_first_paycheck(client, ada, adas)

    assert reserved(client, bob, bobs) == {"rent": 0, "car": 0, "camera": 0}
    assert reserved(client, ada, adas) == {"rent": 40_000, "car": 7_500, "camera": 6_667}
