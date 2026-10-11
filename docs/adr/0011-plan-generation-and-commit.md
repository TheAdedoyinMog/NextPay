# 0011. Generating, committing, and paying against paycheck plans

- Status: Accepted
- Date: 2026-10-10

## Context
Milestone 2D is the first time the backend calls `plan_paycheck`. It has to decide how a
paycheck is named, what "today" is, when a stored plan may be trusted, and how ADR 0003's
reserves change when a plan is committed and when a bill or debt is paid. ADR 0010 left
income-source archiving for this milestone.

## Decision

### Paychecks are named by income source and pay date
- A paycheck has no row until something is recorded or planned for it, so the API never
  asks for a paycheck id. `POST /plans` and
  `PUT /income-sources/{id}/paychecks/{pay_date}` take the natural key, which is already
  unique in the schema. The row is created on first use.
- The date must be one of the source's paydays, checked with the engine's schedule.
- `GET /paychecks` returns the engine's shared timeline for a date range, merged with what
  is stored. The app never works out a payday itself (weekend rollback, month ends).

### `as_of` is today in the user's time zone
`users.timezone` (IANA name) and the injected clock give the date. `PUT /me/settings` sets
the time zone and the leftover share for goals without a deadline.

### One loader builds `FinancialState`
`PlanningStateLoader` reads the user's active income sources, bills, essentials, debts,
goals, reserves and latest balance snapshot (or $0), and `engine_mapping.to_engine_state`
turns them into the engine's types. Generating and committing use the same loader.

### The input hash decides whether a plan can still be trusted
- `input_hash` is the SHA-256 of a canonical JSON document of everything the engine reads:
  the engine version, `as_of`, the paycheck, and the whole state. Collections are sorted by
  id, keys are sorted, money is integer cents, dates are ISO strings.
- Names are in it, because plans copy them. Row timestamps and balance snapshot ids are
  not. A $0 reserve is left out: the planner treats it as no reserve.
- It is built from the engine's objects, so it describes exactly what was planned. A golden
  test pins the format; changing it makes every stored draft out of date.
- Planning a paycheck whose current draft has the same hash returns that draft (200) and
  makes no new version. Otherwise the old draft is superseded and the version goes up.

### Committing
- The user's row is locked first, so one user's commits, payments and plan generation run
  one at a time.
- The state is loaded and hashed again with the plan's own `as_of`. A different hash is
  409 `plan_out_of_date`. A draft therefore does not expire at midnight, only when data
  changes: an edited bill, a new balance, a recorded actual amount, another paycheck's
  commit.
- **409 `plan_out_of_date` on a draft is the expected, normal signal to generate the plan
  again, not an error state.** This is a contract for every client: on that response,
  call `POST /plans` for the same paycheck, show the new draft, and let the user commit
  that one; never present it as a failure. It happens in ordinary use, for example
  whenever one paycheck is committed while a draft for a later one exists.
- Each funded line is applied: a bill or debt line adds to that target's reserve; a goal or
  emergency-fund line adds to the goal's reserve and to its `current_cents`. Essential
  lines reserve nothing: they are money to spend this period, and the engine has no
  reserve for them.
- Committing an already committed plan returns it and changes nothing, so a retried
  request is safe. A superseded draft is 409 `plan_superseded`. The partial unique index
  (one committed plan per paycheck) stays as the database's backstop, surfaced as 409
  `paycheck_already_committed`.
- **A committed plan is final.** Recording an actual amount after commit is stored but
  changes no plan; the difference reaches the next plan through the balance. Regenerating
  from the actual amount (ADR 0005) applies to drafts.

### Payments
- `POST /bills/{id}/payments` records a payment and draws the bill's reserve down by the
  amount, never below $0. Every field has a default, so "mark as paid" is `{}`: the full
  amount, today, for the due date closest to the payment date (the earlier one on a tie).
  A named `due_date` must be one of the bill's due dates.
- `POST /debts/{id}/payments` does the same for a debt and also lowers its balance. It is
  required, not optional: the planner asks for the minimum less what is reserved, so a
  debt whose reserve never went down would be funded once and never again.
- **Balances are not adjusted** by commits or payments. A balance is what the user entered,
  and the engine reads it only when a plan is generated, as the money on hand before that
  paycheck. The app must ask for a fresh balance then; plans record `balance_as_of`.

### What is set aside is shown, read-only
Bill, debt and goal responses carry `reserved_cents`: the target's reserve, or 0 if it has
none. Commit and payment responses do not list reserves, so this is how a client sees a
commit set money aside and a payment draw it down. It cannot be sent in a request.
Essential expenses have no such field, because nothing is ever reserved for them.

### A goal never has more set aside than it has saved
Lowering a goal's `current_cents` below its reserve lowers the reserve to match. Raising it
reserves nothing.

### Archiving income sources (replaces ADR 0010's 409)
Deleting a source that has paychecks sets `archived_at` instead; one without paychecks is
deleted. Either way the API then treats it as gone: 404, not listed. An archived source
adds no paydays to the timeline and cannot be planned for; a draft for it is out of date.
Its paychecks and plans stay readable. There is no un-archive.

## Consequences
- **Known limitation: a bill or debt paid early is reserved for again.** The planner does
  not know which occurrence is paid. If rent due Oct 20 is paid on Oct 15 and a paycheck
  lands on Oct 16, that paycheck's plan sees an empty reserve and a due date still ahead,
  and reserves the rent again. The extra then covers November, so nothing is underfunded
  and no money is lost, but that plan's Safe to Spend is too low and its explanation names
  a bill that is paid. The fix belongs in the engine (bills and debts that know what has
  been paid) and is deferred until real use; it is deliberately not patched in the backend.
- The mirror case corrects itself the same way: a payment recorded late leaves the old
  reserve standing, so the next occurrence looks funded until the payment is entered.
- A stale balance makes a plan wrong. Nothing forces a new one; `balance_as_of` lets the
  app warn.
- A payment recorded by mistake cannot be undone yet: the reserve it drew down is not
  restored.
- Explanations are written by the current engine each time a plan is read. An old plan's
  numbers never change; its wording can, after an engine upgrade.
- A new `ENGINE_VERSION` changes every hash, so every draft must be regenerated. That is
  intended: a new engine may plan differently.
- Deferred: replacing a committed plan, a plan-history list, and un-archiving a source.
