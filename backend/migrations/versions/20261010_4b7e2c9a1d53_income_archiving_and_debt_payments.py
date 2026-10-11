"""income source archiving and debt payments

Revision ID: 4b7e2c9a1d53
Revises: cffe56eb22a1
Create Date: 2026-10-10 18:00:00.000000+00:00

Milestone 2D (ADR 0011). ``income_sources.archived_at`` marks a source the user
removed after it had paychecks. ``paycheck_plans.balance_as_of`` records when
the balance a plan used was entered. ``debt_payments`` records payments toward
a debt, as ``bill_payments`` does for bills. Like every migration, this file is
frozen: it never imports the app.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4b7e2c9a1d53"
down_revision: str | None = "cffe56eb22a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "income_sources", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column(
        "paycheck_plans", sa.Column("balance_as_of", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "debt_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("debt_id", sa.Uuid(), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_debt_payments"),
        sa.UniqueConstraint("user_id", "id", name="uq_debt_payments_user_id_id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_debt_payments_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "debt_id"],
            ["debts.user_id", "debts.id"],
            name="fk_debt_payments_user_id_debt_id_debts",
            ondelete="CASCADE",
        ),
        # op.f(): the name is already final, so the naming convention is not applied again.
        sa.CheckConstraint("amount_cents > 0", name=op.f("ck_debt_payments_amount_positive")),
    )
    op.create_index("ix_debt_payments_debt_id_paid_on", "debt_payments", ["debt_id", "paid_on"])


def downgrade() -> None:
    op.drop_index("ix_debt_payments_debt_id_paid_on", table_name="debt_payments")
    op.drop_table("debt_payments")
    op.drop_column("paycheck_plans", "balance_as_of")
    op.drop_column("income_sources", "archived_at")
