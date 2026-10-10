"""Models and service results to response schemas, field by field.

Explicit on purpose: a new model column (a password hash, say) can only reach
a response if someone adds it here.
"""

from app.models import User
from app.schemas.auth import TokenResponse
from app.schemas.user import UserResponse
from app.services.auth import TokenPair


def to_token_response(tokens: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token,
    )


def to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id, email=user.email, timezone=user.timezone, created_at=user.created_at
    )
