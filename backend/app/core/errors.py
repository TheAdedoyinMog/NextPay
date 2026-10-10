"""Domain errors: what went wrong, in the app's own terms.

Services raise these; ``app.api.errors`` is the one place that turns them into
HTTP responses. Each class has a stable ``code`` for clients and a default
``message`` that is safe to show to anyone: messages never say whether an
email has an account, or which credential was wrong.
"""

from typing import ClassVar


class DomainError(Exception):
    code: ClassVar[str] = "error"
    message: ClassVar[str] = "Something went wrong."

    def __init__(self, message: str | None = None) -> None:
        self.detail = message or self.message
        super().__init__(self.detail)


class InvalidInputError(DomainError):
    """A value broke a rule the schema could not check on its own."""

    code = "invalid_input"
    message = "Some of the details you entered are not valid."


class EmailUnavailableError(DomainError):
    code = "email_unavailable"
    message = "This email can't be used to create an account."


class NotFoundError(DomainError):
    """No such resource for this user.

    Another user's resource raises exactly this, so a response never says
    whether an id exists (ADR 0006).
    """

    code = "not_found"
    message = "Not found."


class ConflictError(DomainError):
    """The request is valid, but the data as it stands does not allow it."""

    code = "conflict"
    message = "This can't be done right now."


class IncomeSourceInUseError(ConflictError):
    """Paychecks and their plans are history, and they belong to this source (ADR 0010)."""

    code = "income_source_in_use"
    message = "This income source has paychecks recorded, so it can't be deleted."


class EmergencyGoalExistsError(ConflictError):
    """The planner funds one emergency fund; a second would be ambiguous."""

    code = "emergency_goal_exists"
    message = "You already have an emergency fund goal. Change that one instead."


# --- Authentication: all of these mean "who you are could not be established" ---


class AuthenticationError(DomainError):
    code = "not_authenticated"
    message = "Sign in to continue."


class InvalidCredentialsError(AuthenticationError):
    """Wrong password, unknown email, or an account with no password (Apple only)."""

    code = "invalid_credentials"
    message = "Incorrect email or password."


class InvalidAccessTokenError(AuthenticationError):
    code = "invalid_token"
    message = "The access token is not valid."


class AccessTokenExpiredError(AuthenticationError):
    """Distinct from InvalidAccessTokenError so the client knows to refresh, not re-login."""

    code = "token_expired"
    message = "The access token has expired."


class InvalidRefreshTokenError(AuthenticationError):
    """Every refresh failure looks the same to the client: sign in again.

    The subclasses exist for tests and logs, not for responses.
    """

    code = "invalid_refresh_token"
    message = "Your session has ended. Sign in again."


class RefreshTokenNotFoundError(InvalidRefreshTokenError):
    pass


class RefreshTokenExpiredError(InvalidRefreshTokenError):
    pass


class RefreshTokenReusedError(InvalidRefreshTokenError):
    """An already-rotated or revoked token came back: treat the session as stolen."""
