"""The canonical form of a plan's inputs, and its hash (ADR 0011).

``plan_paycheck`` is deterministic, so a plan is fully decided by the engine
version and the three things it is given: the state, the paycheck, and
``as_of``. Hashing them answers one question cheaply: would planning again give
the same plan? A draft whose hash no longer matches is out of date and cannot
be committed.

The canonical form is a JSON document built from the engine's own objects (so
it describes exactly what was planned), with every collection sorted by id,
keys sorted, no whitespace, money as integer cents, and dates as ISO strings.
Changing what goes into it changes every hash, which makes every existing draft
out of date; a golden test pins the format.
"""

import hashlib
import json
from datetime import date
from typing import Any

import nextpay_engine as engine


def input_hash(state: engine.FinancialState, paycheck: engine.Paycheck, as_of: date) -> str:
    """SHA-256 (hex) of ``canonical_input``."""
    document = json.dumps(
        canonical_input(state, paycheck, as_of), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


def canonical_input(
    state: engine.FinancialState, paycheck: engine.Paycheck, as_of: date
) -> dict[str, Any]:
    """Every fact the planner reads, and nothing else (no row ids of balances,
    no timestamps), in a form that does not depend on the order rows were loaded."""
    return {
        "engine_version": engine.ENGINE_VERSION,
        "as_of": as_of.isoformat(),
        "paycheck": {
            "source_id": paycheck.source_id,
            "pay_date": paycheck.pay_date.isoformat(),
            "expected_cents": paycheck.expected_amount.cents,
            "actual_cents": _cents(paycheck.actual_amount),
        },
        "state": {
            "available_balance_cents": state.available_balance.cents,
            "no_deadline_goal_share_bps": state.no_deadline_goal_share_bps,
            "income_sources": _by_id(
                {
                    "id": source.id,
                    "name": source.name,
                    "expected_cents": source.expected_amount.cents,
                    "schedule": _schedule(source.schedule),
                }
                for source in state.income_sources
            ),
            "bills": _by_id(
                {
                    "id": bill.id,
                    "name": bill.name,
                    "amount_cents": bill.amount.cents,
                    "priority": bill.priority,
                    "recurrence": _recurrence(bill.recurrence),
                }
                for bill in state.bills
            ),
            "essentials": _by_id(
                {
                    "id": item.id,
                    "name": item.name,
                    "amount_per_period_cents": item.amount_per_period.cents,
                }
                for item in state.essentials
            ),
            "debts": _by_id(
                {
                    "id": debt.id,
                    "name": debt.name,
                    "balance_cents": debt.balance.cents,
                    "apr_bps": debt.apr_bps,
                    "minimum_payment_cents": debt.minimum_payment.cents,
                    "due_day": debt.due_day,
                }
                for debt in state.debts
            ),
            "goals": _by_id(
                {
                    "id": goal.id,
                    "name": goal.name,
                    "kind": goal.kind.value,
                    "target_cents": goal.target.cents,
                    "current_cents": goal.current.cents,
                    "priority": goal.priority,
                    "deadline": None if goal.deadline is None else goal.deadline.isoformat(),
                }
                for goal in state.goals
            ),
            # A $0 reserve is no reserve to the planner, so it must not change the hash.
            "reserves": sorted(
                (
                    {
                        "kind": reserve.kind.value,
                        "target_id": reserve.target_id,
                        "amount_cents": reserve.amount.cents,
                    }
                    for reserve in state.reserves
                    if not reserve.amount.is_zero()
                ),
                key=lambda reserve: (reserve["kind"], reserve["target_id"]),
            ),
        },
    }


def _by_id(items: Any) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: item["id"])


def _cents(amount: engine.Money | None) -> int | None:
    return None if amount is None else amount.cents


def _schedule(schedule: engine.PaySchedule) -> dict[str, Any]:
    if isinstance(schedule, engine.Weekly):
        return {"type": "weekly", "anchor": schedule.anchor.isoformat()}
    if isinstance(schedule, engine.Biweekly):
        return {"type": "biweekly", "anchor": schedule.anchor.isoformat()}
    if isinstance(schedule, engine.SemiMonthly):
        return {
            "type": "semi_monthly",
            "first_day": schedule.first_day,
            "second_day": schedule.second_day,
        }
    if isinstance(schedule, engine.Monthly):
        return {"type": "monthly", "day": schedule.day}
    raise TypeError(f"no canonical form for pay schedule {type(schedule).__name__}")


def _recurrence(recurrence: engine.BillRecurrence) -> dict[str, Any]:
    if isinstance(recurrence, engine.OneTime):
        return {"type": "one_time", "due": recurrence.due.isoformat()}
    if isinstance(recurrence, engine.EveryNMonths):
        return {
            "type": "every_n_months",
            "first_due": recurrence.first_due.isoformat(),
            "months": recurrence.months,
        }
    raise TypeError(f"no canonical form for bill recurrence {type(recurrence).__name__}")
