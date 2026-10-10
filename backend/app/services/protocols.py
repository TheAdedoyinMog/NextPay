"""What services need from storage, as Protocols.

Services depend on these, never on a repository class, so unit tests can pass
in-memory fakes and the API passes the real repositories.
"""

import uuid
from collections.abc import Sequence
from typing import Protocol


class Transaction(Protocol):
    """What a service needs to end a unit of work. A SQLAlchemy Session is one."""

    def commit(self) -> None: ...


class OwnedStore[M](Protocol):
    """Rows that belong to one user. Every read is scoped by ``user_id``."""

    def get(self, user_id: uuid.UUID, row_id: uuid.UUID) -> M | None: ...
    def list_for(self, user_id: uuid.UUID) -> Sequence[M]: ...
    def add(self, row: M) -> M: ...
    def delete(self, row: M) -> None: ...
