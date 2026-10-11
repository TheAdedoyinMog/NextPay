"""Rows to FinancialState, and the canonical hash of a plan's inputs (ADR 0011)."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest

import nextpay_engine as engine
from app.models import (
    BalanceSnapshot,
    Bill,
    Debt,
    EssentialExpense,
    Goal,
    IncomeSource,
    Paycheck,
    PayFrequency,
    Reserve,
    User,
)
from app.services.engine_mapping import to_engine_paycheck, to_engine_reserve, to_engine_state
from app.services.plan_inputs import canonical_input, input_hash
from nextpay_engine import GoalKind, Money, ReserveKind

AS_OF = date(2026, 10, 2)


def uid(number: int) -> uuid.UUID:
    return uuid.UUID(int=number)


USER = uid(1)


def rows() -> dict[str, Any]:
    """The design doc's worked example, plus a second job, as freshly built rows."""
    return {
        "user": User(id=USER, email="ada@example.com", no_deadline_goal_share_bps=2000),
        "balance": BalanceSnapshot(
            id=uid(2), user_id=USER, amount_cents=40_000, as_of=datetime(2026, 10, 1, tzinfo=UTC)
        ),
        "income_sources": [
            IncomeSource(
                id=uid(10),
                user_id=USER,
                name="Day job",
                expected_amount_cents=150_000,
                pay_frequency=PayFrequency.BIWEEKLY,
                anchor_date=date(2026, 10, 2),
            ),
            IncomeSource(
                id=uid(11),
                user_id=USER,
                name="Weekend job",
                expected_amount_cents=30_000,
                pay_frequency=PayFrequency.SEMI_MONTHLY,
                day_of_month=1,
                second_day_of_month=15,
            ),
        ],
        "bills": [
            Bill(
                id=uid(20),
                user_id=USER,
                name="Rent",
                amount_cents=80_000,
                priority=1,
                first_due_date=date(2026, 10, 20),
                repeat_every_months=1,
            ),
            Bill(
                id=uid(21),
                user_id=USER,
                name="Car registration",
                amount_cents=12_000,
                priority=2,
                first_due_date=date(2026, 12, 1),
                repeat_every_months=None,
            ),
        ],
        "essentials": [
            EssentialExpense(
                id=uid(30), user_id=USER, name="Groceries", amount_per_period_cents=20_000
            )
        ],
        "debts": [
            Debt(
                id=uid(40),
                user_id=USER,
                name="Car loan",
                balance_cents=900_000,
                apr_bps=699,
                minimum_payment_cents=15_000,
                due_day=20,
            )
        ],
        "goals": [
            Goal(
                id=uid(50),
                user_id=USER,
                name="Camera",
                kind=GoalKind.PURCHASE,
                target_cents=200_000,
                current_cents=10_000,
                priority=2,
                deadline=date(2027, 12, 1),
            ),
            Goal(
                id=uid(51),
                user_id=USER,
                name="Emergency fund",
                kind=GoalKind.EMERGENCY,
                target_cents=100_000,
                current_cents=0,
                priority=1,
                deadline=None,
            ),
        ],
        "reserves": [
            Reserve(
                id=uid(60), user_id=USER, kind=ReserveKind.BILL, bill_id=uid(20), amount_cents=5_000
            ),
            Reserve(
                id=uid(61),
                user_id=USER,
                kind=ReserveKind.GOAL,
                goal_id=uid(50),
                amount_cents=10_000,
            ),
            Reserve(
                id=uid(62), user_id=USER, kind=ReserveKind.DEBT, debt_id=uid(40), amount_cents=0
            ),
        ],
    }


def paycheck_row(actual_amount_cents: int | None = None) -> Paycheck:
    return Paycheck(
        id=uid(70),
        user_id=USER,
        income_source_id=uid(10),
        pay_date=date(2026, 10, 2),
        expected_amount_cents=150_000,
        actual_amount_cents=actual_amount_cents,
    )


def hash_of(data: dict[str, Any], paycheck: Paycheck | None = None, as_of: date = AS_OF) -> str:
    return input_hash(
        to_engine_state(**data), to_engine_paycheck(paycheck or paycheck_row()), as_of
    )


# --- rows to engine types ------------------------------------------------------


def test_the_state_carries_every_row() -> None:
    state = to_engine_state(**rows())

    assert state.available_balance == Money(40_000)
    assert state.no_deadline_goal_share_bps == 2000
    assert [source.name for source in state.income_sources] == ["Day job", "Weekend job"]
    assert state.income_sources[0].schedule == engine.Biweekly(date(2026, 10, 2))
    assert [bill.name for bill in state.bills] == ["Rent", "Car registration"]
    assert state.bills[1].recurrence == engine.OneTime(date(2026, 12, 1))
    assert [item.amount_per_period for item in state.essentials] == [Money(20_000)]
    assert [debt.due_day for debt in state.debts] == [20]
    assert state.emergency_goal is not None and state.emergency_goal.id == str(uid(51))
    assert state.reserved_for(ReserveKind.BILL, str(uid(20))) == Money(5_000)
    assert state.reserved_for(ReserveKind.GOAL, str(uid(50))) == Money(10_000)
    # The $0 debt reserve is left out.
    assert state.total_reserved() == Money(15_000)
    assert len(state.reserves) == 2


def test_no_balance_snapshot_means_zero_and_no_rows_means_an_empty_state() -> None:
    state = to_engine_state(
        user=User(email="new@example.com", no_deadline_goal_share_bps=0),
        balance=None,
        income_sources=[],
        bills=[],
        essentials=[],
        debts=[],
        goals=[],
        reserves=[],
    )
    assert state.available_balance == Money.zero()
    assert state.no_deadline_goal_share_bps == 0
    assert state.income_sources == () and state.reserves == ()


def test_an_overdrawn_balance_stays_negative() -> None:
    data = rows()
    data["balance"].amount_cents = -2_500
    assert to_engine_state(**data).available_balance == Money(-2_500)


@pytest.mark.parametrize(
    ("kind", "column"),
    [(ReserveKind.BILL, "bill_id"), (ReserveKind.GOAL, "goal_id"), (ReserveKind.DEBT, "debt_id")],
)
def test_a_reserve_points_at_the_target_its_kind_names(kind: ReserveKind, column: str) -> None:
    row = Reserve(user_id=USER, kind=kind, amount_cents=700, **{column: uid(99)})
    assert to_engine_reserve(row) == engine.Reserve(kind, str(uid(99)), Money(700))


def test_a_paycheck_plans_with_its_actual_amount_once_recorded() -> None:
    expected = to_engine_paycheck(paycheck_row())
    assert (expected.source_id, expected.pay_date) == (str(uid(10)), date(2026, 10, 2))
    assert expected.actual_amount is None and expected.amount == Money(150_000)

    assert to_engine_paycheck(paycheck_row(140_000)).amount == Money(140_000)
    assert to_engine_paycheck(paycheck_row(0)).amount == Money.zero()  # unpaid leave


def test_the_state_is_one_the_planner_accepts() -> None:
    plan = engine.plan_paycheck(
        to_engine_state(**rows()), to_engine_paycheck(paycheck_row()), AS_OF
    )
    assert plan.allocations and not plan.safe_to_spend.is_negative()


# --- the hash ------------------------------------------------------------------


def test_the_hash_is_a_sha256_hex_digest_and_repeatable() -> None:
    first, second = hash_of(rows()), hash_of(rows())
    assert first == second
    assert len(first) == 64 and set(first) <= set("0123456789abcdef")


def test_the_canonical_form_is_pinned() -> None:
    # Changing this value means every stored draft becomes out of date. If that
    # is intended, say so in the ADR and update the value. (A new ENGINE_VERSION
    # changes it too, which is the point: a new engine may plan differently.)
    assert engine.ENGINE_VERSION == "0.2.0"
    assert hash_of(rows()) == "310a316a1091559d348c4caa762a62a2689f984377db254ae5c6678a62fa523e"


def test_the_order_rows_were_loaded_in_does_not_matter() -> None:
    shuffled = rows()
    for name in ("income_sources", "bills", "goals", "reserves"):
        shuffled[name].reverse()
    assert hash_of(shuffled) == hash_of(rows())


def test_a_zero_reserve_hashes_like_no_reserve() -> None:
    without = rows()
    without["reserves"] = [r for r in without["reserves"] if r.amount_cents != 0]
    assert hash_of(without) == hash_of(rows())


def test_a_new_snapshot_of_the_same_balance_does_not_change_the_hash() -> None:
    again = rows()
    again["balance"] = BalanceSnapshot(
        id=uid(999), user_id=USER, amount_cents=40_000, as_of=datetime(2026, 10, 2, tzinfo=UTC)
    )
    assert hash_of(again) == hash_of(rows())


def change(collection: str, index: int, **values: Any) -> Callable[[dict[str, Any]], None]:
    def apply(data: dict[str, Any]) -> None:
        for name, value in values.items():
            setattr(data[collection][index], name, value)

    return apply


def remove(collection: str, index: int) -> Callable[[dict[str, Any]], None]:
    return lambda data: data[collection].pop(index)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: setattr(data["balance"], "amount_cents", 40_001),
        lambda data: data.update(balance=None),
        lambda data: setattr(data["user"], "no_deadline_goal_share_bps", 2500),
        change("income_sources", 0, name="Night job"),
        change("income_sources", 0, expected_amount_cents=150_001),
        change("income_sources", 0, anchor_date=date(2026, 10, 9)),
        change("income_sources", 0, pay_frequency=PayFrequency.WEEKLY),
        change("income_sources", 1, second_day_of_month=16),
        change(
            "income_sources",
            1,
            pay_frequency=PayFrequency.MONTHLY,
            second_day_of_month=None,
        ),
        remove("income_sources", 1),
        change("bills", 0, name="Rent (new place)"),
        change("bills", 0, amount_cents=85_000),
        change("bills", 0, priority=3),
        change("bills", 0, first_due_date=date(2026, 10, 21)),
        change("bills", 0, repeat_every_months=3),
        change("bills", 0, repeat_every_months=None),
        change("bills", 1, first_due_date=date(2026, 12, 2)),
        remove("bills", 1),
        change("essentials", 0, name="Food"),
        change("essentials", 0, amount_per_period_cents=25_000),
        remove("essentials", 0),
        change("debts", 0, name="Auto loan"),
        change("debts", 0, balance_cents=899_999),
        change("debts", 0, apr_bps=700),
        change("debts", 0, minimum_payment_cents=16_000),
        change("debts", 0, due_day=21),
        remove("debts", 0),
        change("goals", 0, name="Lens"),
        change("goals", 0, kind=GoalKind.SAVINGS),
        change("goals", 0, target_cents=250_000),
        change("goals", 0, current_cents=10_001),
        change("goals", 0, priority=1),
        change("goals", 0, deadline=date(2027, 12, 2)),
        change("goals", 0, deadline=None),
        remove("goals", 1),
        change("reserves", 0, amount_cents=5_001),
        change("reserves", 2, amount_cents=1),
        remove("reserves", 1),
    ],
)
def test_any_change_the_planner_could_see_changes_the_hash(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    data = rows()
    mutate(data)
    assert hash_of(data) != hash_of(rows())


def test_the_paycheck_the_date_and_the_engine_version_are_part_of_the_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = hash_of(rows())
    assert hash_of(rows(), paycheck_row(actual_amount_cents=140_000)) != base
    assert hash_of(rows(), paycheck_row(actual_amount_cents=0)) != base
    assert hash_of(rows(), as_of=date(2026, 10, 3)) != base

    other_day = paycheck_row()
    other_day.pay_date = date(2026, 10, 16)
    assert hash_of(rows(), other_day) != base
    other_source = paycheck_row()
    other_source.income_source_id = uid(11)
    assert hash_of(rows(), other_source) != base
    other_amount = paycheck_row()
    other_amount.expected_amount_cents = 150_001
    assert hash_of(rows(), other_amount) != base

    monkeypatch.setattr(engine, "ENGINE_VERSION", "9.9.9")
    assert hash_of(rows()) != base


def test_the_canonical_form_names_every_schedule_and_recurrence() -> None:
    document = canonical_input(to_engine_state(**rows()), to_engine_paycheck(paycheck_row()), AS_OF)
    schedules = [source["schedule"] for source in document["state"]["income_sources"]]
    assert schedules == [
        {"type": "biweekly", "anchor": "2026-10-02"},
        {"type": "semi_monthly", "first_day": 1, "second_day": 15},
    ]
    recurrences = [bill["recurrence"] for bill in document["state"]["bills"]]
    assert recurrences == [
        {"type": "every_n_months", "first_due": "2026-10-20", "months": 1},
        {"type": "one_time", "due": "2026-12-01"},
    ]
    assert document["engine_version"] == engine.ENGINE_VERSION
    assert document["paycheck"] == {
        "source_id": str(uid(10)),
        "pay_date": "2026-10-02",
        "expected_cents": 150_000,
        "actual_cents": None,
    }


def test_weekly_and_monthly_schedules_have_a_canonical_form() -> None:
    data = rows()
    data["income_sources"][0].pay_frequency = PayFrequency.WEEKLY
    data["income_sources"][1].pay_frequency = PayFrequency.MONTHLY
    data["income_sources"][1].second_day_of_month = None
    document = canonical_input(to_engine_state(**data), to_engine_paycheck(paycheck_row()), AS_OF)
    assert [source["schedule"] for source in document["state"]["income_sources"]] == [
        {"type": "weekly", "anchor": "2026-10-02"},
        {"type": "monthly", "day": 1},
    ]


def test_an_unknown_schedule_or_recurrence_cannot_be_hashed_by_accident() -> None:
    class EveryFullMoon:
        def dates_between(self, start: date, end: date) -> tuple[date, ...]:
            return ()

        def due_dates_between(self, start: date, end: date) -> tuple[date, ...]:
            return ()

        def next_due_after(self, day: date) -> date | None:
            return None

    source = engine.IncomeSource("s", "Odd job", EveryFullMoon(), Money(100))
    bill = engine.Bill("b", "Odd bill", Money(100), EveryFullMoon(), 1)
    paycheck = engine.Paycheck("s", AS_OF, Money(100))

    with pytest.raises(TypeError, match="pay schedule EveryFullMoon"):
        input_hash(engine.FinancialState(Money.zero(), income_sources=(source,)), paycheck, AS_OF)
    with pytest.raises(TypeError, match="bill recurrence EveryFullMoon"):
        input_hash(engine.FinancialState(Money.zero(), bills=(bill,)), paycheck, AS_OF)
