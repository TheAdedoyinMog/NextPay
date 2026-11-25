# 0019. Sign in with Apple, account linking, and the fresh-install sign-out

- Status: Accepted
- Date: 2026-11-24

## Context
ADR 0006 promised Sign in with Apple next to email/password, and ADR 0009 deferred it to its
own migration. Milestone 3E builds it. The app signs in natively (`expo-apple-authentication`)
and gets an **identity token** from Apple: a JWT signed by Apple, valid for minutes. The backend
must decide whether to trust it, and which NextPay account it opens.

Apple's quirks shape the design:
- `sub` is the stable user ID for our app. It never changes, even if the user changes the
  email they share.
- Apple gives the app the user's **name only on the first authorization**, and never again,
  even after the user deletes the app. The token never carries the name.
- The email may be a **private relay** address (`…@privaterelay.appleid.com`), and the user can
  turn the relay off or change where it forwards.
- Our email/password signup does **not verify emails** yet (ADR 0009, pre-beta gate).

ADR 0013 also left one problem for this milestone: iOS keeps Keychain items after an app is
deleted, so a reinstalled app found the old refresh token and restored the session.

## Decision

### Verifying the identity token
- **The app makes the nonce.** For each sign-in it creates 32 random bytes (hex), passes
  `SHA-256(raw)` to Apple, and sends `raw` to `POST /auth/apple`. The backend hashes `raw` and
  compares it with the token's `nonce` claim in constant time. The raw value is in no token, so
  a token that leaks from a log or crash report can't be replayed by itself.
- **Checked every time:** signature against Apple's published keys
  (`https://appleid.apple.com/auth/keys`), algorithm pinned to RS256, `iss` =
  `https://appleid.apple.com`, `aud` = our bundle ID (`NEXTPAY_APPLE_BUNDLE_ID`, default
  `com.theadedoyinmog.nextpay`), `exp` against the backend's injected clock (as for access
  tokens, so tests control time), and `sub`, `iat`, `nonce` required.
- **Apple's keys are fetched with PyJWT's `PyJWKClient`** and cached in the process. A token
  with an unknown `kid` (Apple rotated its keys) refetches the key set, at most once per 30
  seconds. If Apple can't be reached, the answer is **503 `apple_unavailable`**, not 401. The
  user did nothing wrong, and the app says so.
- **Every verification failure is one public 401, `invalid_apple_token`.** Distinct exception
  classes (expired, wrong audience, nonce mismatch, …) exist for tests and logs only, as for
  refresh tokens (ADR 0009). A failure is logged as a warning with its class, never the token.

### Which account a token opens
- **An Apple account is found by Apple's `sub` alone, never by email.** A new table,
  `apple_identities`, holds `apple_user_id` (unique) and `user_id` (unique: one Apple ID per
  NextPay account), plus the email Apple last reported and whether it is a private relay.
- **`users.email` becomes nullable and means "the email you sign in with by password."** An
  account made with Apple has no email and no password there. Its Apple email is kept on the
  identity row as contact information, and nothing looks accounts up by it.
- **First sign-in creates the account.** The account doesn't depend on anything Apple sends
  only once. If the first response is lost, the next sign-in still finds or creates the account
  by `sub`. Only the name would be lost.
- **The name** comes from the app (Apple gives it only to the app, only the first time). It is
  saved as `users.display_name` when the account is created, and never overwritten after
  that: later sign-ins carry no name.
- **The email comes from the token, never from the request body.** It is stored when present
  and updated whenever a later token carries a different one (the user changed their relay
  settings). A token without an email is fine.
- **Two first sign-ins racing** (a double tap) both try to create the account. The database's
  unique `apple_user_id` lets one win, and the other signs in to the winner's account.
- **Sessions are the same as email/password.** `/auth/apple` returns the usual `TokenResponse`
  and starts a refresh-token family (ADR 0009). The app stores it the same way (ADR 0013).

### No automatic linking by email
- **An Apple sign-in whose email matches a password account creates a separate account.**
  Merging on email would let anyone take over a future Apple user's account: register a
  password account with the victim's address (we don't verify emails), wait for the victim to
  sign in with Apple, and share the account, including everything the victim enters. Apple's
  `email_verified` proves the Apple side, not ours.
- **Linking will be explicit.** A signed-in user proves they hold the Apple ID, and an
  `apple_identities` row is added to their account. The schema needs no change for that. It is
  **not built in 3E**: no user needs it yet, and the hard case (the Apple ID already has its own
  account with data) needs a design of its own.
- `GET /me` returns `email` (null for an Apple-only account) and `display_name`. The app shows
  the name, then the email, then "your Apple ID".

### Fresh install signs out (the stale Keychain fix)
- **At launch, before reading the Keychain, `session.restore()` looks for a marker file**
  (`nextpay-installed`) in the app's Documents directory, through `expo-file-system`. iOS deletes
  that directory with the app. The Keychain survives.
- **No marker means a fresh install:** delete the stored refresh token, *then* write the marker,
  and start signed out. The order makes it safe to stop halfway: if the app dies between the
  two, the next launch simply clears again. If the delete fails, the marker is not written, and
  the launch is signed out anyway.
- **`expo-file-system` over AsyncStorage:** it is already a dependency of `expo` and already in
  the native build, and one marker file needs nothing more.

## Consequences
- **One person can end up with two accounts** (Apple and password) if they use both. Accepted
  until linking exists. The sign-in screen offers both, so this is a real possibility.
- **Installing the 3E build over an older build signs the user out once.** An upgrade from a
  build that never wrote the marker looks exactly like a reinstall.
- **Restoring a device backup restores the marker but not the Keychain item** (it is
  `THIS_DEVICE_ONLY`), so that phone simply starts signed out.
- **Before App Store release:** account deletion (App Review 5.1.1(v)) must also revoke the
  user's Apple tokens, which needs a Sign in with Apple key and the authorization code. Apple's
  server-to-server notifications (the user stops using their Apple ID with NextPay) aren't
  handled yet: the account just stays until its sessions expire.
- **An identity token can be used more than once within its few minutes of validity** by
  someone who has both the token and its raw nonce. Only the phone that made the nonce has
  both, and it sends them over TLS, so no single-use table yet.
- **Rate limiting on `/auth/*`** (pre-beta, ADR 0009) now covers `/auth/apple` too. Each unknown
  `kid` can trigger a key fetch, limited by the 30-second cooldown.
- **A new native module** (`expo-apple-authentication`, plus `expo-crypto` for the nonce) and the
  Sign in with Apple entitlement mean a new EAS development build.

## Follow-ups
- [ ] **TODO before beta: warn about an existing password account.** When someone signs in with
  Apple and Apple's verified email matches an email/password account, tell them that account
  exists, so they don't land in an empty Apple account by mistake. Only tell them, and don't
  merge the accounts (see "No automatic linking by email"). Telling them is safe because Apple
  has proved they own that address, so this doesn't reveal which emails have accounts. It can't
  help someone who chooses Hide My Email: a private relay address never matches.
