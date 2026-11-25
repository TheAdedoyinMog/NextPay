"""Storage for the Apple IDs accounts sign in with (ADR 0019)."""

import psycopg
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AppleIdentity, User

_APPLE_USER_ID_UNIQUE = "uq_apple_identities_apple_user_id"


class AppleIdentityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_apple_user_id(self, apple_user_id: str) -> AppleIdentity | None:
        """Apple's ``sub`` is the credential here, as a token hash is for refresh, so there is
        no user_id to scope by yet."""
        query = select(AppleIdentity).where(AppleIdentity.apple_user_id == apple_user_id)
        return self._session.scalar(query)

    def add_with_user(self, user: User, identity: AppleIdentity) -> bool:
        """Insert a new account and its Apple ID together.

        Returns False, and inserts neither, if the Apple ID already has an account: two first
        sign-ins raced, and the other one won. The transaction stays usable.
        """
        try:
            with self._session.begin_nested():
                self._session.add(user)
                self._session.flush()  # the user row first: the identity references it
                self._session.add(identity)
        except IntegrityError as error:
            cause = error.orig
            if (
                isinstance(cause, psycopg.Error)
                and cause.diag.constraint_name == _APPLE_USER_ID_UNIQUE
            ):
                return False
            raise
        return True
