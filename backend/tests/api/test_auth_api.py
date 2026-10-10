"""Every auth route and failure path, end to end against PostgreSQL."""

import uuid
from datetime import timedelta
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import RefreshToken

EMAIL = "ada@example.com"
PASSWORD = "correct horse battery"
API_SECRET = "api-test-secret-" + "x" * 32  # matches conftest.py

type Json = dict[str, Any]


def register(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> Json:
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return dict(response.json())


def bearer(tokens: Json) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
    return dict(body["error"])


# --- register --------------------------------------------------------------------


def test_register_signs_the_user_in(client: TestClient) -> None:
    tokens = register(client, email="  Ada@Example.com")
    assert set(tokens) == {"access_token", "token_type", "expires_in", "refresh_token"}
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 900

    me = client.get("/me", headers=bearer(tokens))
    assert me.status_code == 200
    assert set(me.json()) == {"id", "email", "timezone", "created_at"}
    assert me.json()["email"] == EMAIL
    assert me.json()["timezone"] == "UTC"


def test_register_stores_only_hashes(client: TestClient, db_session: Session) -> None:
    tokens = register(client)
    stored_password = db_session.execute(text("SELECT password_hash FROM users")).scalar_one()
    assert stored_password.startswith("$argon2id$") and PASSWORD not in stored_password
    stored_token = db_session.scalars(select(RefreshToken.token_hash)).one()
    assert stored_token != tokens["refresh_token"]


def test_register_with_a_taken_email_says_nothing_specific(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/auth/register", json={"email": "ADA@example.com", "password": "another long password"}
    )
    error = assert_error(response, 409, "email_unavailable")
    assert "already" not in error["message"].lower()
    assert "exist" not in error["message"].lower()


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"email": "not an email", "password": PASSWORD}, "email"),
        ({"email": EMAIL, "password": "short"}, "password"),
        ({"email": EMAIL, "password": "p" * 129}, "password"),
        ({"email": EMAIL}, "password"),
        ({"email": EMAIL, "password": PASSWORD, "is_admin": True}, "is_admin"),
    ],
)
def test_register_rejects_invalid_bodies(client: TestClient, body: Json, field: str) -> None:
    error = assert_error(client.post("/auth/register", json=body), 422, "validation_error")
    assert field in error["message"]


def test_a_rejected_password_is_never_echoed(client: TestClient) -> None:
    response = client.post("/auth/register", json={"email": EMAIL, "password": "hunter2!"})
    assert_error(response, 422, "validation_error")
    assert "hunter2" not in response.text


# --- login -----------------------------------------------------------------------


def test_login_returns_a_working_token_pair(client: TestClient) -> None:
    register(client)
    response = client.post("/auth/login", json={"email": "Ada@Example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert client.get("/me", headers=bearer(response.json())).json()["email"] == EMAIL


def test_wrong_password_and_unknown_email_get_the_same_answer(client: TestClient) -> None:
    register(client)
    wrong_password = client.post(
        "/auth/login", json={"email": EMAIL, "password": "not the password"}
    )
    unknown_email = client.post(
        "/auth/login", json={"email": "bob@example.com", "password": PASSWORD}
    )
    assert_error(wrong_password, 401, "invalid_credentials")
    assert wrong_password.json() == unknown_email.json()
    assert unknown_email.status_code == 401


# --- refresh -------------------------------------------------------------------


def test_refresh_returns_a_new_pair(client: TestClient) -> None:
    tokens = register(client)
    response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]
    assert client.get("/me", headers=bearer(rotated)).json()["email"] == EMAIL


def test_a_reused_refresh_token_ends_the_session(client: TestClient) -> None:
    tokens = register(client)
    rotated = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()

    reused = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert_error(reused, 401, "invalid_refresh_token")

    # The family was revoked and committed even though that request failed, so the
    # newest token no longer works either.
    newest = client.post("/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert_error(newest, 401, "invalid_refresh_token")


def test_an_expired_refresh_token_is_rejected(client: TestClient, clock: Any) -> None:
    tokens = register(client)
    clock.advance(timedelta(days=30))
    response = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert_error(response, 401, "invalid_refresh_token")


def test_every_refresh_failure_looks_the_same(client: TestClient, clock: Any) -> None:
    ada, bob = register(client), register(client, "bob@example.com")
    client.post("/auth/refresh", json={"refresh_token": ada["refresh_token"]})
    reused = client.post("/auth/refresh", json={"refresh_token": ada["refresh_token"]})
    unknown = client.post("/auth/refresh", json={"refresh_token": "never-issued"})
    clock.advance(timedelta(days=30))
    expired = client.post("/auth/refresh", json={"refresh_token": bob["refresh_token"]})
    for response in (reused, unknown, expired):
        assert_error(response, 401, "invalid_refresh_token")
    assert reused.json() == unknown.json() == expired.json()


# --- logout --------------------------------------------------------------------


def test_logout_ends_the_session(client: TestClient) -> None:
    tokens = register(client)
    response = client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 204
    assert response.content == b""
    after = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert_error(after, 401, "invalid_refresh_token")


def test_logout_succeeds_for_any_token(client: TestClient) -> None:
    response = client.post("/auth/logout", json={"refresh_token": "never-issued"})
    assert response.status_code == 204


def test_an_access_token_outlives_logout_until_it_expires(client: TestClient, clock: Any) -> None:
    """Documented tradeoff (ADR 0009): access tokens are not looked up, so they stay
    valid for at most their 15 minutes after logout."""
    tokens = register(client)
    client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert client.get("/me", headers=bearer(tokens)).status_code == 200
    clock.advance(timedelta(minutes=15))
    assert_error(client.get("/me", headers=bearer(tokens)), 401, "token_expired")


# --- the protected route -------------------------------------------------------


def test_me_without_a_token_is_rejected(client: TestClient) -> None:
    assert_error(client.get("/me"), 401, "not_authenticated")


def test_me_with_another_auth_scheme_is_rejected(client: TestClient) -> None:
    response = client.get("/me", headers={"Authorization": "Basic YWRhOnB3"})
    assert_error(response, 401, "not_authenticated")


def test_me_with_a_garbage_token_is_rejected(client: TestClient) -> None:
    response = client.get("/me", headers={"Authorization": "Bearer not-a-token"})
    assert_error(response, 401, "invalid_token")


def test_me_with_an_expired_token_says_so(client: TestClient, clock: Any) -> None:
    tokens = register(client)
    clock.advance(timedelta(minutes=15))
    assert_error(client.get("/me", headers=bearer(tokens)), 401, "token_expired")


def test_me_with_a_refresh_token_is_rejected(client: TestClient) -> None:
    tokens = register(client)
    response = client.get("/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert_error(response, 401, "invalid_token")


# --- one user cannot act as another ----------------------------------------------


def forged(sub: str, secret: str = API_SECRET, algorithm: str = "HS256") -> dict[str, str]:
    claims = {
        "sub": sub,
        "iat": 1_791_400_000,
        "exp": 1_891_400_000,
        "iss": "nextpay",
        "aud": "nextpay-api",
    }
    token = jwt.encode(claims, secret if algorithm != "none" else None, algorithm=algorithm)
    return {"Authorization": f"Bearer {token}"}


def test_each_users_token_shows_only_that_user(client: TestClient) -> None:
    ada, bob = register(client), register(client, "bob@example.com")
    assert client.get("/me", headers=bearer(ada)).json()["email"] == EMAIL
    assert client.get("/me", headers=bearer(bob)).json()["email"] == "bob@example.com"


def test_a_token_naming_another_user_needs_our_signature(client: TestClient) -> None:
    register(client)
    bob_id = client.get("/me", headers=bearer(register(client, "bob@example.com"))).json()["id"]

    signed_elsewhere = forged(bob_id, secret="attacker-secret-" + "y" * 32)
    assert_error(client.get("/me", headers=signed_elsewhere), 401, "invalid_token")
    unsigned = forged(bob_id, algorithm="none")
    assert_error(client.get("/me", headers=unsigned), 401, "invalid_token")


def test_a_validly_signed_token_for_a_missing_user_is_rejected(client: TestClient) -> None:
    # Proves the user is loaded, not trusted from the token: a deleted account's
    # unexpired token stops working at once.
    response = client.get("/me", headers=forged(str(uuid.uuid4())))
    assert_error(response, 401, "invalid_token")
