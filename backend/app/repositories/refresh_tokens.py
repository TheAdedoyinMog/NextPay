"""Storage for refresh tokens (hashes only; ADR 0009)."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        """The token with ``token_hash``, row-locked until the transaction ends.

        The lock makes two refreshes with the same token take turns, so the
        second sees the first's rotation and is caught as reuse. The hash is the
        credential, so there is no user_id to scope by yet.
        """
        query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self._session.scalar(query.with_for_update())

    def add(self, token: RefreshToken) -> RefreshToken:
        self._session.add(token)
        self._session.flush()
        return token

    def revoke_family(self, user_id: uuid.UUID, family_id: uuid.UUID, at: datetime) -> int:
        """Revoke every live token in one session (family). Returns how many."""
        result = self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=at)
        )
        return result.rowcount  # type: ignore[attr-defined, no-any-return]
