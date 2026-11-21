"""Milestone 3D's API additions, end to end against PostgreSQL (ADR 0015):

- GET /dashboard: the home screen's facts, chosen by the server.
- ``is_out_of_date`` on plans: what commit would refuse, known before committing.
- A client-made payment ``id``: a repeated payment request records one payment.
- Safe to Spend on the dashboard falls by what a payment pays beyond its reserve (ADR 0016).
- Undoing a payment puts back exactly what it took, once, until the next commit (ADR 0017).

The setup is the design doc's worked example: $1,500 every two weeks from Friday,
Oct 2, 2026. The fake clock is at noon UTC on Oct 7, so the current paycheck is
Oct 2 and the next is Oct 16.
"""

import uuid
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BillPayment, DebtPayment, Reserve

type Json = dict[str, Any]
type Headers = dict[str, str]

PAYDAY = "2026-10-02"


def plan(client: TestClient, headers: Headers, source: Json, pay_date: str = PAYDAY) -> Json:
    response = client.post(
        "/plans", json={"income_source_id": source["id"], "pay_date": pay_date}, headers=headers
    )
    assert response.status_code in (200, 201), response.text
    return dict(response.json())


def commit(client: TestClient, headers: Headers, body: Json) -> Json:
    response = client.post(f"/plans/{body['id']}/commit", headers=headers)
    assert response.status_code == 200, response.text
    return dict(response.json())


def dashboard(client: TestClient, headers: Headers) -> Json:
    response = client.get("/dashboard", headers=headers)
    assert response.status_code == 200, response.text
    return dict(response.json())


def sign_in_again(client: TestClient, email: str) -> Headers:
    """After the fake clock moves past the 15-minute access token."""
    response = client.post(
        "/auth/login", json={"email": email, "password": "correct horse battery"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def reserved(session: Session, **target: uuid.UUID) -> int | None:
    session.expire_all()
    ((column, value),) = target.items()
    return session.scalar(select(Reserve.amount_cents).where(getattr(Reserve, column) == value))


# --- the dashboard -------------------------------------------------------------


def test_a_new_account_has_an_empty_dashboard(client: TestClient, ada: Headers) -> None:
    assert dashboard(client, ada) == {
        "today": "2026-10-07",
        "current_paycheck": None,
        "next_paycheck": None,
        "safe_to_spend": None,
        "balance": None,
    }


def test_it_names_the_current_and_next_paycheck(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)

    body = dashboard(client, ada)

    assert body["current_paycheck"]["pay_date"] == PAYDAY
    assert body["current_paycheck"]["income_source_id"] == world["job"]["id"]
    assert body["current_paycheck"]["plan"] is None
    assert body["next_paycheck"]["pay_date"] == "2026-10-16"
    assert body["safe_to_spend"] is None


def test_today_is_the_users_own_date(client: TestClient, ada: Headers, clock: Any) -> None:
    clock.advance(timedelta(hours=11))  # 23:00 UTC on Oct 7: Oct 8 in Tokyo
    ada = sign_in_again(client, "ada@example.com")
    client.put(
        "/me/settings",
        json={"timezone": "Asia/Tokyo", "no_deadline_goal_share_bps": 2000},
        headers=ada,
    )

    assert dashboard(client, ada)["today"] == "2026-10-08"


def test_a_draft_is_shown_but_safe_to_spend_waits_for_a_commit(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    draft = plan(client, ada, world["job"])

    body = dashboard(client, ada)

    assert body["current_paycheck"]["plan"] == {
        "id": draft["id"],
        "version": 1,
        "status": "draft",
        "safe_to_spend_cents": 75_833,
        "is_out_of_date": False,
    }
    assert body["safe_to_spend"] is None


def test_safe_to_spend_comes_from_the_committed_plan(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    committed = commit(client, ada, plan(client, ada, world["job"]))

    assert dashboard(client, ada)["safe_to_spend"] == {
        "plan_id": committed["id"],
        "pay_date": PAYDAY,
        "income_source_name": world["job"]["name"],
        "safe_to_spend_cents": 75_833,
        "reserve_deficit_cents": 0,
        "paid_beyond_reserves_cents": 0,
    }


def test_it_shows_the_latest_balance(client: TestClient, ada: Headers, clock: Any) -> None:
    client.post("/balance-snapshots", json={"amount_cents": 1_000}, headers=ada)
    clock.advance(timedelta(minutes=1))
    client.post("/balance-snapshots", json={"amount_cents": 81_229}, headers=ada)

    assert dashboard(client, ada)["balance"]["amount_cents"] == 81_229


def test_another_users_plans_never_show(
    client: TestClient, ada: Headers, bob: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    commit(client, ada, plan(client, ada, world["job"]))

    assert dashboard(client, bob)["safe_to_spend"] is None
    assert dashboard(client, bob)["current_paycheck"] is None


# --- out of date ---------------------------------------------------------------


def test_a_draft_goes_out_of_date_when_setup_changes_and_a_new_one_is_current(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    draft = plan(client, ada, world["job"])
    assert draft["is_out_of_date"] is False

    rent = world["rent"]
    client.put(
        f"/bills/{rent['id']}",
        json={
            "name": rent["name"],
            "amount_cents": rent["amount_cents"] + 100,
            "priority": rent["priority"],
            "first_due_date": rent["first_due_date"],
            "repeat_every_months": rent["repeat_every_months"],
        },
        headers=ada,
    )

    read = client.get(f"/plans/{draft['id']}", headers=ada).json()
    assert read["is_out_of_date"] is True
    assert read["paycheck"]["plan"]["is_out_of_date"] is True
    assert dashboard(client, ada)["current_paycheck"]["plan"]["is_out_of_date"] is True
    timeline = client.get("/paychecks", params={"start": PAYDAY, "end": PAYDAY}, headers=ada)
    assert timeline.json()["items"][0]["plan"]["is_out_of_date"] is True
    # It is exactly what commit refuses.
    refused = client.post(f"/plans/{draft['id']}/commit", headers=ada)
    assert refused.json()["error"]["code"] == "plan_out_of_date"

    again = plan(client, ada, world["job"])
    assert (again["version"], again["is_out_of_date"]) == (2, False)


def test_recording_the_actual_amount_makes_the_draft_out_of_date(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    plan(client, ada, world["job"])

    response = client.put(
        f"/income-sources/{world['job']['id']}/paychecks/{PAYDAY}",
        json={"actual_amount_cents": 140_000},
        headers=ada,
    )

    assert response.json()["plan"]["is_out_of_date"] is True


def test_the_same_balance_entered_again_leaves_the_draft_current(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    """The app asks for the balance every time it plans (ADR 0015); confirming it is harmless."""
    world = worked_example(ada)
    client.post("/balance-snapshots", json={"amount_cents": 50_000}, headers=ada)
    draft = plan(client, ada, world["job"])

    client.post("/balance-snapshots", json={"amount_cents": 50_000}, headers=ada)

    assert client.get(f"/plans/{draft['id']}", headers=ada).json()["is_out_of_date"] is False
    assert plan(client, ada, world["job"])["id"] == draft["id"]


def test_a_committed_plan_is_never_out_of_date(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    committed = commit(client, ada, plan(client, ada, world["job"]))
    client.post("/balance-snapshots", json={"amount_cents": 1}, headers=ada)

    assert client.get(f"/plans/{committed['id']}", headers=ada).json()["is_out_of_date"] is False


def test_committing_twice_returns_the_same_plan_and_reserves_once(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    draft = plan(client, ada, world["job"])

    first = commit(client, ada, draft)
    second = commit(client, ada, draft)

    assert first == second
    assert reserved(db_session, bill_id=uuid.UUID(world["rent"]["id"])) == 40_000


# --- Safe to Spend after payments (ADR 0016) -----------------------------------


def safe_now(client: TestClient, headers: Headers) -> tuple[int, int, int]:
    safe = dashboard(client, headers)["safe_to_spend"]
    return (
        safe["safe_to_spend_cents"],
        safe["reserve_deficit_cents"],
        safe["paid_beyond_reserves_cents"],
    )


def test_a_payment_covered_by_its_reserve_leaves_safe_to_spend_alone(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    commit(client, ada, plan(client, ada, world["job"]))
    rent = world["rent"]
    assert reserved(db_session, bill_id=uuid.UUID(rent["id"])) == 40_000

    client.post(f"/bills/{rent['id']}/payments", json={"amount_cents": 40_000}, headers=ada)

    assert safe_now(client, ada) == (75_833, 0, 0)
    assert reserved(db_session, bill_id=uuid.UUID(rent["id"])) == 0


def test_paying_more_than_was_set_aside_comes_out_of_safe_to_spend(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    """$75 set aside for the car's $150 minimum; paying $150 takes $75 from Safe to Spend."""
    world = worked_example(ada)
    commit(client, ada, plan(client, ada, world["job"]))
    car = world["car"]
    assert reserved(db_session, debt_id=uuid.UUID(car["id"])) == 7_500

    client.post(f"/debts/{car['id']}/payments", json={}, headers=ada)

    assert safe_now(client, ada) == (68_333, 0, 7_500)
    assert reserved(db_session, debt_id=uuid.UUID(car["id"])) == 0


def test_a_repeated_payment_lowers_safe_to_spend_once(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    commit(client, ada, plan(client, ada, world["job"]))
    body = {"id": str(uuid.uuid4())}

    for _ in range(2):
        client.post(f"/debts/{world['car']['id']}/payments", json=body, headers=ada)

    assert safe_now(client, ada) == (68_333, 0, 7_500)


def test_paying_past_safe_to_spend_shows_a_shortfall_not_a_negative(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    commit(client, ada, plan(client, ada, world["job"]))

    # $1,000 toward rent with $400 set aside: $600 beyond, against $758.33 free.
    client.post(
        f"/bills/{world['rent']['id']}/payments", json={"amount_cents": 100_000}, headers=ada
    )
    assert safe_now(client, ada) == (15_833, 0, 60_000)
    # $250 toward the car with $75 set aside: $175 beyond, $16.67 more than was free.
    client.post(f"/debts/{world['car']['id']}/payments", json={"amount_cents": 25_000}, headers=ada)
    assert safe_now(client, ada) == (0, 1_667, 77_500)


def test_payments_before_the_commit_do_not_count(
    client: TestClient, ada: Headers, worked_example: Any, clock: Any
) -> None:
    """The plan started from a balance entered after them, so they are already in it."""
    world = worked_example(ada)
    client.post(f"/debts/{world['car']['id']}/payments", json={}, headers=ada)
    clock.advance(timedelta(minutes=1))
    ada = sign_in_again(client, "ada@example.com")

    committed = commit(client, ada, plan(client, ada, world["job"]))

    assert safe_now(client, ada) == (committed["safe_to_spend_cents"], 0, 0)


def test_a_payment_after_the_plan_does_not_change_the_plan_itself(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    """A committed plan is a record of what was decided; only the dashboard moves."""
    world = worked_example(ada)
    committed = commit(client, ada, plan(client, ada, world["job"]))

    client.post(f"/debts/{world['car']['id']}/payments", json={}, headers=ada)

    again = client.get(f"/plans/{committed['id']}", headers=ada).json()
    assert again["safe_to_spend_cents"] == 75_833


# --- payment ids ---------------------------------------------------------------


def test_a_repeated_bill_payment_is_recorded_once(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    commit(client, ada, plan(client, ada, world["job"]))
    rent = world["rent"]
    payment_id = str(uuid.uuid4())
    body = {"id": payment_id, "amount_cents": 30_000}

    first = client.post(f"/bills/{rent['id']}/payments", json=body, headers=ada)
    # A retry after a timeout, or a second tap: the same request again.
    second = client.post(f"/bills/{rent['id']}/payments", json=body, headers=ada)

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json() == second.json()
    assert first.json()["id"] == payment_id
    assert db_session.scalar(select(func.count()).select_from(BillPayment)) == 1
    assert reserved(db_session, bill_id=uuid.UUID(rent["id"])) == 10_000


def test_a_repeated_debt_payment_lowers_the_balance_once(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    loan = world["car"]
    body = {"id": str(uuid.uuid4())}

    for _ in range(3):
        client.post(f"/debts/{loan['id']}/payments", json=body, headers=ada)

    assert db_session.scalar(select(func.count()).select_from(DebtPayment)) == 1
    after = client.get(f"/debts/{loan['id']}", headers=ada).json()
    assert after["balance_cents"] == loan["balance_cents"] - loan["minimum_payment_cents"]


def test_a_retry_the_next_day_returns_the_original_payment(
    client: TestClient, ada: Headers, worked_example: Any, clock: Any
) -> None:
    """Left-out fields default to today; a retry must not become a second payment."""
    rent = worked_example(ada)["rent"]
    body = {"id": str(uuid.uuid4())}
    first = client.post(f"/bills/{rent['id']}/payments", json=body, headers=ada).json()
    clock.advance(timedelta(days=1))
    ada = sign_in_again(client, "ada@example.com")

    second = client.post(f"/bills/{rent['id']}/payments", json=body, headers=ada)

    assert second.status_code == 200
    assert second.json() == first


def test_a_payment_id_used_for_another_bill_is_refused(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    rent = worked_example(ada)["rent"]
    phone = client.post(
        "/bills",
        json={
            "name": "Phone",
            "amount_cents": 4_599,
            "priority": 2,
            "first_due_date": "2026-10-25",
            "repeat_every_months": 1,
        },
        headers=ada,
    ).json()
    body = {"id": str(uuid.uuid4())}
    client.post(f"/bills/{rent['id']}/payments", json=body, headers=ada)

    response = client.post(f"/bills/{phone['id']}/payments", json=body, headers=ada)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "payment_id_conflict"
    assert db_session.scalar(select(func.count()).select_from(BillPayment)) == 1


def test_another_users_payment_id_is_refused_without_revealing_it(
    client: TestClient, ada: Headers, bob: Headers, worked_example: Any
) -> None:
    adas_rent = worked_example(ada)["rent"]
    bobs_rent = worked_example(bob)["rent"]
    body = {"id": str(uuid.uuid4())}
    client.post(f"/bills/{adas_rent['id']}/payments", json=body, headers=ada)

    response = client.post(f"/bills/{bobs_rent['id']}/payments", json=body, headers=bob)

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "payment_id_conflict",
        "message": "This payment id is already used by another payment. Make a new one.",
    }


def test_without_an_id_each_request_is_a_new_payment(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    rent = worked_example(ada)["rent"]

    client.post(f"/bills/{rent['id']}/payments", json={}, headers=ada)
    client.post(f"/bills/{rent['id']}/payments", json={}, headers=ada)

    assert db_session.scalar(select(func.count()).select_from(BillPayment)) == 2


# --- undoing a payment (ADR 0017) ----------------------------------------------


def pay_debt(client: TestClient, headers: Headers, debt: Json, **body: Any) -> Json:
    response = client.post(f"/debts/{debt['id']}/payments", json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return dict(response.json())


def undo_debt(client: TestClient, headers: Headers, debt: Json, payment: Json) -> Any:
    return client.post(f"/debts/{debt['id']}/payments/{payment['id']}/undo", headers=headers)


def debt_balance(client: TestClient, headers: Headers, debt: Json) -> int:
    return int(client.get(f"/debts/{debt['id']}", headers=headers).json()["balance_cents"])


def test_undo_puts_safe_to_spend_the_reserve_and_the_balance_back_exactly(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    """$75 set aside for the car's $150 minimum: paying takes $75 from Safe to Spend, and
    undoing it gives the $75 back and refills the reserve."""
    world = worked_example(ada)
    car = world["car"]
    commit(client, ada, plan(client, ada, world["job"]))
    assert safe_now(client, ada) == (75_833, 0, 0)

    payment = pay_debt(client, ada, car, id=str(uuid.uuid4()))
    assert safe_now(client, ada) == (68_333, 0, 7_500)
    assert reserved(db_session, debt_id=uuid.UUID(car["id"])) == 0
    assert debt_balance(client, ada, car) == 885_000

    response = undo_debt(client, ada, car, payment)

    assert response.status_code == 200, response.text
    undone = response.json()
    assert undone["id"] == payment["id"]
    assert undone["undone_at"] is not None
    assert undone["can_undo"] is False
    assert safe_now(client, ada) == (75_833, 0, 0)
    assert reserved(db_session, debt_id=uuid.UUID(car["id"])) == 7_500
    assert debt_balance(client, ada, car) == 900_000
    # Kept as history, but no longer listed.
    assert db_session.scalar(select(func.count()).select_from(DebtPayment)) == 1
    listed = client.get(f"/debts/{car['id']}/payments", headers=ada).json()
    assert listed == {"items": []}


def test_undoing_a_covered_bill_payment_leaves_safe_to_spend_alone(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    rent = world["rent"]
    commit(client, ada, plan(client, ada, world["job"]))
    payment = client.post(
        f"/bills/{rent['id']}/payments", json={"amount_cents": 40_000}, headers=ada
    ).json()
    assert reserved(db_session, bill_id=uuid.UUID(rent["id"])) == 0

    response = client.post(f"/bills/{rent['id']}/payments/{payment['id']}/undo", headers=ada)

    assert response.status_code == 200, response.text
    assert safe_now(client, ada) == (75_833, 0, 0)
    assert reserved(db_session, bill_id=uuid.UUID(rent["id"])) == 40_000
    assert client.get(f"/bills/{rent['id']}/payments", headers=ada).json() == {"items": []}


def test_a_repeated_undo_undoes_once(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    """A double tap, or a retry after the first reply was lost: the second request finds the
    payment already undone and changes nothing."""
    world = worked_example(ada)
    car = world["car"]
    commit(client, ada, plan(client, ada, world["job"]))
    payment = pay_debt(client, ada, car)

    first = undo_debt(client, ada, car, payment)
    second = undo_debt(client, ada, car, payment)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert reserved(db_session, debt_id=uuid.UUID(car["id"])) == 7_500
    assert debt_balance(client, ada, car) == 900_000
    assert safe_now(client, ada) == (75_833, 0, 0)


def test_a_retry_of_an_undo_the_next_day_still_undoes_once(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session, clock: Any
) -> None:
    world = worked_example(ada)
    car = world["car"]
    commit(client, ada, plan(client, ada, world["job"]))
    payment = pay_debt(client, ada, car)
    first = undo_debt(client, ada, car, payment).json()
    clock.advance(timedelta(days=1))
    ada = sign_in_again(client, "ada@example.com")

    second = undo_debt(client, ada, car, payment)

    assert second.status_code == 200
    assert second.json() == first
    assert reserved(db_session, debt_id=uuid.UUID(car["id"])) == 7_500


def test_undoing_an_overpayment_puts_back_only_what_was_owed(
    client: TestClient, ada: Headers, db_session: Session
) -> None:
    """$100 owed, $150 paid: the balance stopped at $0, so undo puts back $100, not $150."""
    card = client.post(
        "/debts",
        json={
            "name": "Store card",
            "balance_cents": 10_000,
            "apr_bps": 2_499,
            "minimum_payment_cents": 2_500,
            "due_day": 15,
        },
        headers=ada,
    ).json()
    payment = pay_debt(client, ada, card, amount_cents=15_000)
    assert debt_balance(client, ada, card) == 0

    undo_debt(client, ada, card, payment)

    assert debt_balance(client, ada, card) == 10_000
    row = db_session.get(DebtPayment, uuid.UUID(payment["id"]))
    assert row is not None and row.balance_reduced_cents == 10_000


def test_a_payment_cannot_be_undone_after_a_later_commit(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session, clock: Any
) -> None:
    """The Oct 16 plan was made around the empty car reserve; refilling it now would hold
    the same $75 twice."""
    world = worked_example(ada)
    car = world["car"]
    commit(client, ada, plan(client, ada, world["job"]))
    payment = pay_debt(client, ada, car)
    clock.advance(timedelta(minutes=1))
    commit(client, ada, plan(client, ada, world["job"], "2026-10-16"))
    reserve_before = reserved(db_session, debt_id=uuid.UUID(car["id"]))

    response = undo_debt(client, ada, car, payment)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "payment_undo_too_late"
    assert reserved(db_session, debt_id=uuid.UUID(car["id"])) == reserve_before
    assert debt_balance(client, ada, car) == 885_000
    listed = client.get(f"/debts/{car['id']}/payments", headers=ada).json()["items"]
    assert [(item["id"], item["can_undo"]) for item in listed] == [(payment["id"], False)]


def test_undo_makes_a_draft_from_before_the_payment_current_again(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    """Out of date is the hash of today's inputs, never stored. The payment changed the car's
    reserve and balance; undo puts both back exactly, so the earlier draft matches again."""
    world = worked_example(ada)
    car = world["car"]
    commit(client, ada, plan(client, ada, world["job"]))
    draft = plan(client, ada, world["job"], "2026-10-16")
    payment = pay_debt(client, ada, car)
    assert client.get(f"/plans/{draft['id']}", headers=ada).json()["is_out_of_date"] is True

    undo_debt(client, ada, car, payment)

    assert client.get(f"/plans/{draft['id']}", headers=ada).json()["is_out_of_date"] is False
    assert dashboard(client, ada)["next_paycheck"]["plan"]["is_out_of_date"] is False
    commit(client, ada, draft)


def test_undo_makes_a_draft_made_after_the_payment_out_of_date(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    car = world["car"]
    commit(client, ada, plan(client, ada, world["job"]))
    payment = pay_debt(client, ada, car)
    after_payment = plan(client, ada, world["job"], "2026-10-16")

    undo_debt(client, ada, car, payment)

    read = client.get(f"/plans/{after_payment['id']}", headers=ada).json()
    assert read["is_out_of_date"] is True
    refused = client.post(f"/plans/{after_payment['id']}/commit", headers=ada)
    assert refused.json()["error"]["code"] == "plan_out_of_date"


def test_an_undone_payment_can_be_paid_again_as_a_new_payment(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    world = worked_example(ada)
    car = world["car"]
    commit(client, ada, plan(client, ada, world["job"]))
    first = pay_debt(client, ada, car, id=str(uuid.uuid4()))
    undo_debt(client, ada, car, first)

    again = client.post(f"/debts/{car['id']}/payments", json={"id": str(uuid.uuid4())}, headers=ada)

    assert again.status_code == 201
    assert again.json()["can_undo"] is True
    assert safe_now(client, ada) == (68_333, 0, 7_500)
    assert reserved(db_session, debt_id=uuid.UUID(car["id"])) == 0
    assert debt_balance(client, ada, car) == 885_000
    listed = client.get(f"/debts/{car['id']}/payments", headers=ada).json()["items"]
    assert [item["id"] for item in listed] == [again.json()["id"]]


def test_the_undone_payments_own_id_is_a_retry_not_a_new_payment(
    client: TestClient, ada: Headers, worked_example: Any, db_session: Session
) -> None:
    """A late retry of the original "Mark paid" must not bring an undone payment back."""
    world = worked_example(ada)
    car = world["car"]
    commit(client, ada, plan(client, ada, world["job"]))
    body = {"id": str(uuid.uuid4())}
    first = pay_debt(client, ada, car, **body)
    undo_debt(client, ada, car, first)

    retry = client.post(f"/debts/{car['id']}/payments", json=body, headers=ada)

    assert retry.status_code == 200
    assert retry.json()["undone_at"] is not None
    assert safe_now(client, ada) == (75_833, 0, 0)
    assert debt_balance(client, ada, car) == 900_000
    assert db_session.scalar(select(func.count()).select_from(DebtPayment)) == 1


def test_a_payment_is_undone_only_through_its_own_bill_or_debt(
    client: TestClient, ada: Headers, worked_example: Any
) -> None:
    world = worked_example(ada)
    rent_paid = client.post(f"/bills/{world['rent']['id']}/payments", json={}, headers=ada).json()
    car_paid = pay_debt(client, ada, world["car"])

    wrong_debt = client.post(
        f"/debts/{world['car']['id']}/payments/{rent_paid['id']}/undo", headers=ada
    )
    wrong_bill = client.post(
        f"/bills/{world['rent']['id']}/payments/{car_paid['id']}/undo", headers=ada
    )

    assert wrong_debt.status_code == wrong_bill.status_code == 404
