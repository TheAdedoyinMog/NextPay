# 0009. Auth token lifecycle, logout scope, and pre-Beta security gates

- Status: Accepted
- Date: 2026-10-07

## Context
ADR 0006 chose email/password with argon2, short-lived JWT access tokens, and rotating
refresh tokens stored hashed. Milestone 2B implements them and has to settle the details:
what each token is, what happens when a refresh token is stolen, what logout ends, and
what is acceptable before NextPay is reachable from the internet.

## Decision
- **Access tokens** are JWTs signed with HS256 (`NEXTPAY_JWT_SECRET`, at least 32 characters,
  never defaulted), valid for 15 minutes, with `sub`, `iat`, `exp`, `iss` and `aud`. Decoding
  pins the algorithm, so `alg: none` and algorithm confusion are rejected. Every request
  loads the user, so a deleted account's token stops working at once.
- **Refresh tokens** are opaque 256-bit random strings, not JWTs. Only their SHA-256 is
  stored: they are high-entropy, so a slow hash adds nothing, and lookup is by hash. They
  last 30 days, renewed on each refresh (sliding).
- **Sessions are token families.** Each login starts a family; each refresh rotates the
  token (the old one gets `replaced_by_id`, the new one joins the family). The token row
  is locked during a refresh, so concurrent refreshes with one token are serialized.
- **Reuse means theft.** A rotated or revoked token that comes back revokes its whole
  family, and that revocation is committed even though the request fails. Reuse is
  checked before expiry. It is logged as a warning (user and family ids, never tokens).
  There is no grace window: the mobile client must not refresh concurrently.
- **Logout ends this session**: it revokes the presented token's family, so other devices
  stay signed in. It always returns 204, so it can't be used to test tokens. "Log out
  everywhere" waits for password change and reset, where it belongs.
- **Failures say little.** Login returns one 401 for a wrong password, an unknown email, or
  an account without a password, and checks a dummy hash so the timing matches. Every
  refresh failure (unknown, expired, revoked, reused) returns the same 401 publicly; the
  distinct error classes exist for tests and logs. Expired access tokens get their own
  code (`token_expired`) so the client refreshes instead of signing in again.
- **Passwords** are 12 to 128 characters with no composition rules (NIST SP 800-63B), hashed
  with argon2id at argon2-cffi's RFC 9106 defaults, and rehashed on login when those
  parameters are raised.
- **Migrations need no secrets**: they read `DatabaseSettings` only; the API's `Settings`
  adds the auth values.

## Consequences
- A stolen refresh token works at most until either party refreshes; then both are
  signed out and the theft is logged.
- An access token stays valid for up to 15 minutes after logout or revocation. That is
  the price of not looking tokens up on every request.
- **Pre-Beta requirement: rate limiting on `/auth/*`.** Without it, attackers can guess
  passwords freely, and each argon2 hash costs 64 MiB, so login is a cheap way to exhaust
  memory. Deferred to Phase 4 (production engineering), and it must exist before any
  public deployment in Phase 5.
- **Pre-Beta requirement: email-verified signup.** Registration reveals whether an email
  already has an account: whatever the message says, failing for a taken email is the
  signal. The response is generic and its timing matches, but only a "check your inbox"
  flow, where register answers the same for new and taken emails, closes the gap. Real
  signup must gate on email verification before public deployment.
- Deferred with them: password change and reset, "log out everywhere", a breached-password
  check, and Sign in with Apple (its own migration, per ADR 0006).
