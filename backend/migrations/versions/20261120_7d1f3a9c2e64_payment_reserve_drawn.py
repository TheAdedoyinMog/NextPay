"""what each payment drew from its reserve

Revision ID: 7d1f3a9c2e64
Revises: 4b7e2c9a1d53
Create Date: 2026-11-20 18:00:00.000000+00:00

Milestone 3D (ADR 0016). ``reserve_drawn_cents`` on ``bill_payments`` and
``debt_payments`` is how much of the payment came out of what was set aside for
it; the rest came out of Safe to Spend. Existing payments are treated as fully
covered, so no Safe to Spend changes when this runs. Like every migration, this
file is frozen: it never imports the app.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d1f3a9c2e64"
down_revision: str | None = "4b7e2c9a1d53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("bill_payments", "debt_payments")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("reserve_drawn_cents", sa.BigInteger(), nullable=True))
        op.execute(f"UPDATE {table} SET reserve_drawn_cents = amount_cents")
        op.alter_column(table, "reserve_drawn_cents", nullable=False)
        op.create_check_constraint(
            op.f(f"ck_{table}_reserve_drawn_range"),
            table,
            "reserve_drawn_cents >= 0 AND reserve_drawn_cents <= amount_cents",
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(op.f(f"ck_{table}_reserve_drawn_range"), table, type_="check")
        op.drop_column(table, "reserve_drawn_cents")
