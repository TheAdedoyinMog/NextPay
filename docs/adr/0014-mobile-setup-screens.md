# 0014. Mobile setup screens: forms, onboarding, navigation, and cache invalidation

- Status: Accepted
- Date: 2026-11-20

## Context
Milestone 3C builds the screens where a user enters their money setup: income and pay
schedule, current balance, bills, essential expenses, debts and goals, plus a first-run
onboarding. The app must never calculate money (ADR 0012), PUT must send the whole resource
with explicit nulls (ADR 0010), and the backend's validation errors must appear next to the
field they are about. Native modules cost an EAS build each (ADR 0012), so every choice here
was checked for whether it needs one. None does.

## Decision

### Field-level validation errors come from the backend, in a new `fields` map
- **A 422 `validation_error` now carries `fields`**: each rejected field's dotted path, as in
  `message`, mapped to Pydantic's description of the rule ("Input should be greater than 0").
  Other errors leave it out of the JSON. `message` is unchanged, so older clients still work.
- **The value is never included.** Pydantic keeps the input in `input`, which is not copied,
  so the rule from ADR 0006 that a rejected password is never echoed still holds.
- **Rejected: parsing the message string.** It would tie the app to wording meant for people,
  and only say which field, not why.
- **The app places errors by the path's last part.** A schema field is unique by name within
  a resource, so `schedule.weekly.anchor_date` belongs to the form's payday field. A field the
  form doesn't show is named above the submit button rather than hidden. Money limits arrive
  in cents and are reformatted as dollars for display; that is formatting, not arithmetic.
- **Rules the schema can't express (`invalid_input`, such as semi-monthly paydays too close
  together) and conflicts (409) are shown for the whole form.**

### Input conversion is by string, never by float
- **Money:** `parseMoney` ports the engine's `Money.parse` pattern exactly (optional minus,
  digits, up to two decimals; no "$", commas, spaces, or third decimal) and builds cents by
  joining the digit strings. `parseFloat` is never used: `0.29 * 100` is not 29.
- **APR:** typed as a percent with up to two decimals. A basis point is a hundredth of a
  percent, so the same parser gives basis points ("24.99" is 2499) with no arithmetic.
- **Editing** shows stored cents and basis points back as text by moving the point, the
  inverse of parsing.
- **Only the format is checked before sending.** Ranges and business rules stay the backend's.

### Calendar dates stay strings end to end
- **Due dates, deadlines and pay anchors are `YYYY-MM-DD` strings** from the API to the
  screen and back. They never pass through `new Date("YYYY-MM-DD")`, which reads them as UTC
  midnight and shows the previous day west of UTC.
- **The date picker is a JS calendar in a modal**, built from plain views. Weekdays come from
  integer arithmetic (Sakamoto's method). "Today" is read from the phone's local date fields.
  A native picker would look more like iOS but needs a build. It can replace this later, in
  a batch with other native changes.
- **Instants (a balance's `as_of`) do go through `Date`**, because converting an instant to
  local time is exactly what `Date` is for.
- **Every Jest run uses `America/Indiana/Indianapolis`** (set in `jest.globalSetup.js`), so a
  UTC slip fails tests on any machine and in CI.

### Navigation: two tabs, with a stack inside Setup
- **Home** shows what is set up, and in 3D the next paycheck's plan. **Setup** lists Income,
  Current balance, Bills, Essentials, Debts and Goals, each opening its list and then a form,
  with the account and Log out at the bottom.
- **JS tabs from `expo-router/js-tabs`**, which ship with Expo Router. The native tabs are
  still marked unstable.
- **Tab icons are Ionicons from `@expo/vector-icons`**, an icon font loaded by `expo-font`.
  `expo-font` and `expo-asset` were already in the development build as dependencies of
  `expo`, so no new build was needed. Expo's native fingerprint confirmed it: afterwards, the
  only native difference was where the two packages sit in `node_modules`. The install had
  pulled a newer `expo-font` patch, and a hoisted `expo-font` must find `expo-asset` beside
  it, so both are pinned to the build's exact versions (58.0.11 and 58.0.20). **At the next
  EAS build (3E), return both to the SDK range with `npx expo install expo-font expo-asset`.**

### Onboarding is decided by the server, once per sign-in
- **An account with no income sources gets onboarding**: income and pay schedule, then the
  balance (skippable), then the suggested $1,000 emergency fund (editable or skippable). The
  $1,000 is a pre-filled suggestion, not a calculation.
- **Rejected: a "has onboarded" flag on the phone.** It would need AsyncStorage, a native
  module, and it would be wrong on a second device.
- **The decision is made from the first income list after sign-in and then held** in a
  provider at the root, and reset whenever nobody is signed in. If it were recomputed,
  onboarding's own first step (which adds income) would end onboarding in the middle, and
  deleting the last income later would throw the user back into it. It is held above the
  navigator because Expo Router can recreate the signed-in layout when its protected routes
  change, which lost state kept there. A failed income list opens the app, whose screens show
  the error and a retry.
- **Removing the only income source means onboarding again at the next sign-in.** This is
  intended. It applies whether the backend deleted the source (no paychecks) or archived it
  (has paychecks), because an archived source is no longer listed either (ADR 0011). Within
  the same sign-in the held decision keeps the user in the app. At the next sign-in, an
  account with no income is set up like a new one, since planning needs income.
- **A step that is already done is left out.** Income is always asked for, since onboarding
  only runs without it. The balance step is skipped if a balance exists, and the goal step if
  an emergency goal exists. So someone onboarded again after removing their only income is
  asked only for income, and isn't offered a second emergency fund. The steps are planned once,
  when onboarding opens, and then held: saving the balance refetches it, and recomputing would
  drop the step being shown and renumber the rest. If a list fails to load, its step stays,
  which is safe: the backend still refuses a second emergency goal (409), and every step after
  income can be skipped.
- **Each step saves as it goes**, so leaving halfway keeps what was entered. Home then asks
  for anything missing, such as the balance.

### Query keys and invalidation
- **Each feature owns its keys**: `['income-sources']`, `['balance-snapshots']`, `['bills']`,
  `['essential-expenses']`, `['debts']`, `['goals']`.
- **Every setup mutation calls `invalidateAfterSetupChange`**, which invalidates that
  resource's key and `planningKeys.all` (`['planning']`). The mutation stays pending until the
  list has refetched, so a screen that goes back on success lands on fresh data.
- **For 3D: every paycheck and plan query must start with `['planning']`**, for example
  `['planning', 'paychecks', range]` and `['planning', 'plans', id]`. The backend marks draft
  plans out of date after any change to setup, and this one prefix makes every plan query
  stale at the same moment. Settings changes (3D or later) must call the same helper.

### Screen states and server errors
- **Every data screen handles loading, error (with Try again, and "You're still signed in"
  when no response arrived), and empty.** Home handles them per section, so one failed list
  doesn't blank the screen.
- **A 5xx without the error envelope shows "Something went wrong on our side. Try again in a
  moment."** and never the status code. The status stays on `ApiError` for tests and logs. A
  5xx that does carry the envelope keeps the backend's message.
- **A submit button can't be pressed again while its request is pending**, which matters
  because POST is not idempotent (ADR 0010).

## Consequences
- **No new native code: the 3B development build runs 3C**, icons included.
- The fake backend in `src/test/` now keeps resources in memory per user and copies the
  backend's error shapes, so screens are tested end to end through the real client. It
  copies only the checks the app's error handling depends on; the backend's tests remain the
  authority on validation.
- Pydantic's rule descriptions are shown to users as they are. They are accurate but plain
  ("String should have at least 1 character"). If they read badly on the phone, the backend
  can map the common ones to friendlier text in one place.
- The decimal pad shows the phone's locale separator. In a locale that uses a comma, "12,50"
  is rejected with a message. That's correct for now (US only), but internationalization
  will need a locale-aware parser that still works on the digits.
- A launch URL such as `/setup/income` is lost during session restore, because the root
  guard redirects through sign-in (3B). There are no deep links yet; if they arrive, the
  root guard must keep the target.
