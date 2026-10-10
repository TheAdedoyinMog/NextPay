"""Security primitives: password hashing, access tokens, refresh tokens (ADR 0006, 0009).

Pure helpers with no database access. Time is always passed in, so expiry is
testable without sleeping.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import argon2
import jwt

from app.core.errors import AccessTokenExpiredError, InvalidAccessTokenError

# NIST SP 800-63B: length over composition rules. The maximum caps the work one
# request can make the hasher do.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

_JWT_ALGORITHM = "HS256"
_JWT_ISSUER = "nextpay"
_JWT_AUDIENCE = "nextpay-api"


class PasswordHasher:
    """Argon2id hashing. The default parameters are argon2-cffi's (RFC 9106)."""

    def __init__(self, hasher: argon2.PasswordHasher | None = None) -> None:
        self._hasher = hasher or argon2.PasswordHasher()
        self._dummy_hash: str | None = None

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except argon2.exceptions.VerificationError:
            return False
        except argon2.exceptions.InvalidHashError:
            return False

    def verify_dummy(self, password: str) -> None:
        """Spend the same time as a real check, for an email with no account.

        Without it, "unknown email" answers faster than "wrong password", which
        tells an attacker which emails have accounts.
        """
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(16))
        self.verify(self._dummy_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        """True when ``password_hash`` used older parameters than the current ones."""
        return self._hasher.check_needs_rehash(password_hash)


@dataclass(frozen=True, slots=True)
class AccessToken:
    token: str
    expires_in: int  # seconds


class AccessTokenCodec:
    """Signs and checks short-lived JWT access tokens (HS256)."""

    def __init__(self, secret: str, ttl: timedelta) -> None:
        self._secret = secret
        self._ttl = ttl

    def issue(self, user_id: uuid.UUID, now: datetime) -> AccessToken:
        claims = {
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int((now + self._ttl).timestamp()),
            "iss": _JWT_ISSUER,
            "aud": _JWT_AUDIENCE,
        }
        token = jwt.encode(claims, self._secret, algorithm=_JWT_ALGORITHM)
        return AccessToken(token, int(self._ttl.total_seconds()))

    def user_id(self, token: str, now: datetime) -> uuid.UUID:
        """The user a valid token was issued to.

        Raises ``AccessTokenExpiredError`` or ``InvalidAccessTokenError``.
        """
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[_JWT_ALGORITHM],  # pinned: rejects "none" and algorithm confusion
                issuer=_JWT_ISSUER,
                audience=_JWT_AUDIENCE,
                # Time checks use our clock below, not PyJWT's wall clock.
                options={
                    "require": ["sub", "iat", "exp", "iss", "aud"],
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
            expires = claims["exp"]
            if type(expires) is not int:
                raise InvalidAccessTokenError()
            if expires <= now.timestamp():
                raise AccessTokenExpiredError()
            return uuid.UUID(claims["sub"])
        except jwt.PyJWTError as error:
            raise InvalidAccessTokenError() from error
        except (TypeError, ValueError, AttributeError) as error:  # malformed sub
            raise InvalidAccessTokenError() from error


def new_refresh_token() -> str:
    """A fresh opaque refresh token: 256 random bits, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hex. Refresh tokens are random, so a fast hash is enough to make a
    leaked table useless, and it lets us look tokens up by their hash."""
    return hashlib.sha256(token.encode()).hexdigest()
