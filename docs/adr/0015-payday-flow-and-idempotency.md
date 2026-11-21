# 0015. The payday flow: dashboard, out-of-date plans, and repeat-safe money actions

- Status: Accepted
- Date: 2026-11-20

## Context
Milestone 3D puts the payday loop in the app: a paycheck arrives, the user records what it
paid, plans it, reviews the plan, commits it, and marks bills and debts paid as the period
goes on (ADR 0011). The app must not calculate money (ADR 0001, ADR 0003), so every number it
shows has to come from the API, and some did not exist yet. Phones lose signal, so every
money action must be safe against a double tap and against a retry after a timeout, where the
first request may already have been applied.

## Decision

### Every money action is safe to repeat
Checked action by action against what the backend already did, preferring operations that are
idempotent by nature, then client-made ids, and a generic `Idempotency-Key` header only if
neither covers it. Neither left a gap, so there is no header.

| Action | How a repeat is safe |
|---|---|
| Record what a paycheck paid | `PUT`: the same value again changes nothing. |
| Enter the balance | A second snapshot with the same amount is harmless: snapshot ids and times are not in the plan's input hash (ADR 0011), so drafts stay current. |
| Plan a paycheck | The same inputs return the same draft (200); after a commit, 409, which the app handles. |
| Commit a plan | Already did nothing for a committed plan and returned it (ADR 0011). |
| Pay a bill or debt | **New: the request carries an `id` the app made.** A payment with that id for the same target is returned as it was (200) and nothing changes. The same id for anything else is 409 `payment_id_conflict`. |

- **The payment id is optional** in the API, so `{}` still means "mark as paid" (ADR 0011),
  and the app always sends one. Without it, every request is a new payment.
- **The lookup by id is not filtered by user**, so a reused id is refused rather than hitting
  the primary key. Only the user's own payment is ever returned, and the 409 says nothing
  about whose it was. The user's row lock (ADR 0011) means two copies of one request can't
  both get past the check.
- **A retry is matched by id alone.** Left-out fields default to "today", so a retry on the
  next day would not match field by field. Comparing fields would turn a harmless retry into
  an error.
- **In the app, the id is made once per "Mark paid" and kept until the server has it.** A
  second tap or a retry after an error sends the same id. React Native has no Web Crypto, so
  the id falls back to a `Math.random` version 4 UUID; it needs to be unique, not secret.
- **Buttons can't be pressed while their request is pending**, which stops most double taps
  before they reach the network.
- **Tests prove each case against a fake backend that applies a request and then loses its
  reply**, which is exactly the retry-after-timeout case: the commit reserves once, the bill
  reserve draws down once, the debt balance falls once. The backend tests repeat each request
  and check one row and one change.

### The API says when a draft is out of date
- **`is_out_of_date` on every plan, and on the plan summary in paychecks**: a draft that commit
  would refuse with `plan_out_of_date`. It runs the same check as commit (the input hash, or an
  archived source), moved into one helper, so they cannot disagree. Committed and superseded
  plans are never out of date.
- **The app shows it and offers to update**, and still treats a 409 at commit as the signal to
  plan again (ADR 0011's contract): it makes the new draft and says the details changed, never
  that something failed. `plan_superseded` is handled the same way.

### `GET /dashboard` answers what the home screen asks
- `today` in the user's time zone; `current_paycheck` (the newest payday on or before today);
  `next_paycheck`; `safe_to_spend` from **the newest committed plan** for a payday on or
  before today, with its `reserve_deficit_cents`; and the latest `balance`.
- **Why an endpoint:** `GET /paychecks` defaults to a week back, which misses the current
  paycheck of a biweekly or monthly schedule, and choosing the "current" payday and plan is
  a rule, which belongs on the server with the timeline.
- **A draft's Safe to Spend is shown only on its plan, as "after you commit".** Home shows the
  committed number, so it never shows money as spendable that a commit could change.
- **Payments since the commit move it** when they pay beyond their reserves (ADR 0016).
- **A shortfall is shown separately**: `reserve_deficit_cents` when more is set aside than the
  user has, and each underfunded line's `shortfall_cents`. The app never adds them up.

### The balance is asked for every time a paycheck is planned
- The flow is: what the paycheck paid, then **the balance before this paycheck arrived**,
  prefilled with the last one, then the plan. This replaces a stale-balance rule: there is no
  threshold to choose, and the plan always starts from a balance the user just confirmed.
- A plan still shows the balance it used and when it was entered (`balance_as_of`).
- **Risk:** someone who enters their balance after the paycheck landed counts it twice. The
  field and its hint say "before this paycheck", and Safe to Spend would look too high. A
  bank connection (Phase 7) is the real fix.

### The account's time zone follows the phone
Accounts were created in UTC, where 7 PM in Indiana is already tomorrow, which would date
plans and payments a day late. While signed in, if the account's zone differs from the
phone's (`Intl`, no native module), the app sends `PUT /me/settings` once, with the goal share
unchanged.

### Screens and keys
- The payday flow and the plan open over the tabs from Home. Lines are grouped by tier in
  waterfall order, each with the engine's explanation as it is (ADR 0011). On a committed
  plan, bill and debt lines have **Mark paid**, with what is set aside for them now, so the
  draw-down is visible.
- All new keys start with `['planning']`: `dashboard`, `plans/{id}`, `payments/bill|debt/{id}`
  (ADR 0014). Recording or planning invalidates planning. Committing or paying also
  invalidates bills, debts and goals, whose `reserved_cents` and progress changed.

## Consequences
- No new native code; no migration (payment ids were already UUID primary keys).
- `GET /dashboard`, `GET /plans/{id}` and `GET /paychecks` now load the planning state to
  check drafts: one state load per request, however many drafts. Fine at one user's scale.
- **Still open from ADR 0011:** a payment can't be undone, and a bill paid early is reserved
  for again by the next plan. Both confirmations say "can't be undone yet".
- The dashboard looks 62 days back for the current payday, enough for any monthly schedule.
- The fake backend's plans come from a template each test sets; the engine's own tests, and
  the backend's, remain the authority on what a plan says.
