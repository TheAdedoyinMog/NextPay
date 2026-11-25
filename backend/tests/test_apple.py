"""Verifying Sign in with Apple identity tokens (ADR 0019), with Apple's keys mocked.

Fixtures (``apple_token``, ``apple_keys``, the keys themselves) live in tests/conftest.py.
"""

import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from app.core.apple import AppleKeySet, AppleTokenVerifier, hash_nonce
from app.core.errors import (
    AppleNonceMismatchError,
    AppleTokenClaimsError,
    AppleTokenExpiredError,
    AppleTokenSignatureError,
    AppleUnavailableError,
    InvalidAppleTokenError,
)

BUNDLE_ID = "com.theadedoyinmog.nextpay"
NONCE = "a" * 64  # matches APPLE_NONCE in conftest.py
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)  # matches APPLE_NOW

type MakeToken = Callable[..., str]


@pytest.fixture
def verifier(apple_keys: Any) -> AppleTokenVerifier:
    return AppleTokenVerifier(apple_keys, BUNDLE_ID)


# --- a valid token -----------------------------------------------------------------------


def test_a_valid_token_gives_the_apple_user(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    claims = verifier.verify(apple_token(), NONCE, NOW)
    assert claims.user_id == "001234.abcdef0123456789.1234"
    assert claims.email == "x7k2p9@privaterelay.appleid.com"
    assert claims.is_private_email is True


def test_a_real_email_is_lowercased_and_not_private(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    token = apple_token(email="Ada@iCloud.com", is_private_email=False)
    claims = verifier.verify(token, NONCE, NOW)
    assert claims.email == "ada@icloud.com"
    assert claims.is_private_email is False


def test_a_token_without_an_email_is_still_valid(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    claims = verifier.verify(apple_token(email=None, is_private_email=None), NONCE, NOW)
    assert claims.email is None
    assert claims.is_private_email is False


# --- expiry ------------------------------------------------------------------------------


def test_a_token_is_valid_until_its_last_second(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    token = apple_token(exp=int(NOW.timestamp()) + 1)
    assert verifier.verify(token, NONCE, NOW).user_id


def test_an_expired_token_is_rejected(verifier: AppleTokenVerifier, apple_token: MakeToken) -> None:
    token = apple_token(exp=int(NOW.timestamp()))
    with pytest.raises(AppleTokenExpiredError):
        verifier.verify(token, NONCE, NOW)


def test_expiry_follows_the_injected_clock_not_the_wall_clock(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    token = apple_token()  # valid for ten minutes from NOW, long past on the wall clock
    assert verifier.verify(token, NONCE, NOW + timedelta(minutes=9)).user_id
    with pytest.raises(AppleTokenExpiredError):
        verifier.verify(token, NONCE, NOW + timedelta(minutes=10))


def test_a_non_integer_expiry_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    with pytest.raises(InvalidAppleTokenError):
        verifier.verify(apple_token(exp="tomorrow"), NONCE, NOW)


# --- audience and issuer -----------------------------------------------------------------


def test_a_token_for_another_app_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    with pytest.raises(AppleTokenClaimsError):
        verifier.verify(apple_token(aud="com.someone.else"), NONCE, NOW)


def test_a_token_from_another_issuer_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    with pytest.raises(AppleTokenClaimsError):
        verifier.verify(apple_token(iss="https://evil.example"), NONCE, NOW)


@pytest.mark.parametrize("claim", ["iss", "aud", "exp", "iat", "sub", "nonce"])
def test_every_required_claim_must_be_present(
    verifier: AppleTokenVerifier, apple_token: MakeToken, claim: str
) -> None:
    with pytest.raises(AppleTokenClaimsError):
        verifier.verify(apple_token(**{claim: None}), NONCE, NOW)


@pytest.mark.parametrize("sub", ["", "x" * 256, 12345])
def test_an_unusable_user_id_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken, sub: object
) -> None:
    with pytest.raises(InvalidAppleTokenError):
        verifier.verify(apple_token(sub=sub), NONCE, NOW)


# --- signature ---------------------------------------------------------------------------


def test_a_token_signed_with_another_key_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken, other_private_key: Any
) -> None:
    with pytest.raises(AppleTokenSignatureError):
        verifier.verify(apple_token(key=other_private_key), NONCE, NOW)


def test_a_token_whose_claims_were_edited_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    header, payload, signature = apple_token().split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["sub"] = "someone-else"
    edited = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    with pytest.raises(AppleTokenSignatureError):
        verifier.verify(f"{header}.{edited}.{signature}", NONCE, NOW)


def test_a_key_id_apple_never_published_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    with pytest.raises(AppleTokenSignatureError):
        verifier.verify(apple_token(kid="made-up"), NONCE, NOW)


def test_an_unsigned_token_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    _, payload, _ = apple_token().split(".")
    header = base64.urlsafe_b64encode(b'{"alg":"none","kid":"test-key-1"}').rstrip(b"=").decode()
    with pytest.raises(AppleTokenSignatureError):
        verifier.verify(f"{header}.{payload}.", NONCE, NOW)


def test_hs256_signed_with_apples_public_key_is_rejected(
    verifier: AppleTokenVerifier, apple_private_key: Any
) -> None:
    """Algorithm confusion: treating the public key, which anyone has, as an HMAC secret."""
    public_pem = apple_private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","kid":"test-key-1"}').rstrip(b"=")
    body = base64.urlsafe_b64encode(
        json.dumps(
            {
                "iss": "https://appleid.apple.com",
                "aud": BUNDLE_ID,
                "sub": "forged",
                "iat": 0,
                "exp": int(NOW.timestamp()) + 600,
                "nonce": hash_nonce(NONCE),
            }
        ).encode()
    ).rstrip(b"=")
    signature = base64.urlsafe_b64encode(
        hmac.new(public_pem, header + b"." + body, hashlib.sha256).digest()
    ).rstrip(b"=")
    forged = b".".join([header, body, signature]).decode()
    with pytest.raises(AppleTokenSignatureError):
        verifier.verify(forged, NONCE, NOW)


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c", "x" * 50])
def test_garbage_is_rejected(verifier: AppleTokenVerifier, token: str) -> None:
    with pytest.raises(InvalidAppleTokenError):
        verifier.verify(token, NONCE, NOW)


# --- nonce -------------------------------------------------------------------------------


def test_a_token_made_for_another_nonce_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    token = apple_token(nonce=hash_nonce("b" * 64))
    with pytest.raises(AppleNonceMismatchError):
        verifier.verify(token, NONCE, NOW)


def test_presenting_the_hash_from_inside_the_token_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    """The token holds only the nonce's hash, so someone who has just the token can't
    produce the raw nonce it was made for."""
    with pytest.raises(AppleNonceMismatchError):
        verifier.verify(apple_token(), hash_nonce(NONCE), NOW)


def test_a_non_string_nonce_claim_is_rejected(
    verifier: AppleTokenVerifier, apple_token: MakeToken
) -> None:
    with pytest.raises(AppleNonceMismatchError):
        verifier.verify(apple_token(nonce=12345), NONCE, NOW)


def test_the_nonce_hash_is_lowercase_hex_sha256() -> None:
    # What expo-crypto's digestStringAsync(SHA256, "abc") returns.
    assert hash_nonce("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


# --- Apple's keys ------------------------------------------------------------------------


def test_apple_being_unreachable_is_not_the_users_fault(
    verifier: AppleTokenVerifier, apple_token: MakeToken, apple_keys: Any
) -> None:
    apple_keys.unavailable = True
    with pytest.raises(AppleUnavailableError):
        verifier.verify(apple_token(), NONCE, NOW)


def test_rotated_keys_are_used_by_key_id(
    verifier: AppleTokenVerifier, apple_token: MakeToken, apple_keys: Any, other_private_key: Any
) -> None:
    apple_keys.keys["test-key-2"] = other_private_key.public_key()
    token = apple_token(key=other_private_key, kid="test-key-2")
    assert verifier.verify(token, NONCE, NOW).user_id


def test_the_key_set_reports_a_network_failure_as_apple_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = AppleKeySet()

    def unreachable(kid: str) -> Any:
        raise jwt.PyJWKClientConnectionError("timed out")

    monkeypatch.setattr(keys._client, "get_signing_key", unreachable)
    with pytest.raises(AppleUnavailableError):
        keys.signing_key("any")


def test_the_key_set_reports_an_unknown_key_id_as_a_bad_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = AppleKeySet()

    def no_such_key(kid: str) -> Any:
        raise jwt.PyJWKClientError("Unable to find a signing key that matches")

    monkeypatch.setattr(keys._client, "get_signing_key", no_such_key)
    with pytest.raises(AppleTokenSignatureError):
        keys.signing_key("any")


def test_the_key_set_returns_the_published_key(
    monkeypatch: pytest.MonkeyPatch, apple_private_key: Any
) -> None:
    keys = AppleKeySet()
    jwk = jwt.PyJWK.from_dict(
        {
            **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(apple_private_key.public_key())),
            "kid": "k",
            "alg": "RS256",
            "use": "sig",
        }
    )
    monkeypatch.setattr(keys._client, "get_signing_key", lambda kid: jwk)
    assert keys.signing_key("k") is jwk.key
