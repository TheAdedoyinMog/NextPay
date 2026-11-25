"""UserRepository, RefreshTokenRepository and AppleIdentityRepository against a real PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import EmailUnavailableError
from app.models import AppleIdentity, RefreshToken, User
from app.repositories import AppleIdentityRepository, RefreshTokenRepository, UserRepository

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def make_token(user: User, family_id: uuid.UUID, token_hash: str) -> RefreshToken:
    return RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        family_id=family_id,
        expires_at=NOW + timedelta(days=30),
    )


def test_users_are_found_by_id_and_by_email(db_session: Session) -> None:
    users = UserRepository(db_session)
    user = users.add(User(email="ada@example.com", password_hash="h"))
    assert users.get(user.id) is user
    assert users.get_by_email("ada@example.com") is user
    assert users.get_by_email("bob@example.com") is None
    assert users.get(uuid.uuid4()) is None


def test_a_taken_email_raises_without_breaking_the_transaction(db_session: Session) -> None:
    users = UserRepository(db_session)
    users.add(User(email="ada@example.com", password_hash="h"))
    with pytest.raises(EmailUnavailableError):
        # As if a concurrent sign-up got past the service's existence check.
        users.add(User(email="ada@example.com", password_hash="other"))
    # Only the savepoint was rolled back; the session is still usable.
    assert users.get_by_email("ada@example.com") is not None
    users.add(User(email="bob@example.com", password_hash="h"))


def test_other_integrity_errors_are_not_mistaken_for_a_taken_email(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        UserRepository(db_session).add(User(email="Not-Lowercase@example.com"))


def test_tokens_are_found_by_hash(db_session: Session) -> None:
    user = UserRepository(db_session).add(User(email="ada@example.com"))
    tokens = RefreshTokenRepository(db_session)
    token = tokens.add(make_token(user, uuid.uuid4(), "a" * 64))
    assert tokens.get_by_hash_for_update("a" * 64) is token
    assert tokens.get_by_hash_for_update("b" * 64) is None


def test_revoke_family_revokes_only_that_family_of_that_user(db_session: Session) -> None:
    users = UserRepository(db_session)
    ada = users.add(User(email="ada@example.com"))
    bob = users.add(User(email="bob@example.com"))
    tokens = RefreshTokenRepository(db_session)
    family, other_family = uuid.uuid4(), uuid.uuid4()
    tokens.add(make_token(ada, family, "1" * 64))
    tokens.add(make_token(ada, family, "2" * 64))
    tokens.add(make_token(ada, other_family, "3" * 64))
    # Bob's token claims Ada's family id: revoking for Ada must not touch it.
    tokens.add(make_token(bob, family, "4" * 64))

    assert tokens.revoke_family(ada.id, family, NOW) == 2
    assert tokens.revoke_family(ada.id, family, NOW) == 0  # already revoked

    revoked = db_session.scalars(
        select(RefreshToken.token_hash).where(RefreshToken.revoked_at.is_not(None))
    ).all()
    assert sorted(revoked) == ["1" * 64, "2" * 64]


# --- Apple identities (ADR 0019) ---------------------------------------------------------


def apple_account(apple_user_id: str = "apple-ada") -> tuple[User, AppleIdentity]:
    user = User(id=uuid.uuid4(), display_name="Ada")
    return user, AppleIdentity(user_id=user.id, apple_user_id=apple_user_id)


def test_an_apple_account_is_added_with_its_user_and_found_by_apple_id(
    db_session: Session,
) -> None:
    identities = AppleIdentityRepository(db_session)
    user, identity = apple_account()
    assert identities.add_with_user(user, identity) is True
    assert identities.get_by_apple_user_id("apple-ada") is identity
    assert identities.get_by_apple_user_id("apple-bob") is None
    assert UserRepository(db_session).get(user.id) is user
    assert user.email is None and identity.is_private_email is False


def test_a_taken_apple_id_adds_neither_row_and_keeps_the_transaction(db_session: Session) -> None:
    identities = AppleIdentityRepository(db_session)
    identities.add_with_user(*apple_account())
    loser, duplicate = apple_account()  # a concurrent first sign-in with the same Apple ID
    assert identities.add_with_user(loser, duplicate) is False
    # Only the savepoint was rolled back: the loser's user row went with it.
    assert db_session.scalar(select(User).where(User.id == loser.id)) is None
    identities.add_with_user(*apple_account("apple-bob"))


def test_an_account_has_at_most_one_apple_id(db_session: Session) -> None:
    identities = AppleIdentityRepository(db_session)
    user, _ = apple_account()
    identities.add_with_user(user, AppleIdentity(user_id=user.id, apple_user_id="first"))
    db_session.add(AppleIdentity(user_id=user.id, apple_user_id="second"))
    with pytest.raises(IntegrityError, match="uq_apple_identities_user_id"):
        db_session.flush()


def test_other_integrity_errors_are_not_mistaken_for_a_taken_apple_id(
    db_session: Session,
) -> None:
    with pytest.raises(IntegrityError):
        AppleIdentityRepository(db_session).add_with_user(
            User(id=uuid.uuid4(), email="Not-Lowercase@example.com"),
            AppleIdentity(user_id=uuid.uuid4(), apple_user_id="x"),
        )


def test_deleting_a_user_deletes_their_apple_id(db_session: Session) -> None:
    identities = AppleIdentityRepository(db_session)
    user, _ = apple_account()
    identities.add_with_user(user, AppleIdentity(user_id=user.id, apple_user_id="apple-ada"))
    db_session.delete(user)
    db_session.flush()
    db_session.expire_all()
    assert identities.get_by_apple_user_id("apple-ada") is None
