# 0013. Mobile sessions: token storage, single-flight refresh, and sign-out rules

- Status: Accepted
- Date: 2026-11-14

## Context
Milestone 3B adds sign-in to the app. The backend rotates refresh tokens and treats a reused
one as theft, revoking the whole session with no grace window (ADR 0009). So the client must
never refresh twice with the same token, even when several requests hit a 401 at once. The
app is used on phones, which lose signal often, and a dropped connection must not look like
being signed out. ADR 0012 named `expo-secure-store` for tokens but left the details here.

## Decision

### Where tokens live
- **The refresh token is kept in the iOS Keychain** through `expo-secure-store`, with
  `WHEN_UNLOCKED_THIS_DEVICE_ONLY`. "This device only" keeps it out of backups, so restoring a
  backup to another phone carries no session.
- **The access token is kept in memory only.** It lasts 15 minutes, so storing it would buy
  one saved request per launch at the cost of a second secret at rest.

### What "signed in" means
- **Signed in means holding a refresh token the server hasn't rejected.** Launch reads the
  Keychain and decides from that alone. The splash stays up only for that read, never for
  the network. An offline launch therefore opens the app (signed in) instead of hanging on
  the splash or signing out.
- **The first request after launch refreshes before it is sent**, because there is no access
  token yet. A launch whose session was revoked shows the home screen briefly, then sign-in
  with "Your session has ended."

### Refresh
- **All HTTP still goes through `src/api/client.ts`.** It attaches the access token and, on a
  401 from any route outside `/auth/`, asks the session for a new token and retries the
  request **once**. `/auth/*` routes never trigger a refresh: their 401 means wrong
  credentials.
- **Refresh is single-flight.** `src/api/session.ts` keeps one refresh promise, and every
  caller that needs a refresh awaits it.
- **A late 401 doesn't refresh again.** Each request remembers the token it was sent with. If
  its 401 arrives after another request already refreshed, it retries with the newer token.
- **An epoch counter guards against races.** It goes up at every sign-in and sign-out. A
  refresh that finishes in a different epoch from the one it started in is discarded, so a
  refresh that completes after logout can't write a token back.
- **The rotated refresh token is written to the Keychain as soon as it arrives.**

### What signs a user out
- **Only two things: a 401 from `/auth/refresh`, or the user logging out.**
- **Network errors, timeouts and 5xx never sign anyone out.** Network errors and timeouts get
  separate codes (`network_error`, `timeout`) and messages, and the home screen adds "You're
  still signed in." A 401 on a retried request (the token was just refreshed) is shown as an
  error, not treated as a sign-out.

### Logout
- **Local first, then the backend.** Logout clears the Keychain, memory and the query cache
  at once, then calls `/auth/logout` without waiting for it. Offline logout still works. The
  token is gone from the phone, and the backend session expires with it.
- **The whole TanStack Query cache (queries and mutations) is cleared whenever the session
  becomes signed out**, for any reason. A session listener does this before any screen
  re-renders, so the next account never sees the previous one's data.

### Routing
- **Expo Router's `Stack.Protected` guards two groups.** `(app)` is for signed-in users and
  `(auth)` (sign-in, sign-up) for everyone else. Each guard has an explicit `redirectTo`
  (without one, a signed-out launch at `/` showed "Unmatched Route").

## Consequences
- **No new native code.** `expo-secure-store` and `expo-splash-screen` were already in the 3A
  development build.
- **Tests run against a fake backend that enforces rotation and reuse detection.** If the
  client ever refreshed twice with one token, the fake revokes the session and the
  concurrency tests fail. Disabling single-flight was confirmed to fail them.
- **A narrow window remains between the server rotating a token and the Keychain write.** If
  the app is killed in that gap, the next launch presents the old token. The backend then
  revokes the session, and the user signs in again. Safe, but annoying; it's rare.
  Accepted.
- **iOS keeps Keychain items after the app is deleted.** A reinstall can therefore find an old
  session and restore it. The backend still decides whether that token is valid, but a user
  who deleted the app expects to be signed out. **Must fix before beta:** scheduled for 3E,
  which needs a new EAS build anyway. The usual fix is a first-run flag in non-Keychain
  storage that clears the Keychain on a fresh install.
- **An offline logout leaves the backend session alive until it expires (30 days, sliding),**
  but nothing on the phone can use it. Accepted.
- **Every launch rotates the refresh token once,** on the first request.
