"""AuthService rules, with in-memory fakes (see conftest.py): no database needed."""

from datetime import timedelta
from typing import Any

import argon2
import pytest

from app.core.errors import (
    AccessTokenExpiredError,
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
    PasswordHasher,
    hash_refresh_token,
)
from app.models import User
from app.services.auth import AuthService

PASSWORD = "correct horse battery"
EMAIL = "ada@example.com"

# The fakes are fixtures from conftest.py, so they are typed loosely here.
type Fake = Any


def token_for(refresh_tokens: Fake, raw: str) -> Any:
    return refresh_tokens.get_by_hash_for_update(hash_refresh_token(raw))


# --- register ------------------------------------------------------------------


def test_register_creates_the_user_and_signs_them_in(
    service: AuthService, users: Fake, refresh_tokens: Fake, transaction: Fake
) -> None:
    tokens = service.register(EMAIL, PASSWORD)

    (user,) = users.by_id.values()
    assert user.email == EMAIL
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash
    assert service.authenticate(tokens.access_token) is user
    assert tokens.expires_in == 15 * 60
    (stored,) = refresh_tokens.all
    assert stored.token_hash == hash_refresh_token(tokens.refresh_token)
    assert stored.token_hash != tokens.refresh_token  # only the hash is stored
    assert transaction.commits == 1


def test_register_normalizes_the_email(service: AuthService, users: Fake) -> None:
    service.register("  Ada@Example.COM ", PASSWORD)
    assert [user.email for user in users.by_id.values()] == [EMAIL]


@pytest.mark.parametrize("email", ["", "ada", "ada@", "@example.com", "ada example@x.com"])
def test_register_rejects_an_invalid_email(service: AuthService, email: str) -> None:
    with pytest.raises(InvalidInputError, match="valid email"):
        service.register(email, PASSWORD)


@pytest.mark.parametrize("length", [0, MIN_PASSWORD_LENGTH - 1, MAX_PASSWORD_LENGTH + 1])
def test_register_rejects_a_password_of_the_wrong_length(service: AuthService, length: int) -> None:
    with pytest.raises(InvalidInputError, match="12 to 128 characters"):
        service.register(EMAIL, "p" * length)


@pytest.mark.parametrize("length", [MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH])
def test_register_accepts_passwords_at_the_length_limits(service: AuthService, length: int) -> None:
    service.register(EMAIL, "p" * length)


def test_register_refuses_a_taken_email_in_any_case(
    service: AuthService, transaction: Fake, hasher: PasswordHasher, monkeypatch: Any
) -> None:
    service.register(EMAIL, PASSWORD)
    hashed: list[str] = []
    original = hasher.hash
    monkeypatch.setattr(hasher, "hash", lambda pw: hashed.append(pw) or original(pw))

    with pytest.raises(EmailUnavailableError):
        service.register("ADA@example.com", "another long password")
    assert hashed == ["another long password"]  # hashed anyway: no timing difference
    assert transaction.commits == 1  # only the first registration


# --- login -----------------------------------------------------------------------


def test_login_with_the_right_password_starts_a_new_session(
    service: AuthService, refresh_tokens: Fake
) -> None:
    first = service.register(EMAIL, PASSWORD)
    second = service.login(" ADA@example.com", PASSWORD)

    assert service.authenticate(second.access_token).email == EMAIL
    families = {token_for(refresh_tokens, t.refresh_token).family_id for t in (first, second)}
    assert len(families) == 2  # each login is its own session


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (EMAIL, "wrong password here"),
        ("bob@example.com", PASSWORD),  # no such account
        ("not an email", PASSWORD),
    ],
)
def test_login_failures_all_look_the_same(
    service: AuthService, email: str, password: str, transaction: Fake
) -> None:
    service.register(EMAIL, PASSWORD)
    with pytest.raises(InvalidCredentialsError) as error:
        service.login(email, password)
    assert error.value.detail == "Incorrect email or password."
    assert transaction.commits == 1


def test_login_for_an_unknown_email_still_checks_a_password(
    service: AuthService, hasher: PasswordHasher, monkeypatch: Any
) -> None:
    checked: list[str] = []
    monkeypatch.setattr(hasher, "verify_dummy", checked.append)
    with pytest.raises(InvalidCredentialsError):
        service.login("bob@example.com", PASSWORD)
    assert checked == [PASSWORD]


def test_an_account_without_a_password_cannot_log_in_with_one(
    service: AuthService, users: Fake
) -> None:
    users.add(User(email=EMAIL, password_hash=None))  # e.g. Sign in with Apple, later
    with pytest.raises(InvalidCredentialsError):
        service.login(EMAIL, PASSWORD)


def test_login_upgrades_a_hash_made_with_older_parameters(
    service: AuthService, users: Fake, hasher: PasswordHasher
) -> None:
    old = argon2.PasswordHasher(time_cost=2, memory_cost=8, parallelism=1).hash(PASSWORD)
    user = users.add(User(email=EMAIL, password_hash=old))

    service.login(EMAIL, PASSWORD)

    assert user.password_hash != old
    assert not hasher.needs_rehash(user.password_hash)
    assert hasher.verify(user.password_hash, PASSWORD)


# --- refresh -------------------------------------------------------------------


def test_refresh_rotates_the_token_within_its_family(
    service: AuthService, refresh_tokens: Fake, clock: Fake, transaction: Fake
) -> None:
    first = service.register(EMAIL, PASSWORD)
    clock.advance(timedelta(days=29))

    second = service.refresh(first.refresh_token)

    old, new = token_for(refresh_tokens, first.refresh_token), refresh_tokens.all[-1]
    assert new.token_hash == hash_refresh_token(second.refresh_token)
    assert old.replaced_by_id == new.id
    assert old.revoked_at is None  # rotated, not revoked
    assert new.family_id == old.family_id
    assert new.expires_at == clock.now + timedelta(days=30)  # sliding expiry
    assert service.authenticate(second.access_token).email == EMAIL
    assert transaction.commits == 2


def test_a_rotated_token_coming_back_revokes_the_whole_family(
    service: AuthService, refresh_tokens: Fake, transaction: Fake
) -> None:
    first = service.register(EMAIL, PASSWORD)
    second = service.refresh(first.refresh_token)
    other_session = service.login(EMAIL, PASSWORD)
    commits = transaction.commits

    with pytest.raises(RefreshTokenReusedError):
        service.refresh(first.refresh_token)  # the stolen copy, or the victim's

    assert transaction.commits == commits + 1  # the revocation is kept despite the error
    family = token_for(refresh_tokens, first.refresh_token).family_id
    assert all(t.revoked_at for t in refresh_tokens.all if t.family_id == family)
    with pytest.raises(RefreshTokenReusedError):
        service.refresh(second.refresh_token)  # the newest token died with its family
    service.refresh(other_session.refresh_token)  # other sessions are untouched


def test_a_revoked_token_coming_back_is_treated_as_reuse(service: AuthService) -> None:
    tokens = service.register(EMAIL, PASSWORD)
    service.logout(tokens.refresh_token)
    with pytest.raises(RefreshTokenReusedError):
        service.refresh(tokens.refresh_token)


def test_reuse_is_detected_even_after_the_rotated_token_expired(
    service: AuthService, clock: Fake
) -> None:
    first = service.register(EMAIL, PASSWORD)
    service.refresh(first.refresh_token)
    clock.advance(timedelta(days=31))
    with pytest.raises(RefreshTokenReusedError):
        service.refresh(first.refresh_token)


def test_an_unknown_refresh_token_is_rejected(service: AuthService) -> None:
    with pytest.raises(RefreshTokenNotFoundError):
        service.refresh("not-a-token-we-issued")


def test_a_refresh_token_expires_after_thirty_days(service: AuthService, clock: Fake) -> None:
    tokens = service.register(EMAIL, PASSWORD)
    clock.advance(timedelta(days=30))
    with pytest.raises(RefreshTokenExpiredError):
        service.refresh(tokens.refresh_token)


def test_a_refresh_token_works_until_just_before_it_expires(
    service: AuthService, clock: Fake
) -> None:
    tokens = service.register(EMAIL, PASSWORD)
    clock.advance(timedelta(days=30) - timedelta(seconds=1))
    service.refresh(tokens.refresh_token)


# --- logout --------------------------------------------------------------------


def test_logout_ends_only_this_session(service: AuthService, refresh_tokens: Fake) -> None:
    phone = service.register(EMAIL, PASSWORD)
    rotated = service.refresh(phone.refresh_token)
    tablet = service.login(EMAIL, PASSWORD)

    service.logout(rotated.refresh_token)

    family = token_for(refresh_tokens, phone.refresh_token).family_id
    assert all(t.revoked_at for t in refresh_tokens.all if t.family_id == family)
    with pytest.raises(RefreshTokenReusedError):
        service.refresh(rotated.refresh_token)
    service.refresh(tablet.refresh_token)


def test_logout_with_an_unknown_token_does_nothing(service: AuthService, transaction: Fake) -> None:
    service.logout("not-a-token-we-issued")
    assert transaction.commits == 0


def test_logout_twice_is_harmless(service: AuthService) -> None:
    tokens = service.register(EMAIL, PASSWORD)
    service.logout(tokens.refresh_token)
    service.logout(tokens.refresh_token)


# --- authenticate ----------------------------------------------------------------


def test_an_access_token_expires_after_fifteen_minutes(service: AuthService, clock: Fake) -> None:
    tokens = service.register(EMAIL, PASSWORD)
    clock.advance(timedelta(minutes=15) - timedelta(seconds=1))
    service.authenticate(tokens.access_token)
    clock.advance(timedelta(seconds=1))
    with pytest.raises(AccessTokenExpiredError):
        service.authenticate(tokens.access_token)


def test_an_access_token_for_a_deleted_user_is_rejected(service: AuthService, users: Fake) -> None:
    tokens = service.register(EMAIL, PASSWORD)
    users.by_id.clear()
    with pytest.raises(InvalidAccessTokenError):
        service.authenticate(tokens.access_token)


def test_a_refresh_token_is_not_an_access_token(service: AuthService) -> None:
    tokens = service.register(EMAIL, PASSWORD)
    with pytest.raises(InvalidAccessTokenError):
        service.authenticate(tokens.refresh_token)
