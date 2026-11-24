"""paid occurrences

Revision ID: c8e2f4a6d0b1
Revises: a3c5e7f9b1d2
Create Date: 2026-11-22 18:00:00.000000+00:00

Milestone 3D part 3 (ADR 0018). ``debt_payments.due_date`` names the occurrence
a debt payment pays, as ``bill_payments.due_date`` does. Existing payments get
the debt's due date on or before the day they were paid (the due day moved to
the month's last day when the month is shorter): a conservative choice, which
can never skip a later occurrence the user didn't clearly pay.

``allocations`` gains the five facts the engine's Basis now carries about what
is already paid. Existing lines get "nothing paid", so their explanations read
as before. Like every migration, this file is frozen: it never imports the app.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e2f4a6d0b1"
down_revision: str | None = "a3c5e7f9b1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The due date in the month of paid_on and in the month before, each clamped to the
# month's length; the later of the two that is not after paid_on.
_BACKFILL_DUE_DATE = """
WITH candidates AS (
    SELECT
        p.id,
        p.paid_on,
        date_trunc('month', p.paid_on)::date
            + (least(
                d.due_day,
                extract(day FROM date_trunc('month', p.paid_on)
                    + interval '1 month' - interval '1 day')::int
            ) - 1) AS this_month,
        date_trunc('month', p.paid_on - interval '1 month')::date
            + (least(
                d.due_day,
                extract(day FROM date_trunc('month', p.paid_on) - interval '1 day')::int
            ) - 1) AS last_month
    FROM debt_payments p
    JOIN debts d ON d.id = p.debt_id
)
UPDATE debt_payments p
SET due_date = CASE
    WHEN c.this_month <= c.paid_on THEN c.this_month
    ELSE c.last_month
END
FROM candidates c
WHERE c.id = p.id
"""


def upgrade() -> None:
    op.add_column("debt_payments", sa.Column("due_date", sa.Date(), nullable=True))
    op.execute(_BACKFILL_DUE_DATE)
    op.alter_column("debt_payments", "due_date", nullable=False)
    op.create_index("ix_debt_payments_debt_id_due_date", "debt_payments", ["debt_id", "due_date"])

    op.add_column("allocations", sa.Column("paid_cents", sa.BigInteger(), nullable=True))
    op.add_column("allocations", sa.Column("paid_on", sa.Date(), nullable=True))
    op.add_column("allocations", sa.Column("paid_ahead", sa.Integer(), nullable=True))
    op.add_column("allocations", sa.Column("paid_through", sa.Date(), nullable=True))
    op.add_column("allocations", sa.Column("paid_ahead_on", sa.Date(), nullable=True))
    op.execute("UPDATE allocations SET paid_cents = 0, paid_ahead = 0")
    op.alter_column("allocations", "paid_cents", nullable=False)
    op.alter_column("allocations", "paid_ahead", nullable=False)
    op.create_check_constraint(
        op.f("ck_allocations_paid_not_negative"), "allocations", "paid_cents >= 0"
    )
    op.create_check_constraint(
        op.f("ck_allocations_paid_ahead_not_negative"), "allocations", "paid_ahead >= 0"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_allocations_paid_ahead_not_negative"), "allocations", type_="check")
    op.drop_constraint(op.f("ck_allocations_paid_not_negative"), "allocations", type_="check")
    for column in ("paid_ahead_on", "paid_through", "paid_ahead", "paid_on", "paid_cents"):
        op.drop_column("allocations", column)
    op.drop_index("ix_debt_payments_debt_id_due_date", table_name="debt_payments")
    op.drop_column("debt_payments", "due_date")
