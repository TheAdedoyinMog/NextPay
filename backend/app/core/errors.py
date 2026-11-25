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


class PaycheckAlreadyCommittedError(ConflictError):
    """A committed plan is final: its paycheck cannot be planned again (ADR 0011)."""

    code = "paycheck_already_committed"
    message = "This paycheck already has a committed plan."


class PlanOutOfDateError(ConflictError):
    """Something the plan was built from has changed since, so it must be made again."""

    code = "plan_out_of_date"
    message = "Your details have changed since this plan was made. Generate a new plan."


class PlanSupersededError(ConflictError):
    code = "plan_superseded"
    message = "A newer plan replaced this one. Commit the newer plan."


class PaymentIdConflictError(ConflictError):
    """A client-made payment id that is already used by a different payment."""

    code = "payment_id_conflict"
    message = "This payment id is already used by another payment. Make a new one."


class PaymentUndoTooLateError(ConflictError):
    """A plan was committed after the payment, and planned around it (ADR 0017)."""

    code = "payment_undo_too_late"
    message = (
        "A newer plan was committed after this payment, so it can't be undone. "
        "If the payment didn't happen, correct the balance instead."
    )


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


class InvalidAppleTokenError(AuthenticationError):
    """Apple's identity token can't be trusted (ADR 0019). One public answer for every reason.

    The subclasses exist for tests and logs, not for responses.
    """

    code = "invalid_apple_token"
    message = "Sign in with Apple didn't work. Try again."


class AppleTokenMalformedError(InvalidAppleTokenError):
    pass


class AppleTokenSignatureError(InvalidAppleTokenError):
    """Not signed by any of Apple's current keys, or with an algorithm other than RS256."""


class AppleTokenClaimsError(InvalidAppleTokenError):
    """Wrong issuer or audience, or a required claim is missing."""


class AppleTokenExpiredError(InvalidAppleTokenError):
    pass


class AppleNonceMismatchError(InvalidAppleTokenError):
    """The token wasn't made for the nonce this request presented."""


# --- Services we depend on ---


class ServiceUnavailableError(DomainError):
    code = "service_unavailable"
    message = "A service NextPay depends on isn't answering. Try again in a moment."


class AppleUnavailableError(ServiceUnavailableError):
    """Apple's signing keys couldn't be fetched, so no identity token can be checked."""

    code = "apple_unavailable"
    message = "Apple isn't answering right now. Try again in a moment."
