"""UserRepository and RefreshTokenRepository against a real PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import EmailUnavailableError
from app.models import RefreshToken, User
from app.repositories import RefreshTokenRepository, UserRepository

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
