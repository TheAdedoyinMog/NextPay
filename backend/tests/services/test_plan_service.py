"""PlanService.generate and .get, with in-memory fakes (see conftest.py).

The setup is the design doc's worked example: paid $1,500 on Oct 2 and every two
weeks after; $800 rent due Oct 20; $200 of groceries a period; a $150 car
minimum due the 20th; and a $2,000 camera with 30 paychecks to go. The fake
clock is at noon UTC on Oct 7, 2026.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from app.core.errors import (
    InvalidInputError,
    NotFoundError,
    PaycheckAlreadyCommittedError,
    PlanOutOfDateError,
    PlanSupersededError,
)
from app.models import (
    BalanceSnapshot,
    Bill,
    Debt,
    EssentialExpense,
    Goal,
    IncomeSource,
    PaycheckPlan,
    PayFrequency,
    PlanStatus,
    Reserve,
    User,
)
from app.services.plans import PlanService
from nextpay_engine import ENGINE_VERSION, GoalKind, GoalStatus, Reason, ReserveKind, Tier

ADA = User(
    id=uuid.uuid4(), email="ada@example.com", timezone="UTC", no_deadline_goal_share_bps=2000
)
BOB = User(
    id=uuid.uuid4(), email="bob@example.com", timezone="UTC", no_deadline_goal_share_bps=2000
)
PAYDAY = date(2026, 10, 2)

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


class World:
    """The worked example's rows, added to the fake stores for one user."""

    def __init__(
        self,
        user: User,
        income_sources: Fake,
        bills: Fake,
        essentials: Fake,
        debts: Fake,
        goals: Fake,
    ) -> None:
        owner: dict[str, Any] = {"user_id": user.id}
        self.job = income_sources.add(
            IncomeSource(
                id=uuid.uuid4(),
                name="Day job",
                expected_amount_cents=150_000,
                pay_frequency=PayFrequency.BIWEEKLY,
                anchor_date=PAYDAY,
                **owner,
            )
        )
        self.rent = bills.add(
            Bill(
                id=uuid.uuid4(),
                name="Rent",
                amount_cents=80_000,
                priority=1,
                first_due_date=date(2026, 10, 20),
                repeat_every_months=1,
                **owner,
            )
        )
        self.groceries = essentials.add(
            EssentialExpense(
                id=uuid.uuid4(), name="Groceries", amount_per_period_cents=20_000, **owner
            )
        )
        self.car = debts.add(
            Debt(
                id=uuid.uuid4(),
                name="Car loan",
                balance_cents=900_000,
                apr_bps=699,
                minimum_payment_cents=15_000,
                due_day=20,
                **owner,
            )
        )
        self.camera = goals.add(
            Goal(
                id=uuid.uuid4(),
                name="Camera",
                kind=GoalKind.PURCHASE,
                target_cents=200_000,
                current_cents=0,
                priority=2,
                deadline=date(2027, 11, 20),  # 30 paychecks from Oct 2, 2026
                **owner,
            )
        )


@pytest.fixture
def world(income_sources: Fake, bills: Fake, essentials: Fake, debts: Fake, goals: Fake) -> World:
    return World(ADA, income_sources, bills, essentials, debts, goals)


def funded(details: Any) -> dict[str, int]:
    return {line.row.name: line.row.funded_cents for line in details.allocations}


# --- generating ----------------------------------------------------------------


def test_the_worked_example_is_planned_and_stored_as_a_draft(
    plan_service: PlanService,
    world: World,
    plans: Fake,
    paychecks: Fake,
    user_lock: Fake,
    transaction: Fake,
) -> None:
    details, created = plan_service.generate(ADA, world.job.id, PAYDAY)

    assert created
    assert funded(details) == {
        "Rent": 40_000,
        "Groceries": 20_000,
        "Car loan": 7_500,
        "Camera": 6_667,
    }
    plan = details.plan
    assert plan.safe_to_spend_cents == 75_833
    assert (plan.version, plan.status, plan.committed_at) == (1, PlanStatus.DRAFT, None)
    assert (plan.user_id, plan.engine_version) == (ADA.id, ENGINE_VERSION)
    assert len(plan.input_hash) == 64
    assert (plan.as_of, plan.next_pay_date) == (date(2026, 10, 7), date(2026, 10, 16))
    assert (plan.paycheck_amount_cents, plan.available_balance_cents) == (150_000, 0)
    assert (plan.reserve_deficit_cents, plan.balance_as_of) == (0, None)

    # The paycheck was created on first use, and the plan is stored with its lines.
    (paycheck,) = paychecks.rows.values()
    assert details.paycheck is paycheck and plan.paycheck_id == paycheck.id
    assert (paycheck.income_source_id, paycheck.pay_date) == (world.job.id, PAYDAY)
    assert plans.rows == {plan.id: plan}
    assert user_lock.locked == [ADA.id]
    assert transaction.commits == 1


def test_each_line_records_its_target_and_the_facts_behind_it(
    plan_service: PlanService, world: World
) -> None:
    details, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    rent, groceries, car, camera = (line.row for line in details.allocations)

    assert [line.row.position for line in details.allocations] == [0, 1, 2, 3]
    assert {line.row.plan_id for line in details.allocations} == {details.plan.id}

    assert (rent.tier, rent.reason, rent.bill_id) == (Tier.BILL, Reason.BILL_DUE, world.rent.id)
    assert (rent.requested_cents, rent.total_cents, rent.set_aside_cents) == (40_000, 80_000, 0)
    assert (rent.due_date, rent.paychecks) == (date(2026, 10, 20), 2)
    assert (rent.essential_expense_id, rent.debt_id, rent.goal_id) == (None, None, None)

    assert (groceries.tier, groceries.reason) == (Tier.ESSENTIAL, Reason.ESSENTIAL)
    assert groceries.essential_expense_id == world.groceries.id
    assert (groceries.days_covered, groceries.days_in_period) == (14, 14)

    assert (car.tier, car.reason, car.debt_id) == (
        Tier.DEBT_MINIMUM,
        Reason.DEBT_MINIMUM,
        world.car.id,
    )
    assert (car.total_cents, car.due_date, car.paychecks) == (15_000, date(2026, 10, 20), 2)

    assert (camera.tier, camera.reason, camera.goal_id) == (
        Tier.GOAL,
        Reason.GOAL_DEADLINE,
        world.camera.id,
    )
    assert (camera.total_cents, camera.due_date, camera.paychecks) == (
        200_000,
        date(2027, 11, 20),
        30,
    )

    assert [line.target_id for line in details.allocations] == [
        world.rent.id,
        world.groceries.id,
        world.car.id,
        world.camera.id,
    ]


def test_every_number_comes_with_its_explanation(plan_service: PlanService, world: World) -> None:
    details, _ = plan_service.generate(ADA, world.job.id, PAYDAY)

    assert [line.explanation for line in details.allocations] == [
        "We reserved $400 toward Rent because the $800 bill is due Oct 20 and is split "
        "across the 2 paychecks before then.",
        "We set aside $200 for Groceries to cover this pay period.",
        "We reserved $75 toward Car loan because the $150 minimum payment is due Oct 20 "
        "and is split across the 2 paychecks before then.",
        "We put $66.67 toward Camera because its $2,000 is needed by Nov 20, 2027, "
        "split across the 30 paychecks before then.",
    ]
    assert details.summary == "Safe to Spend is $758.33: what's left after everything above."

    (projection,) = details.projections
    assert (projection.row.goal_id, projection.row.name) == (world.camera.id, "Camera")
    assert (projection.row.contribution_cents, projection.row.still_needed_cents) == (
        6_667,
        193_333,
    )
    assert projection.row.status is GoalStatus.ON_TRACK
    assert projection.row.projected_date == date(2027, 11, 12)
    assert projection.suggested_deadline is None
    assert projection.explanation == (
        "At $66.67 a paycheck, Camera will be reached by Nov 12, 2027, "
        "ahead of its deadline of Nov 20, 2027."
    )


def test_planning_again_with_nothing_changed_returns_the_same_draft(
    plan_service: PlanService, world: World, plans: Fake, paychecks: Fake
) -> None:
    first, _ = plan_service.generate(ADA, world.job.id, PAYDAY)

    again, created = plan_service.generate(ADA, world.job.id, PAYDAY)

    assert not created
    assert again.plan is first.plan
    assert funded(again) == funded(first)
    assert len(plans.rows) == 1 and len(paychecks.rows) == 1


def test_a_change_makes_a_new_version_and_supersedes_the_old_draft(
    plan_service: PlanService, world: World, plans: Fake
) -> None:
    first, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    world.rent.amount_cents = 90_000

    second, created = plan_service.generate(ADA, world.job.id, PAYDAY)

    assert created
    assert (second.plan.version, second.plan.status) == (2, PlanStatus.DRAFT)
    assert first.plan.status is PlanStatus.SUPERSEDED
    assert second.plan.input_hash != first.plan.input_hash
    assert funded(second)["Rent"] == 45_000
    assert len(plans.rows) == 2
    # The first plan still reads as it was made.
    assert funded(plan_service.get(ADA, first.plan.id))["Rent"] == 40_000

    world.rent.amount_cents = 100_000
    third, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    assert (third.plan.version, second.plan.status) == (3, PlanStatus.SUPERSEDED)


def test_the_actual_amount_is_planned_once_it_is_recorded(
    plan_service: PlanService, world: World, paychecks: Fake
) -> None:
    expected, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    (paycheck,) = paychecks.rows.values()
    paycheck.actual_amount_cents = 140_000

    actual, created = plan_service.generate(ADA, world.job.id, PAYDAY)

    assert created and actual.plan.version == 2
    assert actual.plan.paycheck_amount_cents == 140_000
    assert actual.plan.safe_to_spend_cents == expected.plan.safe_to_spend_cents - 10_000


def test_an_unplanned_paycheck_follows_its_sources_expected_amount(
    plan_service: PlanService, world: World, paychecks: Fake
) -> None:
    plan_service.generate(ADA, world.job.id, PAYDAY)
    world.job.expected_amount_cents = 160_000  # a raise

    details, created = plan_service.generate(ADA, world.job.id, PAYDAY)

    (paycheck,) = paychecks.rows.values()
    assert created and paycheck.expected_amount_cents == 160_000
    assert details.plan.paycheck_amount_cents == 160_000


def test_the_latest_balance_and_the_reserves_decide_what_can_be_planned(
    plan_service: PlanService, world: World, snapshots: Fake, reserves: Fake
) -> None:
    old, new = datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)
    snapshots.add(BalanceSnapshot(user_id=ADA.id, amount_cents=999_999, as_of=old))
    snapshots.add(BalanceSnapshot(user_id=ADA.id, amount_cents=50_000, as_of=new))
    snapshots.add(BalanceSnapshot(user_id=BOB.id, amount_cents=777_777, as_of=new))
    reserves.add(
        Reserve(
            id=uuid.uuid4(),
            user_id=ADA.id,
            kind=ReserveKind.BILL,
            bill_id=world.rent.id,
            amount_cents=30_000,
        )
    )

    details, _ = plan_service.generate(ADA, world.job.id, PAYDAY)

    plan = details.plan
    assert (plan.available_balance_cents, plan.balance_as_of) == (50_000, new)
    # $300 of rent is already set aside, so each of the 2 paychecks owes $250.
    rent = details.allocations[0]
    assert (rent.row.set_aside_cents, rent.row.funded_cents) == (30_000, 25_000)
    assert "with $300 already set aside" in rent.explanation
    # $500 on hand + $1,500 - $300 reserved - (250 + 200 + 75 + 66.67) planned.
    assert plan.safe_to_spend_cents == 50_000 + 150_000 - 30_000 - 59_167


def test_as_of_is_today_where_the_user_lives(
    plan_service: PlanService, world: World, clock: Fake
) -> None:
    clock.now = datetime(2026, 10, 8, 3, 0, tzinfo=UTC)  # still Oct 7 in New York
    new_yorker = User(
        id=ADA.id, email=ADA.email, timezone="America/New_York", no_deadline_goal_share_bps=2000
    )
    in_new_york, _ = plan_service.generate(new_yorker, world.job.id, PAYDAY)
    assert in_new_york.plan.as_of == date(2026, 10, 7)

    in_utc, created = plan_service.generate(ADA, world.job.id, PAYDAY)
    # A different day is a different input, so this is a new version.
    assert created and in_utc.plan.as_of == date(2026, 10, 8)


def test_an_archived_source_no_longer_counts_toward_the_timeline(
    plan_service: PlanService, world: World, income_sources: Fake
) -> None:
    weekly = income_sources.add(
        IncomeSource(
            id=uuid.uuid4(),
            user_id=ADA.id,
            name="Weekend job",
            expected_amount_cents=20_000,
            pay_frequency=PayFrequency.MONTHLY,
            day_of_month=9,
        )
    )
    with_both, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    assert with_both.plan.next_pay_date == date(2026, 10, 9)

    weekly.archived_at = datetime(2026, 10, 6, tzinfo=UTC)
    alone, created = plan_service.generate(ADA, world.job.id, PAYDAY)

    assert created and alone.plan.next_pay_date == date(2026, 10, 16)
    with pytest.raises(NotFoundError):
        plan_service.generate(ADA, weekly.id, date(2026, 10, 9))


def test_a_paycheck_too_small_says_what_is_short(
    plan_service: PlanService, world: World, paychecks: Fake
) -> None:
    plan_service.generate(ADA, world.job.id, PAYDAY)
    next(iter(paychecks.rows.values())).actual_amount_cents = 30_000

    details, _ = plan_service.generate(ADA, world.job.id, PAYDAY)

    assert funded(details) == {"Rent": 30_000, "Groceries": 0, "Car loan": 0, "Camera": 0}
    assert details.plan.safe_to_spend_cents == 0
    assert details.allocations[0].explanation == (
        "Rent needs $400 from this paycheck because the $800 bill is due Oct 20 and is split "
        "across the 2 paychecks before then. Only $300 could be covered, so you're $100 short."
    )
    assert details.summary == (
        "Safe to Spend is $0: this paycheck can't cover everything, and 4 items are short. "
        "Bills not fully covered: Rent."
    )
    (projection,) = details.projections
    assert projection.row.status is GoalStatus.BEHIND
    assert projection.explanation == (
        "Nothing went toward Camera this paycheck, so it will miss its deadline of Nov 20, 2027."
    )


def test_more_set_aside_than_on_hand_is_reported_as_a_deficit(
    plan_service: PlanService, world: World, snapshots: Fake, reserves: Fake
) -> None:
    snapshots.add(
        BalanceSnapshot(
            user_id=ADA.id, amount_cents=-20_000, as_of=datetime(2026, 10, 1, tzinfo=UTC)
        )
    )
    reserves.add(
        Reserve(
            id=uuid.uuid4(),
            user_id=ADA.id,
            kind=ReserveKind.GOAL,
            goal_id=world.camera.id,
            amount_cents=150_000,
        )
    )
    details, _ = plan_service.generate(ADA, world.job.id, PAYDAY)

    assert details.plan.reserve_deficit_cents == 20_000
    assert details.plan.safe_to_spend_cents == 0
    assert set(funded(details).values()) == {0}
    assert details.summary.startswith("You've set aside $200 more than you have")


def test_a_user_with_only_income_keeps_the_whole_paycheck(
    plan_service: PlanService, income_sources: Fake
) -> None:
    job = income_sources.add(
        IncomeSource(
            id=uuid.uuid4(),
            user_id=ADA.id,
            name="Day job",
            expected_amount_cents=150_000,
            pay_frequency=PayFrequency.MONTHLY,
            day_of_month=1,
        )
    )
    details, _ = plan_service.generate(ADA, job.id, date(2026, 10, 1))
    assert (details.allocations, details.projections) == ((), ())
    assert details.plan.safe_to_spend_cents == 150_000


# --- what cannot be planned ----------------------------------------------------


def test_a_committed_paycheck_cannot_be_planned_again(
    plan_service: PlanService, world: World, plans: Fake, transaction: Fake
) -> None:
    details, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    details.plan.status = PlanStatus.COMMITTED
    world.rent.amount_cents = 90_000

    with pytest.raises(PaycheckAlreadyCommittedError):
        plan_service.generate(ADA, world.job.id, PAYDAY)

    assert len(plans.rows) == 1
    assert transaction.commits == 1
    # Other paychecks are unaffected.
    later, created = plan_service.generate(ADA, world.job.id, date(2026, 10, 16))
    assert created and later.plan.version == 1


@pytest.mark.parametrize("day", [date(2026, 10, 3), date(2026, 10, 9)])
def test_a_date_that_is_not_a_payday_is_rejected(
    plan_service: PlanService, world: World, plans: Fake, paychecks: Fake, day: date
) -> None:
    with pytest.raises(InvalidInputError, match="is not a payday for Day job"):
        plan_service.generate(ADA, world.job.id, day)
    assert plans.rows == {} and paychecks.rows == {}


def test_unknown_and_other_users_sources_are_not_found(
    plan_service: PlanService, world: World, plans: Fake, transaction: Fake
) -> None:
    for user, source_id in ((ADA, uuid.uuid4()), (BOB, world.job.id)):
        with pytest.raises(NotFoundError):
            plan_service.generate(user, source_id, PAYDAY)
    assert plans.rows == {}
    assert transaction.commits == 0


# --- committing ----------------------------------------------------------------


def reserved(reserves: Fake, user: User = ADA) -> dict[tuple[ReserveKind, uuid.UUID], int]:
    return {
        (row.kind, row.bill_id or row.debt_id or row.goal_id): row.amount_cents
        for row in reserves.list_for(user.id)
    }


def test_committing_turns_what_was_funded_into_reserves(
    plan_service: PlanService,
    world: World,
    reserves: Fake,
    clock: Fake,
    user_lock: Fake,
    transaction: Fake,
) -> None:
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    clock.advance(timedelta(minutes=5))

    committed = plan_service.commit(ADA, draft.plan.id)

    assert committed.plan is draft.plan
    assert (committed.plan.status, committed.plan.committed_at) == (PlanStatus.COMMITTED, clock.now)
    # Bills, debts and goals are set aside; groceries are money to spend, not to hold.
    assert reserved(reserves) == {
        (ReserveKind.BILL, world.rent.id): 40_000,
        (ReserveKind.DEBT, world.car.id): 7_500,
        (ReserveKind.GOAL, world.camera.id): 6_667,
    }
    assert {row.user_id for row in reserves.list_for(ADA.id)} == {ADA.id}
    # The goal's progress grows by what it got; nothing else about the setup changes.
    assert world.camera.current_cents == 6_667
    assert (world.rent.amount_cents, world.car.balance_cents) == (80_000, 900_000)
    assert funded(committed) == funded(draft)
    assert user_lock.locked == [ADA.id, ADA.id]
    assert transaction.commits == 2


def test_committing_adds_to_what_is_already_set_aside(
    plan_service: PlanService, world: World, reserves: Fake
) -> None:
    world.camera.current_cents = 50_000
    reserves.add(
        Reserve(
            id=uuid.uuid4(),
            user_id=ADA.id,
            kind=ReserveKind.BILL,
            bill_id=world.rent.id,
            amount_cents=30_000,
        )
    )
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)

    plan_service.commit(ADA, draft.plan.id)

    assert reserved(reserves)[ReserveKind.BILL, world.rent.id] == 30_000 + 25_000
    camera_share = funded(draft)["Camera"]
    assert world.camera.current_cents == 50_000 + camera_share
    assert len(reserves.rows) == 3


def test_the_emergency_fund_is_reserved_like_any_goal(
    plan_service: PlanService, world: World, goals: Fake, reserves: Fake
) -> None:
    fund = goals.add(
        Goal(
            id=uuid.uuid4(),
            user_id=ADA.id,
            name="Emergency fund",
            kind=GoalKind.EMERGENCY,
            target_cents=50_000,
            current_cents=10_000,
            priority=1,
        )
    )
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    assert funded(draft)["Emergency fund"] == 40_000

    plan_service.commit(ADA, draft.plan.id)

    assert reserved(reserves)[ReserveKind.GOAL, fund.id] == 40_000
    assert fund.current_cents == 50_000


def test_a_line_that_got_nothing_reserves_nothing(
    plan_service: PlanService, world: World, paychecks: Fake, reserves: Fake
) -> None:
    plan_service.generate(ADA, world.job.id, PAYDAY)
    next(iter(paychecks.rows.values())).actual_amount_cents = 30_000
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)

    plan_service.commit(ADA, draft.plan.id)

    assert reserved(reserves) == {(ReserveKind.BILL, world.rent.id): 30_000}
    assert world.camera.current_cents == 0


def test_committing_twice_changes_nothing_the_second_time(
    plan_service: PlanService, world: World, reserves: Fake, clock: Fake, transaction: Fake
) -> None:
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    first = plan_service.commit(ADA, draft.plan.id)
    committed_at = first.plan.committed_at
    clock.advance(timedelta(hours=1))

    again = plan_service.commit(ADA, draft.plan.id)

    assert again == first
    assert again.plan.committed_at == committed_at
    assert reserved(reserves)[ReserveKind.BILL, world.rent.id] == 40_000
    assert world.camera.current_cents == 6_667
    assert transaction.commits == 2


def test_a_draft_can_be_committed_on_a_later_day(
    plan_service: PlanService, world: World, clock: Fake
) -> None:
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    clock.advance(timedelta(days=3))

    committed = plan_service.commit(ADA, draft.plan.id)

    # Still the plan for Oct 7: only a change in the data makes a draft out of date.
    assert committed.plan.status is PlanStatus.COMMITTED
    assert committed.plan.as_of == date(2026, 10, 7)


def change_rent(world: World, **_: Any) -> None:
    world.rent.amount_cents = 90_000


def rename_goal(world: World, **_: Any) -> None:
    world.camera.name = "Lens"


def delete_debt(world: World, debts: Fake, **_: Any) -> None:
    debts.delete(world.car)


def add_bill(world: World, bills: Fake, **_: Any) -> None:
    bills.add(
        Bill(
            id=uuid.uuid4(),
            user_id=ADA.id,
            name="Phone",
            amount_cents=6_000,
            priority=2,
            first_due_date=date(2026, 10, 25),
            repeat_every_months=1,
        )
    )


def enter_balance(snapshots: Fake, **_: Any) -> None:
    snapshots.add(
        BalanceSnapshot(
            user_id=ADA.id, amount_cents=12_345, as_of=datetime(2026, 10, 7, tzinfo=UTC)
        )
    )


def record_actual(paychecks: Fake, **_: Any) -> None:
    next(iter(paychecks.rows.values())).actual_amount_cents = 149_000


def get_a_raise(world: World, **_: Any) -> None:
    world.job.expected_amount_cents = 160_000


def reserve_elsewhere(world: World, reserves: Fake, **_: Any) -> None:
    reserves.add(
        Reserve(
            id=uuid.uuid4(),
            user_id=ADA.id,
            kind=ReserveKind.DEBT,
            debt_id=world.car.id,
            amount_cents=1,
        )
    )


@pytest.mark.parametrize(
    "change",
    [
        change_rent,
        rename_goal,
        delete_debt,
        add_bill,
        enter_balance,
        record_actual,
        get_a_raise,
        reserve_elsewhere,
    ],
)
def test_a_draft_is_out_of_date_once_anything_it_was_built_from_changes(
    plan_service: PlanService,
    world: World,
    bills: Fake,
    debts: Fake,
    snapshots: Fake,
    paychecks: Fake,
    reserves: Fake,
    transaction: Fake,
    change: Any,
) -> None:
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    change(
        world=world,
        bills=bills,
        debts=debts,
        snapshots=snapshots,
        paychecks=paychecks,
        reserves=reserves,
    )
    before = reserved(reserves)

    with pytest.raises(PlanOutOfDateError):
        plan_service.commit(ADA, draft.plan.id)

    assert draft.plan.status is PlanStatus.DRAFT and draft.plan.committed_at is None
    assert reserved(reserves) == before
    assert world.camera.current_cents == 0
    assert transaction.commits == 1
    # Generating again gives a draft that can be committed.
    fresh, created = plan_service.generate(ADA, world.job.id, PAYDAY)
    assert created
    assert plan_service.commit(ADA, fresh.plan.id).plan.status is PlanStatus.COMMITTED


def test_changed_settings_make_a_draft_out_of_date(plan_service: PlanService, world: World) -> None:
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    saver = User(id=ADA.id, email=ADA.email, timezone="UTC", no_deadline_goal_share_bps=5000)
    with pytest.raises(PlanOutOfDateError):
        plan_service.commit(saver, draft.plan.id)


def test_committing_one_paycheck_makes_a_draft_for_another_out_of_date(
    plan_service: PlanService, world: World, reserves: Fake
) -> None:
    first, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    second, _ = plan_service.generate(ADA, world.job.id, date(2026, 10, 16))
    plan_service.commit(ADA, first.plan.id)

    # The second draft was made before $400 of rent was set aside.
    with pytest.raises(PlanOutOfDateError):
        plan_service.commit(ADA, second.plan.id)

    replanned, _ = plan_service.generate(ADA, world.job.id, date(2026, 10, 16))
    rent = replanned.allocations[0]
    assert (rent.row.set_aside_cents, rent.row.funded_cents) == (40_000, 40_000)
    plan_service.commit(ADA, replanned.plan.id)
    assert reserved(reserves)[ReserveKind.BILL, world.rent.id] == 80_000
    assert world.camera.current_cents == 6_667 + funded(replanned)["Camera"]


def test_a_superseded_draft_cannot_be_committed(
    plan_service: PlanService, world: World, reserves: Fake
) -> None:
    old, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    world.rent.amount_cents = 90_000
    plan_service.generate(ADA, world.job.id, PAYDAY)

    with pytest.raises(PlanSupersededError):
        plan_service.commit(ADA, old.plan.id)
    assert reserves.rows == {}


def test_a_draft_for_an_archived_source_is_out_of_date(
    plan_service: PlanService, world: World, reserves: Fake
) -> None:
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    world.job.archived_at = datetime(2026, 10, 7, tzinfo=UTC)

    with pytest.raises(PlanOutOfDateError):
        plan_service.commit(ADA, draft.plan.id)
    assert reserves.rows == {}


def test_a_paycheck_never_gets_a_second_committed_plan(
    plan_service: PlanService, world: World, plans: Fake, reserves: Fake
) -> None:
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    plan_service.commit(ADA, draft.plan.id)
    # A second draft for the same paycheck cannot be made through the service, so
    # this one is put in the store directly, as if it had slipped through.
    stray = PaycheckPlan(
        id=uuid.uuid4(),
        user_id=ADA.id,
        paycheck_id=draft.plan.paycheck_id,
        version=2,
        status=PlanStatus.DRAFT,
        input_hash=draft.plan.input_hash,
        as_of=draft.plan.as_of,
    )
    plans.add_plan(stray, [], [])

    with pytest.raises(PaycheckAlreadyCommittedError):
        plan_service.commit(ADA, stray.id)

    assert stray.status is PlanStatus.DRAFT
    assert reserved(reserves)[ReserveKind.BILL, world.rent.id] == 40_000


def test_commit_treats_another_users_plan_as_missing(
    plan_service: PlanService, world: World, reserves: Fake, transaction: Fake
) -> None:
    draft, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    with pytest.raises(NotFoundError):
        plan_service.commit(BOB, draft.plan.id)
    with pytest.raises(NotFoundError):
        plan_service.commit(ADA, uuid.uuid4())
    assert draft.plan.status is PlanStatus.DRAFT
    assert reserves.rows == {}
    assert transaction.commits == 1


# --- reading -------------------------------------------------------------------


def test_get_returns_the_plan_as_it_was_generated(plan_service: PlanService, world: World) -> None:
    made, _ = plan_service.generate(ADA, world.job.id, PAYDAY)

    read = plan_service.get(ADA, made.plan.id)

    assert read == made
    assert (read.paycheck.pay_date, read.source) == (PAYDAY, world.job)


def test_get_treats_another_users_plan_as_missing(plan_service: PlanService, world: World) -> None:
    made, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    with pytest.raises(NotFoundError):
        plan_service.get(BOB, made.plan.id)
    with pytest.raises(NotFoundError):
        plan_service.get(ADA, uuid.uuid4())


def test_an_old_plan_still_explains_itself_after_its_targets_are_gone(
    plan_service: PlanService, world: World, plans: Fake
) -> None:
    made, _ = plan_service.generate(ADA, world.job.id, PAYDAY)
    # What the database does when a bill and a goal are deleted, and a source archived.
    allocations, projections = plans.lines[made.plan.id]
    allocations[0].bill_id = None
    allocations[3].goal_id = None
    projections[0].goal_id = None
    world.job.archived_at = datetime(2026, 11, 1, tzinfo=UTC)

    read = plan_service.get(ADA, made.plan.id)

    assert [line.target_id for line in read.allocations] == [
        None,
        world.groceries.id,
        world.car.id,
        None,
    ]
    assert [line.explanation for line in read.allocations] == [
        line.explanation for line in made.allocations
    ]
    assert read.projections[0].explanation == made.projections[0].explanation
    assert read.summary == made.summary
    assert read.source is world.job
