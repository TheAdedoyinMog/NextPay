"""POST /auth/apple end to end against PostgreSQL, with Apple's keys mocked (ADR 0019)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AppleIdentity, User

NONCE = "a" * 64  # matches APPLE_NONCE in tests/conftest.py
RELAY = "x7k2p9@privaterelay.appleid.com"

type Json = dict[str, Any]
type MakeToken = Callable[..., str]


def apple(client: TestClient, token: str, nonce: str = NONCE, **extra: Any) -> Any:
    return client.post("/auth/apple", json={"identity_token": token, "nonce": nonce, **extra})


def signed_in(response: Any) -> Json:
    assert response.status_code == 200, response.text
    return dict(response.json())


def me(client: TestClient, tokens: Json) -> Json:
    response = client.get("/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 200, response.text
    return dict(response.json())


def assert_rejected(response: Any) -> None:
    assert response.status_code == 401, response.text
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "error": {
            "code": "invalid_apple_token",
            "message": "Sign in with Apple didn't work. Try again.",
        }
    }


def count(db_session: Session, model: type[Any]) -> int:
    return db_session.scalar(select(func.count()).select_from(model)) or 0


def test_first_sign_in_creates_the_account(
    client: TestClient, apple_token: MakeToken, db_session: Session
) -> None:
    tokens = signed_in(apple(client, apple_token(), full_name="Ada Lovelace"))

    assert set(tokens) == {"access_token", "token_type", "expires_in", "refresh_token"}
    assert tokens["expires_in"] == 900
    user = me(client, tokens)
    assert user["email"] is None
    assert user["display_name"] == "Ada Lovelace"
    identity = db_session.scalars(select(AppleIdentity)).one()
    assert identity.email == RELAY and identity.is_private_email is True
    assert str(identity.user_id) == user["id"]


def test_later_sign_ins_open_the_same_account(
    client: TestClient, apple_token: MakeToken, db_session: Session
) -> None:
    first = me(client, signed_in(apple(client, apple_token(), full_name="Ada Lovelace")))
    later = me(client, signed_in(apple(client, apple_token(email=None))))

    assert later["id"] == first["id"]
    assert later["display_name"] == "Ada Lovelace"
    assert count(db_session, User) == 1
    assert db_session.scalars(select(AppleIdentity.email)).one() == RELAY


def test_an_apple_session_refreshes_and_logs_out(
    client: TestClient, apple_token: MakeToken
) -> None:
    tokens = signed_in(apple(client, apple_token()))
    refreshed = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    rotated = refreshed.json()["refresh_token"]
    assert client.post("/auth/logout", json={"refresh_token": rotated}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": rotated}).status_code == 401


def test_an_apple_account_with_a_password_accounts_email_stays_separate(
    client: TestClient, apple_token: MakeToken, db_session: Session
) -> None:
    password = {"email": "ada@icloud.com", "password": "correct horse battery"}
    registered = client.post("/auth/register", json=password)
    assert registered.status_code == 201
    token = apple_token(email="ada@icloud.com", is_private_email="false")

    apple_user = me(client, signed_in(apple(client, token)))
    password_user = me(client, signed_in(client.post("/auth/login", json=password)))

    assert apple_user["id"] != password_user["id"]
    assert apple_user["email"] is None
    assert password_user["email"] == "ada@icloud.com"
    assert count(db_session, User) == 2


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"exp": 1_791_374_400}, id="expired"),  # exactly the fake clock's now
        pytest.param({"aud": "com.someone.else"}, id="wrong-audience"),
        pytest.param({"iss": "https://evil.example"}, id="wrong-issuer"),
        pytest.param({"nonce": "0" * 64}, id="nonce-mismatch"),
        pytest.param({"kid": "unpublished"}, id="unknown-key"),
    ],
)
def test_an_untrustworthy_token_is_rejected_and_creates_nothing(
    client: TestClient, apple_token: MakeToken, db_session: Session, overrides: Json
) -> None:
    assert_rejected(apple(client, apple_token(**overrides)))
    assert count(db_session, User) == 0


def test_a_token_signed_by_someone_else_is_rejected(
    client: TestClient, apple_token: MakeToken, other_private_key: Any, db_session: Session
) -> None:
    assert_rejected(apple(client, apple_token(key=other_private_key)))
    assert count(db_session, User) == 0


def test_the_wrong_raw_nonce_is_rejected(client: TestClient, apple_token: MakeToken) -> None:
    assert_rejected(apple(client, apple_token(), nonce="b" * 64))


def test_apple_being_unreachable_is_a_503(
    client: TestClient, apple_token: MakeToken, apple_keys: Any
) -> None:
    apple_keys.unavailable = True
    response = apple(client, apple_token())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "apple_unavailable"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"nonce": NONCE}, id="no-token"),
        pytest.param({"identity_token": "t"}, id="no-nonce"),
        pytest.param({"identity_token": "t", "nonce": "short"}, id="short-nonce"),
        pytest.param({"identity_token": "t", "nonce": NONCE, "email": "a@b.c"}, id="extra-field"),
        pytest.param({"identity_token": "t", "nonce": NONCE, "full_name": "x" * 201}, id="long"),
    ],
)
def test_a_malformed_request_is_a_422(client: TestClient, body: Json) -> None:
    response = client.post("/auth/apple", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_the_identity_token_and_nonce_are_never_echoed(client: TestClient) -> None:
    secret = "s3cr3t-" * 10
    response = client.post("/auth/apple", json={"identity_token": secret, "nonce": "short"})
    assert secret not in response.text and "short" not in response.text


def test_password_users_show_their_email_and_no_name(
    client: TestClient, ada: dict[str, str]
) -> None:
    user = client.get("/me", headers=ada).json()
    assert user["email"] == "ada@example.com"
    assert user["display_name"] is None
