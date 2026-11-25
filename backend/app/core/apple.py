"""Checks Sign in with Apple identity tokens (ADR 0019).

The app signs in with Apple on the phone and sends us the identity token Apple gave it:
a JWT signed by Apple. We trust it only if Apple's current keys signed it with RS256, it was
issued by Apple for our bundle ID, it hasn't expired, and it carries the hash of the nonce
the app sent alongside it. Time is passed in, as in ``app.core.security``.
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import jwt

from app.core.errors import (
    AppleNonceMismatchError,
    AppleTokenClaimsError,
    AppleTokenExpiredError,
    AppleTokenMalformedError,
    AppleTokenSignatureError,
    AppleUnavailableError,
)

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
_ALGORITHM = "RS256"
_MAX_USER_ID_LENGTH = 255
_MAX_EMAIL_LENGTH = 320


@dataclass(frozen=True, slots=True)
class AppleClaims:
    """What a verified identity token tells us about the user."""

    user_id: str  # `sub`: Apple's stable ID for this user and our app
    email: str | None  # may be a private relay address; not every token has one
    is_private_email: bool


class AppleKeySource(Protocol):
    def signing_key(self, kid: str) -> Any:
        """Apple's public key with this key ID.

        Raises ``AppleTokenSignatureError`` if Apple has no such key, or
        ``AppleUnavailableError`` if Apple's keys can't be fetched.
        """
        ...


class AppleKeySet:
    """Apple's published keys, fetched and cached by PyJWT.

    A key ID that isn't cached (Apple rotated its keys) refetches the set, at most once per
    ``cooldown`` seconds, so a stream of made-up key IDs can't make us hammer Apple.
    """

    def __init__(
        self, url: str = APPLE_KEYS_URL, *, timeout: float = 5.0, cooldown: float = 30.0
    ) -> None:
        self._client = jwt.PyJWKClient(
            url,
            cache_keys=True,
            lifespan=24 * 60 * 60,
            timeout=timeout,
            cooldown_duration=cooldown,
        )

    def signing_key(self, kid: str) -> Any:
        try:
            return self._client.get_signing_key(kid).key
        except jwt.PyJWKClientConnectionError as error:
            raise AppleUnavailableError() from error
        except jwt.PyJWKClientError as error:  # fetched fine, but no key with this ID
            raise AppleTokenSignatureError() from error


def hash_nonce(nonce: str) -> str:
    """What the app hands Apple for a nonce, and so what the token's `nonce` claim holds:
    SHA-256, lowercase hex."""
    return hashlib.sha256(nonce.encode()).hexdigest()


class AppleTokenVerifier:
    def __init__(self, keys: AppleKeySource, audience: str) -> None:
        self._keys = keys
        self._audience = audience

    def verify(self, identity_token: str, nonce: str, now: datetime) -> AppleClaims:
        """The claims of a token Apple issued for our app and for ``nonce``.

        Raises an ``InvalidAppleTokenError`` subclass, or ``AppleUnavailableError``.
        """
        claims = self._decode(identity_token)

        expires = claims["exp"]
        if type(expires) is not int:
            raise AppleTokenClaimsError()
        if expires <= now.timestamp():
            raise AppleTokenExpiredError()

        token_nonce = claims["nonce"]
        if not isinstance(token_nonce, str) or not hmac.compare_digest(
            token_nonce.encode(), hash_nonce(nonce).encode()
        ):
            raise AppleNonceMismatchError()

        user_id = claims["sub"]
        if not isinstance(user_id, str) or not 0 < len(user_id) <= _MAX_USER_ID_LENGTH:
            raise AppleTokenClaimsError()

        email = claims.get("email")
        if not isinstance(email, str) or not 0 < len(email) <= _MAX_EMAIL_LENGTH:
            email = None
        return AppleClaims(
            user_id=user_id,
            email=email.lower() if email else None,
            is_private_email=_is_true(claims.get("is_private_email")),
        )

    def _decode(self, identity_token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(identity_token)
        except jwt.PyJWTError as error:
            raise AppleTokenMalformedError() from error
        kid = header.get("kid")
        # Checked before any key lookup: "none", HS256 with the public key as a secret, and
        # every other algorithm confusion are refused here and again by `algorithms` below.
        if header.get("alg") != _ALGORITHM or not isinstance(kid, str):
            raise AppleTokenSignatureError()
        key = self._keys.signing_key(kid)
        try:
            claims: dict[str, Any] = jwt.decode(
                identity_token,
                key,
                algorithms=[_ALGORITHM],
                issuer=APPLE_ISSUER,
                audience=self._audience,
                # Expiry is checked against our clock in `verify`, not PyJWT's wall clock.
                options={
                    "require": ["iss", "aud", "exp", "iat", "sub", "nonce"],
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
        except jwt.InvalidSignatureError as error:
            raise AppleTokenSignatureError() from error
        except (
            jwt.InvalidIssuerError,
            jwt.InvalidAudienceError,
            jwt.MissingRequiredClaimError,
        ) as error:
            raise AppleTokenClaimsError() from error
        except jwt.PyJWTError as error:
            raise AppleTokenMalformedError() from error
        return claims


def _is_true(value: object) -> bool:
    """Apple sends some booleans as JSON booleans and some as the strings "true"/"false"."""
    return value is True or value == "true"
