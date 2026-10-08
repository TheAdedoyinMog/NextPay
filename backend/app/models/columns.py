"""Column building blocks shared by the models.

Conventions (see the Database Design in docs/design):

- Primary keys are UUIDs, generated in Python.
- Money is integer cents in BIGINT columns named ``*_cents`` (ADR 0001).
- Every user-owned table has ``user_id`` and ``UNIQUE (user_id, id)``. A row that
  points at another user-owned row does it through ``tenant_fk``, a composite
  foreign key on ``(user_id, <x>_id)``, so the database itself refuses to link
  one user's data to another's.
- Enums are VARCHAR with a CHECK constraint, storing the enum's values (the
  engine's stable strings), not native PostgreSQL enums, which are hard to alter.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

Cents = Annotated[int, mapped_column(BigInteger)]
NullableCents = Annotated[int | None, mapped_column(BigInteger)]

# Mixin columns sort first (id, user_id) or last (timestamps); the rest keep
# their declared order (sort_order 0).

# Room for future values without widening the column.
_ENUM_LENGTH = 32


def str_enum[E: StrEnum](enum_class: type[E], name: str) -> Enum:
    """A VARCHAR column type holding ``enum_class`` values, with a CHECK constraint."""
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=_ENUM_LENGTH,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


def tenant_fk(column: str, table: str, *, ondelete: str) -> ForeignKeyConstraint:
    """``(user_id, column)`` references ``table (user_id, id)``.

    For ``SET NULL``, only ``column`` is cleared (PostgreSQL 15+), never ``user_id``.
    """
    if ondelete == "SET NULL":
        ondelete = f"SET NULL ({column})"
    return ForeignKeyConstraint(
        ["user_id", column], [f"{table}.user_id", f"{table}.id"], ondelete=ondelete
    )


def owned_by_user() -> UniqueConstraint:
    """``UNIQUE (user_id, id)``: the target of ``tenant_fk``, and the user_id index."""
    return UniqueConstraint("user_id", "id")


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, sort_order=-2)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), sort_order=1
    )


class TimestampsMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), sort_order=2
    )


class UserOwnedMixin(IdMixin):
    """A row that belongs to one user and is deleted with them."""

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), sort_order=-1
    )
