"""Request and response bodies for /auth. Passwords are SecretStr: never logged or echoed."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

_MAX_EMAIL_LENGTH = 320
_MAX_REFRESH_TOKEN_LENGTH = 256
_MAX_IDENTITY_TOKEN_LENGTH = 8192
_MIN_NONCE_LENGTH = 16  # the app sends 64 hex characters (32 random bytes)
_MAX_NONCE_LENGTH = 256
_MAX_NAME_LENGTH = 200


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(_Request):
    email: EmailStr = Field(max_length=_MAX_EMAIL_LENGTH)
    password: SecretStr = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class LoginRequest(_Request):
    email: EmailStr = Field(max_length=_MAX_EMAIL_LENGTH)
    # No minimum: the policy applies when a password is chosen, not when it is checked.
    password: SecretStr = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class RefreshRequest(_Request):
    refresh_token: SecretStr = Field(min_length=1, max_length=_MAX_REFRESH_TOKEN_LENGTH)


class LogoutRequest(_Request):
    refresh_token: SecretStr = Field(min_length=1, max_length=_MAX_REFRESH_TOKEN_LENGTH)


class AppleSignInRequest(_Request):
    """What the app got from Sign in with Apple, plus the nonce it made (ADR 0019)."""

    identity_token: SecretStr = Field(
        min_length=1, max_length=_MAX_IDENTITY_TOKEN_LENGTH, description="Apple's identity token."
    )
    nonce: SecretStr = Field(
        min_length=_MIN_NONCE_LENGTH,
        max_length=_MAX_NONCE_LENGTH,
        description="The raw nonce. Apple was given its SHA-256, as lowercase hex.",
    )
    full_name: str | None = Field(
        default=None,
        max_length=_MAX_NAME_LENGTH,
        description=(
            "The name Apple shared. Apple sends it only on the first sign-in, and it is "
            "used only when that sign-in creates the account."
        ),
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the access token expires.")
    refresh_token: str
