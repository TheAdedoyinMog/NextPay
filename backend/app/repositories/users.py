"""Storage for user accounts."""

import uuid

import psycopg
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import EmailUnavailableError
from app.models import User

_EMAIL_UNIQUE = "uq_users_email"


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: uuid.UUID) -> User | None:
        return self._session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        """``email`` must already be normalized (lowercase); there is no user_id yet
        to scope by, since this is how a user is found before signing in."""
        return self._session.scalar(select(User).where(User.email == email))

    def lock(self, user_id: uuid.UUID) -> None:
        """Hold ``user_id``'s row lock until the transaction ends.

        Planning writes (plans, commits, payments, paychecks) take it first, so
        two requests from one user run one after the other, never interleaved.
        """
        self._session.execute(select(User.id).where(User.id == user_id).with_for_update())

    def add(self, user: User) -> User:
        """Insert ``user``. Raises ``EmailUnavailableError`` if the email is taken,
        including when a concurrent sign-up won the race after our check."""
        try:
            with self._session.begin_nested():
                self._session.add(user)
        except IntegrityError as error:
            cause = error.orig
            if isinstance(cause, psycopg.Error) and cause.diag.constraint_name == _EMAIL_UNIQUE:
                raise EmailUnavailableError() from error
            raise
        return user
