"""PaycheckService rules, with in-memory fakes (see conftest.py).

The fake clock starts at noon UTC on Wednesday, Oct 7, 2026.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.core.errors import InvalidInputError, NotFoundError
from app.models import IncomeSource, Paycheck, PayFrequency, User
from app.services.paychecks import PaycheckService, is_payday

ADA = User(id=uuid.uuid4(), email="ada@example.com", timezone="UTC")
BOB = User(id=uuid.uuid4(), email="bob@example.com", timezone="UTC")

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


def add_source(income_sources: Fake, user: User = ADA, **fields: Any) -> IncomeSource:
    """A biweekly job paying on Fridays from Oct 2, unless ``fields`` say otherwise."""
    defaults: dict[str, Any] = {
        "name": "Day job",
        "expected_amount_cents": 150_000,
        "pay_frequency": PayFrequency.BIWEEKLY,
        "anchor_date": date(2026, 10, 2),
    }
    source = IncomeSource(id=uuid.uuid4(), user_id=user.id, **{**defaults, **fields})
    income_sources.add(source)
    return source


def monthly(income_sources: Fake, day: int, **fields: Any) -> IncomeSource:
    return add_source(
        income_sources,
        pay_frequency=PayFrequency.MONTHLY,
        anchor_date=None,
        day_of_month=day,
        **fields,
    )


def days(entries: list[Any]) -> list[date]:
    return [entry.pay_date for entry in entries]


# --- the timeline --------------------------------------------------------------


def test_the_timeline_runs_from_a_week_ago_to_about_two_months_ahead(
    paycheck_service: PaycheckService, income_sources: Fake
) -> None:
    job = add_source(income_sources)

    entries = paycheck_service.timeline(ADA)

    # Sep 30 to Dec 8: the Oct 2 payday was five days ago and is still shown.
    assert days(entries) == [
        date(2026, 10, 2),
        date(2026, 10, 16),
        date(2026, 10, 30),
        date(2026, 11, 13),
        date(2026, 11, 27),
    ]
    assert all(entry.source is job and entry.paycheck is None for entry in entries)
    assert {entry.expected_amount_cents for entry in entries} == {150_000}


def test_today_is_the_users_own_date(
    paycheck_service: PaycheckService, income_sources: Fake, clock: Fake
) -> None:
    add_source(income_sources, pay_frequency=PayFrequency.WEEKLY)
    # 03:00 UTC on Friday Oct 9 is still Thursday Oct 8 in New York.
    clock.now = datetime(2026, 10, 9, 3, 0, tzinfo=UTC)
    new_yorker = User(id=ADA.id, email=ADA.email, timezone="America/New_York")

    assert days(paycheck_service.timeline(ADA))[0] == date(2026, 10, 2)  # from Oct 2
    assert days(paycheck_service.timeline(new_yorker))[0] == date(2026, 10, 2)  # from Oct 1
    clock.now = datetime(2026, 10, 10, 3, 0, tzinfo=UTC)
    assert days(paycheck_service.timeline(ADA))[0] == date(2026, 10, 9)  # from Oct 3
    assert days(paycheck_service.timeline(new_yorker))[0] == date(2026, 10, 2)  # from Oct 2


def test_an_explicit_range_is_inclusive(
    paycheck_service: PaycheckService, income_sources: Fake
) -> None:
    add_source(income_sources)
    between = paycheck_service.timeline(ADA, date(2026, 10, 16), date(2026, 10, 30))
    assert days(between) == [date(2026, 10, 16), date(2026, 10, 30)]
    assert days(paycheck_service.timeline(ADA, date(2026, 10, 16), date(2026, 10, 16))) == [
        date(2026, 10, 16)
    ]
    assert paycheck_service.timeline(ADA, date(2026, 10, 17), date(2026, 10, 29)) == []


def test_a_start_alone_looks_the_usual_distance_ahead(
    paycheck_service: PaycheckService, income_sources: Fake
) -> None:
    add_source(income_sources)
    # 69 days from Jan 1, 2027: to Mar 11.
    entries = paycheck_service.timeline(ADA, date(2027, 1, 1))
    assert days(entries)[0] == date(2027, 1, 8) and days(entries)[-1] == date(2027, 3, 5)


def test_two_jobs_share_one_timeline(
    paycheck_service: PaycheckService, income_sources: Fake
) -> None:
    job = add_source(income_sources)
    weekend = monthly(income_sources, 16, name="Weekend job", expected_amount_cents=30_000)

    entries = paycheck_service.timeline(ADA, date(2026, 10, 1), date(2026, 10, 31))

    assert days(entries) == [
        date(2026, 10, 2),
        date(2026, 10, 16),
        date(2026, 10, 16),
        date(2026, 10, 30),
    ]
    same_day = [entry.source for entry in entries if entry.pay_date == date(2026, 10, 16)]
    # Two paychecks on one day come in a fixed order: by source id.
    assert same_day == sorted([job, weekend], key=lambda source: str(source.id))


def test_a_weekend_payday_moves_to_friday(
    paycheck_service: PaycheckService, income_sources: Fake
) -> None:
    source = monthly(income_sources, 3)  # Oct 3, 2026 is a Saturday
    entries = paycheck_service.timeline(ADA, date(2026, 10, 1), date(2026, 10, 31))
    assert days(entries) == [date(2026, 10, 2)]
    assert is_payday(source, date(2026, 10, 2))
    assert not is_payday(source, date(2026, 10, 3))


def test_recorded_paychecks_appear_with_what_was_recorded(
    paycheck_service: PaycheckService, income_sources: Fake, paychecks: Fake
) -> None:
    job = add_source(income_sources)
    row = paychecks.add(
        Paycheck(
            id=uuid.uuid4(),
            user_id=ADA.id,
            income_source_id=job.id,
            pay_date=date(2026, 10, 2),
            expected_amount_cents=140_000,  # the source paid less back then
            actual_amount_cents=139_500,
        )
    )

    first, second = paycheck_service.timeline(ADA, date(2026, 10, 1), date(2026, 10, 20))

    assert (first.paycheck, first.expected_amount_cents) == (row, 140_000)
    assert (second.paycheck, second.expected_amount_cents) == (None, 150_000)


def test_history_outlives_archiving_and_rescheduling(
    paycheck_service: PaycheckService, income_sources: Fake, paychecks: Fake
) -> None:
    old_job = add_source(income_sources, name="Old job")
    old_job.archived_at = datetime(2026, 10, 5, tzinfo=UTC)
    job = monthly(income_sources, 15)
    for source, day in ((old_job, date(2026, 10, 2)), (job, date(2026, 10, 9))):
        paychecks.add(
            Paycheck(
                id=uuid.uuid4(),
                user_id=ADA.id,
                income_source_id=source.id,
                pay_date=day,  # Oct 9 was a payday before `job` was rescheduled
                expected_amount_cents=150_000,
            )
        )

    entries = paycheck_service.timeline(ADA, date(2026, 10, 1), date(2026, 10, 31))

    # The archived job's recorded paycheck is shown; its later paydays are not.
    assert [(entry.source.name, entry.pay_date) for entry in entries] == [
        ("Old job", date(2026, 10, 2)),
        ("Day job", date(2026, 10, 9)),
        ("Day job", date(2026, 10, 15)),
    ]
    assert [entry.paycheck is not None for entry in entries] == [True, True, False]


def test_the_timeline_is_only_the_users_own(
    paycheck_service: PaycheckService, income_sources: Fake, paychecks: Fake
) -> None:
    bobs = add_source(income_sources, BOB)
    paychecks.add(
        Paycheck(
            id=uuid.uuid4(),
            user_id=BOB.id,
            income_source_id=bobs.id,
            pay_date=date(2026, 10, 2),
            expected_amount_cents=150_000,
        )
    )
    assert paycheck_service.timeline(ADA) == []
    assert len(paycheck_service.timeline(BOB)) == 5


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2026, 10, 2), date(2026, 10, 1)), (date(2026, 1, 1), date(2027, 1, 3))],
)
def test_a_backwards_or_too_long_range_is_rejected(
    paycheck_service: PaycheckService, start: date, end: date
) -> None:
    with pytest.raises(InvalidInputError, match="up to 366 days"):
        paycheck_service.timeline(ADA, start, end)


def test_the_longest_range_is_allowed(
    paycheck_service: PaycheckService, income_sources: Fake
) -> None:
    add_source(income_sources)
    assert len(paycheck_service.timeline(ADA, date(2026, 1, 1), date(2027, 1, 2))) == 26


# --- recording what arrived ----------------------------------------------------


def test_recording_an_amount_creates_the_paycheck_on_first_use(
    paycheck_service: PaycheckService,
    income_sources: Fake,
    paychecks: Fake,
    transaction: Fake,
    user_lock: Fake,
) -> None:
    job = add_source(income_sources)

    entry = paycheck_service.record_actual(ADA, job.id, date(2026, 10, 2), 148_250)

    (row,) = paychecks.rows.values()
    assert entry.paycheck is row and entry.source is job
    assert (row.user_id, row.income_source_id, row.pay_date) == (ADA.id, job.id, date(2026, 10, 2))
    assert (row.expected_amount_cents, row.actual_amount_cents) == (150_000, 148_250)
    assert user_lock.locked == [ADA.id]
    assert transaction.commits == 1


def test_recording_again_changes_the_same_paycheck_and_null_clears_it(
    paycheck_service: PaycheckService, income_sources: Fake, paychecks: Fake
) -> None:
    job = add_source(income_sources)
    paycheck_service.record_actual(ADA, job.id, date(2026, 10, 2), 148_250)

    paycheck_service.record_actual(ADA, job.id, date(2026, 10, 2), 0)  # unpaid leave
    (row,) = paychecks.rows.values()
    assert row.actual_amount_cents == 0

    cleared = paycheck_service.record_actual(ADA, job.id, date(2026, 10, 2), None)
    assert cleared.paycheck is row and row.actual_amount_cents is None
    assert len(paychecks.rows) == 1


def test_a_recorded_paycheck_can_still_be_corrected_after_a_reschedule(
    paycheck_service: PaycheckService, income_sources: Fake, paychecks: Fake
) -> None:
    job = add_source(income_sources)
    paycheck_service.record_actual(ADA, job.id, date(2026, 10, 2), 148_250)
    job.anchor_date = date(2026, 10, 9)  # Oct 2 is no longer on the schedule

    paycheck_service.record_actual(ADA, job.id, date(2026, 10, 2), 149_000)

    (row,) = paychecks.rows.values()
    assert row.actual_amount_cents == 149_000


@pytest.mark.parametrize("day", [date(2026, 10, 3), date(2026, 10, 9), date(2026, 10, 15)])
def test_a_date_that_is_not_a_payday_is_rejected(
    paycheck_service: PaycheckService,
    income_sources: Fake,
    paychecks: Fake,
    transaction: Fake,
    day: date,
) -> None:
    job = add_source(income_sources)
    with pytest.raises(InvalidInputError, match="is not a payday for Day job"):
        paycheck_service.record_actual(ADA, job.id, day, 148_250)
    assert paychecks.rows == {}
    assert transaction.commits == 0


@pytest.mark.parametrize("amount", [-1, True, 1482.5])
def test_an_invalid_amount_stores_nothing(
    paycheck_service: PaycheckService,
    income_sources: Fake,
    paychecks: Fake,
    transaction: Fake,
    amount: Any,
) -> None:
    job = add_source(income_sources)
    with pytest.raises(InvalidInputError):
        paycheck_service.record_actual(ADA, job.id, date(2026, 10, 2), amount)
    assert paychecks.rows == {}
    assert transaction.commits == 0


def test_an_invalid_amount_leaves_a_recorded_paycheck_untouched(
    paycheck_service: PaycheckService, income_sources: Fake, paychecks: Fake
) -> None:
    job = add_source(income_sources)
    paycheck_service.record_actual(ADA, job.id, date(2026, 10, 2), 148_250)
    with pytest.raises(InvalidInputError):
        paycheck_service.record_actual(ADA, job.id, date(2026, 10, 2), -1)
    (row,) = paychecks.rows.values()
    assert row.actual_amount_cents == 148_250


def test_unknown_archived_and_other_users_sources_are_not_found(
    paycheck_service: PaycheckService, income_sources: Fake, paychecks: Fake, transaction: Fake
) -> None:
    bobs = add_source(income_sources, BOB)
    archived = add_source(income_sources, name="Old job")
    archived.archived_at = datetime(2026, 10, 5, tzinfo=UTC)

    for source_id in (uuid.uuid4(), bobs.id, archived.id):
        with pytest.raises(NotFoundError):
            paycheck_service.record_actual(ADA, source_id, date(2026, 10, 2), 148_250)
    assert paychecks.rows == {}
    assert transaction.commits == 0
