"""sign in with apple

Revision ID: e1a7c3f5b9d2
Revises: c8e2f4a6d0b1
Create Date: 2026-11-24 18:00:00.000000+00:00

Milestone 3E (ADR 0019). ``apple_identities`` links an account to the Apple ID it
signs in with, found by Apple's ``sub`` (``apple_user_id``) only. ``users.email``
becomes nullable: it is the email an account signs in with by password, and an
account made with Apple has none. ``users.display_name`` holds the name Apple
shares on the first sign-in. Existing rows need no backfill.

Downgrading deletes every account without an email, and with it everything those
accounts own: without this migration they could never sign in again. Like every
migration, this file is frozen: it never imports the app.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1a7c3f5b9d2"
down_revision: str | None = "c8e2f4a6d0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=True)
    op.add_column("users", sa.Column("display_name", sa.String(200), nullable=True))
    op.create_table(
        "apple_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("apple_user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("is_private_email", sa.Boolean(), server_default=sa.false(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_apple_identities"),
        sa.UniqueConstraint("user_id", "id", name="uq_apple_identities_user_id_id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_apple_identities_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("apple_user_id", name="uq_apple_identities_apple_user_id"),
        sa.UniqueConstraint("user_id", name="uq_apple_identities_user_id"),
    )


def downgrade() -> None:
    op.drop_table("apple_identities")
    op.execute("DELETE FROM users WHERE email IS NULL")
    op.drop_column("users", "display_name")
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=False)
