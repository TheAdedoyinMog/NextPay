"""Access-token checks: only tokens we signed, unaltered and unexpired, name a user."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.errors import AccessTokenExpiredError, InvalidAccessTokenError
from app.core.security import (
    AccessTokenCodec,
    PasswordHasher,
    hash_refresh_token,
    new_refresh_token,
)

SECRET = "codec-test-secret-" + "x" * 64  # long enough for the HS512 case too
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
USER = uuid.uuid4()
CODEC = AccessTokenCodec(SECRET, timedelta(minutes=15))


def claims(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sub": str(USER),
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=15)).timestamp()),
        "iss": "nextpay",
        "aud": "nextpay-api",
    }
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not None}


def test_an_issued_token_names_its_user() -> None:
    token = CODEC.issue(USER, NOW)
    assert token.expires_in == 900
    assert CODEC.user_id(token.token, NOW) == USER


def test_a_token_expires_at_its_exp() -> None:
    token = CODEC.issue(USER, NOW).token
    with pytest.raises(AccessTokenExpiredError):
        CODEC.user_id(token, NOW + timedelta(minutes=15))


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(jwt.encode(claims(), "another-secret-" + "y" * 64), id="wrong secret"),
        pytest.param(jwt.encode(claims(), None, algorithm="none"), id="alg none"),
        pytest.param(jwt.encode(claims(), SECRET, algorithm="HS512"), id="other algorithm"),
        pytest.param(jwt.encode(claims(aud="elsewhere"), SECRET), id="wrong audience"),
        pytest.param(jwt.encode(claims(iss="elsewhere"), SECRET), id="wrong issuer"),
        pytest.param(jwt.encode(claims(exp=None), SECRET), id="no expiry"),
        pytest.param(jwt.encode(claims(sub=None), SECRET), id="no subject"),
        pytest.param(jwt.encode(claims(sub="ada"), SECRET), id="subject not a uuid"),
        pytest.param(jwt.encode(claims(exp="tomorrow"), SECRET), id="expiry not a number"),
        pytest.param("not.a.jwt", id="garbage"),
    ],
)
def test_tokens_we_did_not_issue_are_rejected(token: str) -> None:
    with pytest.raises(InvalidAccessTokenError):
        CODEC.user_id(token, NOW)


def test_a_token_with_a_swapped_subject_fails_its_signature() -> None:
    header, _payload, signature = CODEC.issue(USER, NOW).token.split(".")
    other = jwt.encode(claims(sub=str(uuid.uuid4())), "irrelevant-" + "z" * 32).split(".")[1]
    with pytest.raises(InvalidAccessTokenError):
        CODEC.user_id(f"{header}.{other}.{signature}", NOW)


def test_refresh_tokens_are_random_and_hashed_with_sha256() -> None:
    first, second = new_refresh_token(), new_refresh_token()
    assert first != second
    assert len(first) >= 43  # 256 bits, base64url
    digest = hash_refresh_token(first)
    assert len(digest) == 64
    assert digest == hash_refresh_token(first)
    assert digest != hash_refresh_token(second)


def test_password_verification_never_raises() -> None:
    hasher = PasswordHasher()
    assert not hasher.verify("not-a-hash", "password")
    assert not hasher.verify(hasher.hash("right password"), "wrong password")
