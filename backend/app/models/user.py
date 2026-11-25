"""Accounts, their Apple IDs, and login tokens (ADR 0006, ADR 0009, ADR 0019)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.columns import IdMixin, TimestampsMixin, UserOwnedMixin, owned_by_user, tenant_fk


class User(IdMixin, TimestampsMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email"),
        # The service lowercases emails, so the plain unique constraint is case-insensitive.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("email <> ''", name="email_not_blank"),
        CheckConstraint(
            "no_deadline_goal_share_bps BETWEEN 0 AND 10000", name="goal_share_bps_range"
        ),
    )

    # The email this account signs in with by password. None for an account made with
    # Sign in with Apple, whose Apple email is on AppleIdentity and finds nothing (ADR 0019).
    email: Mapped[str | None] = mapped_column(String(320))
    # None for accounts that only sign in with Apple.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # From Apple's first sign-in, the only time Apple shares the name.
    display_name: Mapped[str | None] = mapped_column(String(200), sort_order=3)  # added in 3E
    # IANA name, e.g. "America/New_York": decides what "today" is for this user.
    timezone: Mapped[str] = mapped_column(String(64), server_default="UTC")
    # FinancialState.no_deadline_goal_share_bps: share of what is left for goals
    # with no deadline. 2000 is 20%.
    no_deadline_goal_share_bps: Mapped[int] = mapped_column(server_default="2000")


class AppleIdentity(UserOwnedMixin, TimestampsMixin, Base):
    """The Apple ID an account signs in with (ADR 0019). Found by ``apple_user_id`` only."""

    __tablename__ = "apple_identities"
    __table_args__ = (
        owned_by_user(),
        UniqueConstraint("apple_user_id"),
        UniqueConstraint("user_id"),  # one Apple ID per account
    )

    # Apple's `sub`: stable for this user and our app, whatever email they share.
    apple_user_id: Mapped[str] = mapped_column(String(255))
    # The email Apple last reported, possibly a private relay. Contact only: never a login.
    email: Mapped[str | None] = mapped_column(String(320))
    is_private_email: Mapped[bool] = mapped_column(server_default=false())


class RefreshToken(UserOwnedMixin, TimestampsMixin, Base):
    """A rotating refresh token, stored only as a hash."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        owned_by_user(),
        UniqueConstraint("token_hash"),
        tenant_fk("replaced_by_id", "refresh_tokens", ondelete="SET NULL"),
    )

    token_hash: Mapped[str] = mapped_column(String(128))
    # Every token rotated from the same login shares a family, so reuse of an old
    # token can revoke the whole family.
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None]
