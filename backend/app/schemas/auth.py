"""Request and response bodies for /auth. Passwords are SecretStr: never logged or echoed."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

_MAX_EMAIL_LENGTH = 320
_MAX_REFRESH_TOKEN_LENGTH = 256


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


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the access token expires.")
    refresh_token: str
