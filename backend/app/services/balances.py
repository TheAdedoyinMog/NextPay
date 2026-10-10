"""Balance snapshots: what the user says they have, each time they say it.

Append-only: a new balance is a new snapshot, never an edit, and the newest
one is the current balance. The server stamps ``as_of`` (ADR 0010).
"""

import uuid
from collections.abc import Sequence
from typing import Protocol

from app.core.clock import Clock
from app.core.errors import InvalidInputError
from app.core.limits import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.models import BalanceSnapshot
from app.services.engine_mapping import to_engine_balance, validated
from app.services.protocols import Transaction


class BalanceSnapshotStore(Protocol):
    def add(self, row: BalanceSnapshot) -> BalanceSnapshot: ...
    def latest(self, user_id: uuid.UUID, limit: int) -> Sequence[BalanceSnapshot]: ...


class BalanceSnapshotService:
    def __init__(
        self, *, snapshots: BalanceSnapshotStore, transaction: Transaction, clock: Clock
    ) -> None:
        self._snapshots = snapshots
        self._transaction = transaction
        self._clock = clock

    def create(self, user_id: uuid.UUID, amount_cents: int) -> BalanceSnapshot:
        """Record the user's balance as of now; negative means overdrawn.

        Raises ``InvalidInputError``.
        """
        snapshot = validated(
            BalanceSnapshot(
                id=uuid.uuid4(), user_id=user_id, amount_cents=amount_cents, as_of=self._clock()
            ),
            to_engine_balance,
        )
        self._snapshots.add(snapshot)
        self._transaction.commit()
        return snapshot

    def list_for(
        self, user_id: uuid.UUID, limit: int = DEFAULT_PAGE_SIZE
    ) -> Sequence[BalanceSnapshot]:
        """Up to ``limit`` snapshots, newest first. Raises ``InvalidInputError``."""
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise InvalidInputError(f"Ask for between 1 and {MAX_PAGE_SIZE} balances at a time.")
        return self._snapshots.latest(user_id, limit)
