"""Plain-English explanations of a plan (US English).

Each sentence is built from the facts the planner records (``Allocation.basis``,
``GoalProjection``, ``PlanResult``), so the app can show these as they are or
build its own wording from the same reason codes.
"""

from datetime import date

from nextpay_engine.money import Money
from nextpay_engine.planning import (
    Allocation,
    Basis,
    GoalProjection,
    GoalStatus,
    PlanResult,
    Reason,
    Tier,
)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# How each tier says what it did with the money.
_VERBS: dict[Tier, tuple[str, str]] = {
    Tier.BILL: ("reserved", "toward"),
    Tier.ESSENTIAL: ("set aside", "for"),
    Tier.DEBT_MINIMUM: ("reserved", "toward"),
    Tier.EMERGENCY_FUND: ("put", "toward"),
    Tier.GOAL: ("put", "toward"),
}
_SAVINGS_TIERS = (Tier.EMERGENCY_FUND, Tier.GOAL)


def explain_allocation(allocation: Allocation, plan: PlanResult) -> str:
    """Why ``allocation`` asked for what it did, and what happened if it fell short.

    "We reserved $400 toward Rent because the $800 bill is due Oct 20 and is split
    across the 2 paychecks before then."
    """
    basis = allocation.basis
    if allocation.is_underfunded:
        lead = f"{basis.name} needs {_money(allocation.requested)} from this paycheck"
    else:
        verb, preposition = _VERBS[allocation.tier]
        lead = f"We {verb} {_money(allocation.requested)} {preposition} {basis.name}"
    sentence = f"{lead} {_why(basis, plan)}."
    if not allocation.is_underfunded:
        return sentence
    covered = "Nothing" if allocation.funded.is_zero() else f"Only {_money(allocation.funded)}"
    if allocation.tier in _SAVINGS_TIERS:
        return f"{sentence} {covered} could go toward it this time, so it will take longer."
    return f"{sentence} {covered} could be covered, so you're {_money(allocation.shortfall)} short."


def explain_projection(projection: GoalProjection, plan: PlanResult) -> str:
    """When the goal would be reached at this paycheck's rate, and against what date."""
    name, rate = projection.name, _money(projection.contribution)
    when = projection.projected_date
    if projection.status is GoalStatus.COMPLETE:
        if projection.contribution.is_positive():
            return f"This paycheck finishes {name}."
        return f"{name} is fully funded."
    if projection.status is GoalStatus.DEADLINE_PASSED:
        passed = projection.deadline
        assert passed is not None
        opening = f"{name}'s date ({_date(passed, plan)}) {_overdue(passed, plan)}."
        if when is None:
            return f"{opening} Pick a new date to put it back on a schedule."
        return (
            f"{opening} At {rate} a paycheck it would be reached by {_date(when, plan)}; "
            "consider that as its new date."
        )

    if when is not None:
        progress = f"At {rate} a paycheck, {name} will be reached by {_date(when, plan)}"
    elif projection.contribution.is_positive():
        progress = f"At {rate} a paycheck, {name} is more than ten years away"
    else:
        progress = f"Nothing went toward {name} this paycheck"
    if projection.deadline is None:
        return f"{progress}."
    deadline = _date(projection.deadline, plan)
    if projection.status is GoalStatus.ON_TRACK:
        return f"{progress}, ahead of its deadline of {deadline}."
    if when is None:
        return f"{progress}, so it will miss its deadline of {deadline}."
    suggested = _date(when, plan)
    return (
        f"{progress}, which misses its deadline of {deadline}. Consider moving it to {suggested}."
    )


def explain_plan(plan: PlanResult) -> str:
    """The Safe to Spend line, and what to watch if the paycheck fell short."""
    if plan.reserve_deficit.is_positive():
        return (
            f"You've set aside {_money(plan.reserve_deficit)} more than you have, so nothing "
            "could be planned from this paycheck. Check your balance and what's set aside."
        )
    if plan.safe_to_spend.is_positive():
        return f"Safe to Spend is {_money(plan.safe_to_spend)}: what's left after everything above."
    short = plan.underfunded
    if not short:
        return "Safe to Spend is $0: everything above used the whole paycheck."
    items = "1 item is" if len(short) == 1 else f"{len(short)} items are"
    sentence = f"Safe to Spend is $0: this paycheck can't cover everything, and {items} short."
    bills = [a.basis.name for a in short if a.tier is Tier.BILL]
    if bills:
        sentence += f" Bills not fully covered: {', '.join(bills)}."
    return sentence


# --- Reasons ----------------------------------------------------------------


def _why(basis: Basis, plan: PlanResult) -> str:
    total = _money(basis.total)
    match basis.reason:
        case Reason.BILL_DUE:
            return _due(f"the {total} bill", basis, plan)
        case Reason.DEBT_MINIMUM:
            return _due(f"the {total} minimum payment", basis, plan)
        case Reason.DEBT_PAYOFF:
            return _due(f"the last {total} you owe", basis, plan)
        case Reason.ESSENTIAL:
            return "to cover this pay period"
        case Reason.ESSENTIAL_PRORATED:
            assert basis.days_covered is not None and basis.days_in_period is not None
            days = _plural(basis.days_covered, "day")
            return (
                f"to cover the {days} until your next paycheck, "
                f"at {total} per {basis.days_in_period}-day pay period"
            )
        case Reason.EMERGENCY_FUND:
            progress = f" ({_money(basis.set_aside)} saved so far)" if basis.set_aside else ""
            return f"to reach its {total} target{progress}"
        case Reason.GOAL_DEADLINE:
            assert basis.due is not None and basis.paychecks is not None
            if basis.set_aside:
                needed = f"{_money(basis.total - basis.set_aside)} of its {total} is still"
            else:
                needed = f"its {total} is"
            return (
                f"because {needed} needed by {_date(basis.due, plan)}, {_spread(basis.paychecks)}"
            )
        case Reason.GOAL_NO_DEADLINE:
            return _leftover_share(basis)
        case Reason.GOAL_DEADLINE_PASSED:
            assert basis.due is not None
            return (
                f"{_leftover_share(basis)}, since its date ({_date(basis.due, plan)}) "
                f"{_overdue(basis.due, plan)}"
            )


def _due(subject: str, basis: Basis, plan: PlanResult) -> str:
    """ "because <subject> is due <date> and is split across the 2 paychecks before then"."""
    assert basis.due is not None and basis.paychecks is not None
    due = f"because {subject} is due {_date(basis.due, plan)}"
    if basis.set_aside:
        rest = "due before your next paycheck" if basis.paychecks == 1 else _spread(basis.paychecks)
        return f"{due}; with {_money(basis.set_aside)} already set aside, the rest is {rest}"
    if basis.paychecks == 1:
        return f"{due}, before your next paycheck"
    return f"{due} and is {_spread(basis.paychecks)}"


def _spread(paychecks: int) -> str:
    if paychecks == 1:
        return "before your next paycheck"
    return f"split across the {paychecks} paychecks before then"


def _leftover_share(basis: Basis) -> str:
    assert basis.share_bps is not None
    return (
        f"as its share of the {_percent(basis.share_bps)} of leftover money "
        "that goes to goals without a deadline"
    )


def _overdue(deadline: date, plan: PlanResult) -> str:
    return "has passed" if deadline < plan.as_of else "is too soon for this paycheck to help"


# --- Formatting -------------------------------------------------------------


def _money(amount: Money) -> str:
    """$400 for whole dollars, $66.67 otherwise."""
    text = str(amount)
    return text.removesuffix(".00")


def _date(day: date, plan: PlanResult) -> str:
    """Oct 20, with the year only when it differs from the paycheck's: Nov 20, 2027."""
    text = f"{_MONTHS[day.month - 1]} {day.day}"
    return text if day.year == plan.paycheck.pay_date.year else f"{text}, {day.year}"


def _percent(bps: int) -> str:
    whole, part = divmod(bps, 100)
    return f"{whole}%" if part == 0 else f"{whole}.{part:02d}".rstrip("0") + "%"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"
