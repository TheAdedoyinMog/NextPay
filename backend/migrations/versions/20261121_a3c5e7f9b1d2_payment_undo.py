"""undoing a payment

Revision ID: a3c5e7f9b1d2
Revises: 7d1f3a9c2e64
Create Date: 2026-11-21 18:00:00.000000+00:00

Milestone 3D part 2 (ADR 0017). ``undone_at`` on ``bill_payments`` and
``debt_payments`` marks a payment undone; the row is kept as history.
``balance_reduced_cents`` on ``debt_payments`` is how much the debt's balance
went down, which is less than the amount when a payment overpaid past $0, so an
undo can put exactly that back. Existing payments are taken to have reduced the
balance by their full amount: nothing recorded more, and a payment made before
the latest commit cannot be undone anyway. Like every migration, this file is
frozen: it never imports the app.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c5e7f9b1d2"
down_revision: str | None = "7d1f3a9c2e64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("bill_payments", "debt_payments")


def upgrade() -> None:
    op.add_column(
        "debt_payments", sa.Column("balance_reduced_cents", sa.BigInteger(), nullable=True)
    )
    op.execute("UPDATE debt_payments SET balance_reduced_cents = amount_cents")
    op.alter_column("debt_payments", "balance_reduced_cents", nullable=False)
    op.create_check_constraint(
        op.f("ck_debt_payments_balance_reduced_range"),
        "debt_payments",
        "balance_reduced_cents >= 0 AND balance_reduced_cents <= amount_cents",
    )
    for table in _TABLES:
        op.add_column(table, sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "undone_at")
    op.drop_constraint(
        op.f("ck_debt_payments_balance_reduced_range"), "debt_payments", type_="check"
    )
    op.drop_column("debt_payments", "balance_reduced_cents")
