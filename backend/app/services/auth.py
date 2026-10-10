"""Accounts and sessions: register, log in, refresh, log out (ADR 0006, ADR 0009).

A session is a family of refresh tokens that starts at login. Each refresh
rotates the token: the old one is marked ``replaced_by_id`` and a new one joins
the same family. Only the newest token in a family is ever usable, so a rotated
or revoked token coming back means two parties hold the session; the whole
family is then revoked and both must sign in again.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from email_validator import EmailNotValidError, validate_email

from app.core.clock import Clock
from app.core.errors import (
    EmailUnavailableError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidInputError,
    RefreshTokenExpiredError,
    RefreshTokenNotFoundError,
    RefreshTokenReusedError,
)
from app.core.security import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    AccessTokenCodec,
    PasswordHasher,
    hash_refresh_token,
    new_refresh_token,
)
from app.models import RefreshToken, User

logger = logging.getLogger(__name__)


class UserStore(Protocol):
    def get(self, user_id: uuid.UUID) -> User | None: ...
    def get_by_email(self, email: str) -> User | None: ...
    def add(self, user: User) -> User: ...


class RefreshTokenStore(Protocol):
    def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None: ...
    def add(self, token: RefreshToken) -> RefreshToken: ...
    def revoke_family(self, user_id: uuid.UUID, family_id: uuid.UUID, at: datetime) -> int: ...


class Transaction(Protocol):
    """What the service needs to end a unit of work. A SQLAlchemy Session is one."""

    def commit(self) -> None: ...


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    expires_in: int  # seconds until the access token expires
    refresh_token: str


def normalize_email(email: str) -> str:
    """The email as stored: syntax-checked, trimmed, and lowercased."""
    try:
        result = validate_email(email.strip(), check_deliverability=False)
    except EmailNotValidError as error:
        raise InvalidInputError("Enter a valid email address.") from error
    return result.normalized.lower()


def check_password(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidInputError(
            f"Use a password of {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters."
        )


class AuthService:
    def __init__(
        self,
        *,
        users: UserStore,
        refresh_tokens: RefreshTokenStore,
        transaction: Transaction,
        hasher: PasswordHasher,
        access_tokens: AccessTokenCodec,
        refresh_token_ttl: timedelta,
        clock: Clock,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._transaction = transaction
        self._hasher = hasher
        self._access_tokens = access_tokens
        self._refresh_token_ttl = refresh_token_ttl
        self._clock = clock

    def register(self, email: str, password: str) -> TokenPair:
        """Create an account and sign it in.

        Raises ``InvalidInputError`` or ``EmailUnavailableError``.
        """
        email = normalize_email(email)
        check_password(password)
        # Hash before looking the email up, so a taken email answers no faster.
        password_hash = self._hasher.hash(password)
        if self._users.get_by_email(email) is not None:
            raise EmailUnavailableError()
        user = self._users.add(User(email=email, password_hash=password_hash))
        tokens = self._start_session(user.id)
        self._transaction.commit()
        return tokens

    def login(self, email: str, password: str) -> TokenPair:
        """Start a new session. Raises ``InvalidCredentialsError`` for any failure."""
        try:
            user = self._users.get_by_email(normalize_email(email))
        except InvalidInputError:
            user = None
        if user is None or user.password_hash is None:
            self._hasher.verify_dummy(password)  # same time as a real check
            raise InvalidCredentialsError()
        if not self._hasher.verify(user.password_hash, password):
            raise InvalidCredentialsError()
        if self._hasher.needs_rehash(user.password_hash):
            user.password_hash = self._hasher.hash(password)
        tokens = self._start_session(user.id)
        self._transaction.commit()
        return tokens

    def refresh(self, refresh_token: str) -> TokenPair:
        """Rotate ``refresh_token`` for a new pair.

        Raises an ``InvalidRefreshTokenError`` subclass. On reuse, the whole
        family is revoked (and committed) before raising.
        """
        now = self._clock()
        token = self._refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
        if token is None:
            raise RefreshTokenNotFoundError()
        # Reuse first: a rotated token is evidence of theft even after it expires.
        if token.replaced_by_id is not None or token.revoked_at is not None:
            revoked = self._refresh_tokens.revoke_family(token.user_id, token.family_id, now)
            self._transaction.commit()
            logger.warning(
                "refresh token reuse: user %s, family %s; revoked %d token(s)",
                token.user_id,
                token.family_id,
                revoked,
            )
            raise RefreshTokenReusedError()
        if token.expires_at <= now:
            raise RefreshTokenExpiredError()

        raw, successor = self._issue_refresh_token(token.user_id, token.family_id, now)
        token.replaced_by_id = successor.id
        access = self._access_tokens.issue(token.user_id, now)
        self._transaction.commit()
        return TokenPair(access.token, access.expires_in, raw)

    def logout(self, refresh_token: str) -> None:
        """End the session ``refresh_token`` belongs to: this device, not all of them.

        Silent for unknown or already-revoked tokens, so logout can't probe tokens.
        """
        token = self._refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
        if token is None:
            return
        self._refresh_tokens.revoke_family(token.user_id, token.family_id, self._clock())
        self._transaction.commit()

    def authenticate(self, access_token: str) -> User:
        """The user an access token belongs to.

        Raises ``AccessTokenExpiredError`` or ``InvalidAccessTokenError``, including
        for a well-formed token whose user no longer exists.
        """
        user = self._users.get(self._access_tokens.user_id(access_token, self._clock()))
        if user is None:
            raise InvalidAccessTokenError()
        return user

    def _start_session(self, user_id: uuid.UUID) -> TokenPair:
        now = self._clock()
        raw, _ = self._issue_refresh_token(user_id, uuid.uuid4(), now)
        access = self._access_tokens.issue(user_id, now)
        return TokenPair(access.token, access.expires_in, raw)

    def _issue_refresh_token(
        self, user_id: uuid.UUID, family_id: uuid.UUID, now: datetime
    ) -> tuple[str, RefreshToken]:
        raw = new_refresh_token()
        token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=hash_refresh_token(raw),
            family_id=family_id,
            expires_at=now + self._refresh_token_ttl,
        )
        return raw, self._refresh_tokens.add(token)
