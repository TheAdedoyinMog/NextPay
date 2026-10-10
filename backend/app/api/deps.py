"""FastAPI dependencies: how routes get services and the current user.

Each piece is its own dependency so tests can override it (a cheaper hasher, a
controllable clock, a rollback session).
"""

from datetime import timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.clock import Clock, utc_now
from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError
from app.core.security import AccessTokenCodec, PasswordHasher
from app.db.session import get_session
from app.models import User
from app.repositories import RefreshTokenRepository, UserRepository
from app.services.auth import AuthService


def get_clock() -> Clock:
    return utc_now


@lru_cache
def get_password_hasher() -> PasswordHasher:
    return PasswordHasher()


def get_auth_service(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AuthService:
    return AuthService(
        users=UserRepository(session),
        refresh_tokens=RefreshTokenRepository(session),
        transaction=session,
        hasher=hasher,
        access_tokens=AccessTokenCodec(
            settings.jwt_secret.get_secret_value(),
            timedelta(minutes=settings.access_token_ttl_minutes),
        ),
        refresh_token_ttl=timedelta(days=settings.refresh_token_ttl_days),
        clock=clock,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

# auto_error=False: a missing or non-Bearer header gets our own error envelope.
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth: AuthServiceDep,
) -> User:
    """The user whose access token came with the request; 401 otherwise."""
    if credentials is None:
        raise AuthenticationError()
    return auth.authenticate(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]
