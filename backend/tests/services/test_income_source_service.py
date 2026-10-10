"""IncomeSourceService rules, with in-memory fakes (see conftest.py)."""

import uuid
from dataclasses import replace
from datetime import date
from typing import Any

import pytest

import nextpay_engine as engine
from app.core.errors import IncomeSourceInUseError, InvalidInputError, NotFoundError
from app.models import PayFrequency
from app.services.engine_mapping import to_engine_income_source
from app.services.income_sources import IncomeSourceInput, IncomeSourceService

ADA = uuid.uuid4()
BOB = uuid.uuid4()
PAYDAY = date(2026, 10, 2)
JOB = IncomeSourceInput(
    name="Day job",
    expected_amount_cents=150_000,
    pay_frequency=PayFrequency.BIWEEKLY,
    anchor_date=PAYDAY,
)

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


def with_schedule(frequency: PayFrequency, **parameters: Any) -> IncomeSourceInput:
    return IncomeSourceInput("Day job", 150_000, frequency, **parameters)


def test_create_stores_the_source_for_its_user(
    income_source_service: IncomeSourceService, income_sources: Fake, transaction: Fake
) -> None:
    job = income_source_service.create(ADA, JOB)

    assert income_sources.rows == {job.id: job}
    assert (job.user_id, job.name, job.expected_amount_cents) == (ADA, "Day job", 150_000)
    assert (job.pay_frequency, job.anchor_date) == (PayFrequency.BIWEEKLY, PAYDAY)
    assert (job.day_of_month, job.second_day_of_month) == (None, None)
    assert transaction.commits == 1


@pytest.mark.parametrize(
    ("data", "schedule"),
    [
        (with_schedule(PayFrequency.WEEKLY, anchor_date=PAYDAY), engine.Weekly(PAYDAY)),
        (with_schedule(PayFrequency.BIWEEKLY, anchor_date=PAYDAY), engine.Biweekly(PAYDAY)),
        (
            with_schedule(PayFrequency.SEMI_MONTHLY, day_of_month=15, second_day_of_month=31),
            engine.SemiMonthly(15, 31),
        ),
        (with_schedule(PayFrequency.MONTHLY, day_of_month=31), engine.Monthly(31)),
    ],
)
def test_each_frequency_becomes_its_engine_schedule(
    income_source_service: IncomeSourceService,
    data: IncomeSourceInput,
    schedule: engine.PaySchedule,
) -> None:
    source = income_source_service.create(ADA, data)
    assert to_engine_income_source(source).schedule == schedule


@pytest.mark.parametrize(
    "data",
    [
        replace(JOB, name=" "),
        replace(JOB, expected_amount_cents=0),
        replace(JOB, expected_amount_cents=-1),
        replace(JOB, expected_amount_cents=True),
        # Each frequency takes exactly its own parameters.
        with_schedule(PayFrequency.WEEKLY),
        with_schedule(PayFrequency.WEEKLY, anchor_date=PAYDAY, day_of_month=1),
        with_schedule(PayFrequency.BIWEEKLY, day_of_month=15),
        with_schedule(PayFrequency.BIWEEKLY, anchor_date=PAYDAY, second_day_of_month=20),
        with_schedule(PayFrequency.MONTHLY),
        with_schedule(PayFrequency.MONTHLY, day_of_month=15, second_day_of_month=30),
        with_schedule(PayFrequency.MONTHLY, day_of_month=15, anchor_date=PAYDAY),
        with_schedule(PayFrequency.MONTHLY, day_of_month=0),
        with_schedule(PayFrequency.MONTHLY, day_of_month=32),
        with_schedule(PayFrequency.SEMI_MONTHLY, day_of_month=1),
        with_schedule(
            PayFrequency.SEMI_MONTHLY, day_of_month=1, second_day_of_month=15, anchor_date=PAYDAY
        ),
        with_schedule("fortnightly", anchor_date=PAYDAY),  # type: ignore[arg-type]
    ],
)
def test_create_rejects_what_the_engine_would_reject(
    income_source_service: IncomeSourceService,
    income_sources: Fake,
    transaction: Fake,
    data: IncomeSourceInput,
) -> None:
    with pytest.raises(InvalidInputError):
        income_source_service.create(ADA, data)
    assert income_sources.rows == {}
    assert transaction.commits == 0


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (1, 31),  # one day from the 31st to the next 1st
        (15, 15),
        (20, 5),  # out of order
        (10, 16),  # six days apart
        (25, 31),  # three days apart in February
    ],
)
def test_semi_monthly_paydays_too_close_together_are_explained(
    income_source_service: IncomeSourceService, first: int, second: int
) -> None:
    data = with_schedule(PayFrequency.SEMI_MONTHLY, day_of_month=first, second_day_of_month=second)
    with pytest.raises(InvalidInputError, match="at least 7 days apart"):
        income_source_service.create(ADA, data)


def test_list_and_get_show_only_the_users_own(income_source_service: IncomeSourceService) -> None:
    job = income_source_service.create(ADA, JOB)
    income_source_service.create(BOB, replace(JOB, name="Bob's job"))

    assert list(income_source_service.list_for(ADA)) == [job]
    assert income_source_service.get(ADA, job.id) is job
    with pytest.raises(NotFoundError):
        income_source_service.get(BOB, job.id)
    with pytest.raises(NotFoundError):
        income_source_service.get(ADA, uuid.uuid4())


def test_update_replaces_the_whole_schedule(
    income_source_service: IncomeSourceService, transaction: Fake
) -> None:
    job = income_source_service.create(ADA, JOB)
    new = IncomeSourceInput(
        "New job", 210_000, PayFrequency.SEMI_MONTHLY, day_of_month=1, second_day_of_month=15
    )

    updated = income_source_service.update(ADA, job.id, new)

    assert updated is job
    assert (job.name, job.expected_amount_cents) == ("New job", 210_000)
    assert job.pay_frequency is PayFrequency.SEMI_MONTHLY
    # The old schedule's anchor is gone, not left behind.
    assert (job.anchor_date, job.day_of_month, job.second_day_of_month) == (None, 1, 15)
    assert transaction.commits == 2


def test_a_rejected_update_leaves_the_source_untouched(
    income_source_service: IncomeSourceService, transaction: Fake
) -> None:
    job = income_source_service.create(ADA, JOB)
    bad = with_schedule(PayFrequency.SEMI_MONTHLY, day_of_month=1, second_day_of_month=31)
    with pytest.raises(InvalidInputError):
        income_source_service.update(ADA, job.id, bad)
    assert (job.pay_frequency, job.anchor_date) == (PayFrequency.BIWEEKLY, PAYDAY)
    assert transaction.commits == 1


def test_update_and_delete_treat_another_users_source_as_missing(
    income_source_service: IncomeSourceService, income_sources: Fake, transaction: Fake
) -> None:
    job = income_source_service.create(ADA, JOB)
    with pytest.raises(NotFoundError):
        income_source_service.update(BOB, job.id, replace(JOB, name="Mine now"))
    with pytest.raises(NotFoundError):
        income_source_service.delete(BOB, job.id)
    assert income_sources.rows == {job.id: job}
    assert job.name == "Day job"
    assert transaction.commits == 1


def test_delete_removes_a_source_without_paychecks(
    income_source_service: IncomeSourceService, income_sources: Fake, transaction: Fake
) -> None:
    job = income_source_service.create(ADA, JOB)
    income_source_service.delete(ADA, job.id)
    assert income_sources.rows == {}
    assert transaction.commits == 2


def test_a_source_with_paychecks_cannot_be_deleted(
    income_source_service: IncomeSourceService, income_sources: Fake, transaction: Fake
) -> None:
    job = income_source_service.create(ADA, JOB)
    income_sources.with_paychecks.add(job.id)

    with pytest.raises(IncomeSourceInUseError):
        income_source_service.delete(ADA, job.id)

    assert income_sources.rows == {job.id: job}
    assert transaction.commits == 1
