# 0006. Email/password with JWT, plus Sign in with Apple

- Status: Accepted
- Date: 2026-10-06

## Context
NextPay ships on iOS and holds sensitive financial data.

## Decision
Email/password accounts with argon2 password hashing, short-lived JWT access tokens, and
rotating refresh tokens stored hashed in the database. Sign in with Apple is also offered.
Every query is scoped by user_id; another user resource returns 404.

## Consequences
- Full control and no auth vendor cost.
- We own token rotation, revocation, and rate limiting on auth endpoints, so these get
  dedicated tests.
