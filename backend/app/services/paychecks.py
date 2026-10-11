"""Paychecks: the timeline of paydays, and what actually arrived (ADR 0005, ADR 0011).

Paydays come from the engine's schedules, so the app never works them out. A
paycheck is identified by its income source and pay date; its row is created
the first time something is recorded or planned for it.
"""

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import nextpay_engine as engine
from app.core.clock import Clock, local_date
from app.core.errors import InvalidInputError, NotFoundError
from app.core.limits import MAX_TIMELINE_DAYS, TIMELINE_DAYS_AHEAD, TIMELINE_DAYS_BACK
from app.models import IncomeSource, Paycheck, PaycheckPlan, User
from app.services.engine_mapping import to_engine_income_source, to_engine_paycheck, validated
from app.services.protocols import Transaction, UserLock


class PaycheckSources(Protocol):
    """Income sources, as paychecks need them. ``get`` and ``list_for`` skip archived ones."""

    def get(self, user_id: uuid.UUID, row_id: uuid.UUID) -> IncomeSource | None: ...
    def list_for(self, user_id: uuid.UUID) -> Sequence[IncomeSource]: ...
    def list_including_archived(self, user_id: uuid.UUID) -> Sequence[IncomeSource]: ...


class PaycheckStore(Protocol):
    def find(self, user_id: uuid.UUID, source_id: uuid.UUID, pay_date: date) -> Paycheck | None: ...
    def list_between(self, user_id: uuid.UUID, start: date, end: date) -> Sequence[Paycheck]: ...
    def add(self, row: Paycheck) -> Paycheck: ...


class CurrentPlans(Protocol):
    def current_for_paychecks(
        self, user_id: uuid.UUID, paycheck_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, PaycheckPlan]: ...


@dataclass(frozen=True, slots=True)
class PaycheckEntry:
    """One payday of one income source: expected by its schedule, recorded, or both."""

    source: IncomeSource
    pay_date: date
    expected_amount_cents: int
    # None: on the schedule, but nothing has been recorded or planned for it yet.
    paycheck: Paycheck | None
    # The paycheck's plan that counts: committed, or else its current draft.
    plan: PaycheckPlan | None = None


def is_payday(source: IncomeSource, day: date) -> bool:
    """Whether ``source``'s schedule pays on ``day`` (weekend paydays move to Friday)."""
    return to_engine_income_source(source).schedule.dates_between(day, day) == (day,)


def find_or_create_paycheck(
    paychecks: PaycheckStore, source: IncomeSource, pay_date: date
) -> Paycheck:
    """``source``'s paycheck on ``pay_date``, created if this is the first use of it.

    Raises ``InvalidInputError`` if there is none and ``pay_date`` is not a payday.
    The caller must hold the user's lock, so two requests cannot both create it.
    """
    paycheck = paychecks.find(source.user_id, source.id, pay_date)
    if paycheck is not None:
        return paycheck
    if not is_payday(source, pay_date):
        raise InvalidInputError(f"{pay_date.isoformat()} is not a payday for {source.name}.")
    return paychecks.add(
        Paycheck(
            id=uuid.uuid4(),
            user_id=source.user_id,
            income_source_id=source.id,
            pay_date=pay_date,
            expected_amount_cents=source.expected_amount_cents,
        )
    )


class PaycheckService:
    def __init__(
        self,
        *,
        users: UserLock,
        income_sources: PaycheckSources,
        paychecks: PaycheckStore,
        plans: CurrentPlans,
        transaction: Transaction,
        clock: Clock,
    ) -> None:
        self._users = users
        self._income_sources = income_sources
        self._paychecks = paychecks
        self._plans = plans
        self._transaction = transaction
        self._clock = clock

    def timeline(
        self, user: User, start: date | None = None, end: date | None = None
    ) -> list[PaycheckEntry]:
        """Every payday from ``start`` to ``end``, by date.

        Defaults to a week back from today (in the user's time zone) and about two
        months ahead. Paydays come from the active sources' schedules; a recorded
        paycheck is shown even if its source was archived or rescheduled since.
        Raises ``InvalidInputError`` for a range that is backwards or too long.
        """
        if start is None:
            start = local_date(self._clock(), user.timezone) - timedelta(days=TIMELINE_DAYS_BACK)
        if end is None:
            end = start + timedelta(days=TIMELINE_DAYS_BACK + TIMELINE_DAYS_AHEAD)
        if not 0 <= (end - start).days <= MAX_TIMELINE_DAYS:
            raise InvalidInputError(
                f"Ask for a range of up to {MAX_TIMELINE_DAYS} days, with start on or before end."
            )

        sources = {source.id: source for source in self._income_sources.list_for(user.id)}
        rows = self._paychecks.list_between(user.id, start, end)
        recorded = {(row.income_source_id, row.pay_date): row for row in rows}
        plans = self._plans.current_for_paychecks(user.id, [row.id for row in rows])
        scheduled = engine.paycheck_timeline(
            [to_engine_income_source(source) for source in sources.values()], start, end
        )
        entries: list[PaycheckEntry] = []
        for expected in scheduled:
            source = sources[uuid.UUID(expected.source_id)]
            row = recorded.pop((source.id, expected.pay_date), None)
            if row is None:
                entry = PaycheckEntry(source, expected.pay_date, source.expected_amount_cents, None)
            else:
                entry = _entry(source, row, plans)
            entries.append(entry)
        if recorded:
            # History the schedules no longer produce: an archived or rescheduled source.
            everyone = {s.id: s for s in self._income_sources.list_including_archived(user.id)}
            entries.extend(
                _entry(everyone[row.income_source_id], row, plans) for row in recorded.values()
            )
        return sorted(entries, key=lambda entry: (entry.pay_date, str(entry.source.id)))

    def record_actual(
        self,
        user: User,
        source_id: uuid.UUID,
        pay_date: date,
        actual_amount_cents: int | None,
    ) -> PaycheckEntry:
        """Record what ``source_id`` actually paid on ``pay_date``; None clears it.

        A draft plan for this paycheck becomes out of date; a committed one is
        final and is not changed (ADR 0011). Raises ``NotFoundError`` for an
        unknown or archived source, ``InvalidInputError`` for a date that is not a
        payday or an amount below zero.
        """
        self._users.lock(user.id)
        source = self._income_sources.get(user.id, source_id)
        if source is None:
            raise NotFoundError()
        # Check the amount on a copy first, so a rejected one stores nothing.
        validated(
            Paycheck(
                income_source_id=source.id,
                pay_date=pay_date,
                expected_amount_cents=source.expected_amount_cents,
                actual_amount_cents=actual_amount_cents,
            ),
            to_engine_paycheck,
        )
        paycheck = find_or_create_paycheck(self._paychecks, source, pay_date)
        paycheck.actual_amount_cents = actual_amount_cents
        self._transaction.commit()
        return _entry(source, paycheck, self._plans.current_for_paychecks(user.id, [paycheck.id]))


def _entry(
    source: IncomeSource, paycheck: Paycheck, plans: dict[uuid.UUID, PaycheckPlan]
) -> PaycheckEntry:
    return PaycheckEntry(
        source,
        paycheck.pay_date,
        paycheck.expected_amount_cents,
        paycheck,
        plans.get(paycheck.id),
    )
