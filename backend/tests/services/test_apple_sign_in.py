"""AuthService.sign_in_with_apple (ADR 0019): which account a verified Apple token opens.

Token verification itself is covered in tests/test_apple.py; here the real verifier runs
against mocked Apple keys, and accounts live in in-memory fakes.
"""

import logging
from collections.abc import Callable
from typing import Any

import pytest

from app.core.errors import (
    AppleNonceMismatchError,
    AppleTokenExpiredError,
    AppleUnavailableError,
    InvalidCredentialsError,
)
from app.models import AppleIdentity
from app.services.auth import AuthService

NONCE = "a" * 64  # matches APPLE_NONCE in tests/conftest.py
SUB = "001234.abcdef0123456789.1234"
RELAY = "x7k2p9@privaterelay.appleid.com"

type MakeToken = Callable[..., str]


def test_first_sign_in_creates_an_account_with_the_name_and_apple_email(
    service: AuthService, apple_token: MakeToken, users: Any, apple_identities: Any
) -> None:
    tokens = service.sign_in_with_apple(apple_token(), NONCE, "  Ada   Lovelace ")

    user = service.authenticate(tokens.access_token)
    assert user.display_name == "Ada Lovelace"
    assert user.email is None  # no password login, so no login email
    assert user.password_hash is None
    identity = apple_identities.get_by_apple_user_id(SUB)
    assert identity.user_id == user.id
    assert identity.email == RELAY
    assert identity.is_private_email is True
    assert len(users.by_id) == 1


def test_a_blank_name_is_stored_as_none(service: AuthService, apple_token: MakeToken) -> None:
    tokens = service.sign_in_with_apple(apple_token(), NONCE, "   ")
    assert service.authenticate(tokens.access_token).display_name is None


def test_later_sign_ins_open_the_same_account_and_keep_what_apple_no_longer_sends(
    service: AuthService, apple_token: MakeToken, users: Any, apple_identities: Any
) -> None:
    first = service.sign_in_with_apple(apple_token(), NONCE, "Ada Lovelace")
    # Apple sends no name after the first time, and this token carries no email.
    later = service.sign_in_with_apple(apple_token(email=None), NONCE, None)

    user = service.authenticate(later.access_token)
    assert user.id == service.authenticate(first.access_token).id
    assert user.display_name == "Ada Lovelace"
    assert apple_identities.get_by_apple_user_id(SUB).email == RELAY
    assert len(users.by_id) == 1


def test_a_name_sent_on_a_later_sign_in_does_not_replace_the_first(
    service: AuthService, apple_token: MakeToken
) -> None:
    service.sign_in_with_apple(apple_token(), NONCE, "Ada Lovelace")
    later = service.sign_in_with_apple(apple_token(), NONCE, "Someone Else")
    assert service.authenticate(later.access_token).display_name == "Ada Lovelace"


def test_a_changed_apple_email_is_updated(
    service: AuthService, apple_token: MakeToken, apple_identities: Any
) -> None:
    service.sign_in_with_apple(apple_token(), NONCE, None)
    service.sign_in_with_apple(
        apple_token(email="ada@icloud.com", is_private_email="false"), NONCE, None
    )
    identity = apple_identities.get_by_apple_user_id(SUB)
    assert identity.email == "ada@icloud.com"
    assert identity.is_private_email is False


def test_first_sign_in_without_name_or_email_still_creates_the_account(
    service: AuthService, apple_token: MakeToken
) -> None:
    """If the first response was lost, Apple won't resend the name: the account doesn't need it."""
    tokens = service.sign_in_with_apple(apple_token(email=None), NONCE, None)
    user = service.authenticate(tokens.access_token)
    assert user.display_name is None and user.email is None


def test_different_apple_ids_get_different_accounts(
    service: AuthService, apple_token: MakeToken
) -> None:
    ada = service.sign_in_with_apple(apple_token(sub="apple-ada"), NONCE, None)
    bob = service.sign_in_with_apple(apple_token(sub="apple-bob"), NONCE, None)
    assert service.authenticate(ada.access_token).id != service.authenticate(bob.access_token).id


def test_an_apple_email_matching_a_password_account_does_not_merge_them(
    service: AuthService, apple_token: MakeToken, users: Any
) -> None:
    password_tokens = service.register("ada@icloud.com", "correct horse battery")
    apple_tokens = service.sign_in_with_apple(
        apple_token(email="ada@icloud.com", is_private_email="false"), NONCE, None
    )

    password_user = service.authenticate(password_tokens.access_token)
    apple_user = service.authenticate(apple_tokens.access_token)
    assert apple_user.id != password_user.id
    assert len(users.by_id) == 2
    # The password account still signs in by email, and still opens itself.
    again = service.login("ada@icloud.com", "correct horse battery")
    assert service.authenticate(again.access_token).id == password_user.id


def test_an_apple_only_account_cannot_be_opened_by_password_login(
    service: AuthService, apple_token: MakeToken
) -> None:
    service.sign_in_with_apple(apple_token(email="ada@icloud.com"), NONCE, None)
    with pytest.raises(InvalidCredentialsError):
        service.login("ada@icloud.com", "anything at all")


def test_a_password_account_can_still_register_after_an_apple_account_with_its_email(
    service: AuthService, apple_token: MakeToken
) -> None:
    service.sign_in_with_apple(apple_token(email="ada@icloud.com"), NONCE, None)
    tokens = service.register("ada@icloud.com", "correct horse battery")
    assert service.authenticate(tokens.access_token).email == "ada@icloud.com"


def test_a_concurrent_first_sign_in_signs_in_to_the_account_that_won(
    service: AuthService, apple_token: MakeToken, users: Any, apple_identities: Any
) -> None:
    winner = AppleIdentity(user_id=None, apple_user_id=SUB, email=RELAY, is_private_email=True)
    winner_tokens = service.sign_in_with_apple(apple_token(sub="someone-first"), NONCE, None)
    winner.user_id = service.authenticate(winner_tokens.access_token).id
    apple_identities.race_winner = winner

    tokens = service.sign_in_with_apple(apple_token(), NONCE, "Ada")

    assert service.authenticate(tokens.access_token).id == winner.user_id
    assert len(users.by_id) == 1


def test_a_rejected_token_creates_nothing_and_is_logged_without_the_token(
    service: AuthService,
    apple_token: MakeToken,
    users: Any,
    transaction: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = apple_token(nonce="not-our-nonce")
    with caplog.at_level(logging.WARNING), pytest.raises(AppleNonceMismatchError):
        service.sign_in_with_apple(token, NONCE, "Ada")
    assert users.by_id == {}
    assert transaction.commits == 0
    assert "AppleNonceMismatchError" in caplog.text
    assert token not in caplog.text


def test_an_expired_token_is_refused(
    service: AuthService, apple_token: MakeToken, clock: Any
) -> None:
    token = apple_token()
    clock.now = clock.now.replace(hour=13)  # an hour later; tokens last ten minutes
    with pytest.raises(AppleTokenExpiredError):
        service.sign_in_with_apple(token, NONCE, None)


def test_apple_being_unreachable_creates_nothing(
    service: AuthService, apple_token: MakeToken, apple_keys: Any, users: Any
) -> None:
    apple_keys.unavailable = True
    with pytest.raises(AppleUnavailableError):
        service.sign_in_with_apple(apple_token(), NONCE, None)
    assert users.by_id == {}


def test_an_apple_session_refreshes_and_logs_out_like_any_other(
    service: AuthService, apple_token: MakeToken
) -> None:
    tokens = service.sign_in_with_apple(apple_token(), NONCE, None)
    rotated = service.refresh(tokens.refresh_token)
    assert service.authenticate(rotated.access_token)
    service.logout(rotated.refresh_token)
    with pytest.raises(Exception, match="session has ended"):
        service.refresh(rotated.refresh_token)
