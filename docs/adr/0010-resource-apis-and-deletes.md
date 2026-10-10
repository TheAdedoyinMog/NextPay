# 0010. Resource API conventions and what deleting means

- Status: Accepted
- Date: 2026-10-10

## Context
Milestone 2C puts the first user-owned data behind HTTP: income sources, bills, essential
expenses, debts, goals, and balance snapshots. Six resources need one shape, so the mobile
client and the next milestone can rely on it. Two questions were left open by earlier
records: ADR 0008 deferred what happens when an income source with paychecks is deleted,
and ADR 0003 says deleting a goal releases its reserve without saying what "release" is.

## Decision

### One shape for every resource
- **Routes.** `POST /x`, `GET /x`, `GET /x/{id}`, `PUT /x/{id}`, `DELETE /x/{id}`, all
  requiring a signed-in user. Lists return `{"items": [...]}` so paging can be added
  without breaking clients.
- **PUT replaces the whole resource; there is no PATCH.** An edit screen sends the whole
  form, validation is the same as for create, and "left out" can never be confused with
  "clear this". Every request field is therefore required, including nullable ones
  (`repeat_every_months`, `deadline`), which must be sent as `null`. A test keeps them
  `required` in the OpenAPI schema so a generated client types them `T | null`, not
  optional.
- **Not found means not yours.** Another user's id and an id that does not exist return
  the same 404 body (ADR 0006). One test per verb proves it for every resource.
- **Validation has three layers.** The request schema checks shape and single fields and
  forbids unknown fields. The service then builds the engine's own domain type from the
  row (`services/engine_mapping.py`), so it cannot accept what the engine would reject.
  The database's CHECK constraints remain the backstop (ADR 0008). 2D feeds the planner
  through the same mapping functions.
- **Upper bounds are API limits, not money rules** (`core/limits.py`): $1 billion per
  amount, priority 1,000, 120 months between bill occurrences, 100,000 bps. The engine
  has none; these keep a request from overflowing a column.
- **Wire format.** Money is integer `*_cents` (ADR 0001). Integers are strict: `12.0`,
  `"12"` and `true` are rejected. Dates are ISO strings. A pay schedule is a tagged
  union on `type`, so a frequency can only carry its own parameters.
- **One generic repository.** `UserOwnedRepository` holds get, list, add and delete, each
  filtered by `user_id`. The design avoids generic base classes; this is the one
  exception, because it is the tenant boundary and belongs in one place, not six.
  Services and schemas stay written out per resource.

### Balance snapshots are append-only and stamped by the server
There is only `POST` and `GET` (newest first, `limit` up to 100). The client sends an
amount; the server sets `as_of`. A new balance is a new snapshot, and the newest is the
current balance.

### Deleting
- **Income source with paychecks: refused, 409 `income_source_in_use`.** Paychecks and
  their plans are history and belong to their source (RESTRICT, ADR 0008). The database
  decides, so a paycheck recorded during the request is still caught. A source with no
  paychecks is deleted.
- **Bill, debt, essential expense, goal: always allowed.** The database cascades: a
  bill's payments and any reserve go with it. Past plans keep the name they copied and
  lose only the link (SET NULL, ADR 0008).
- **Deleting a goal releases its reserve, and "release" is the reserve row being
  deleted.** A reserve is an earmark inside the available balance, not a separate pot, so
  nothing is moved: the next Safe to Spend simply stops subtracting it. This is right in
  both real cases. If the user changed their mind, the money is spendable again. If they
  bought the thing, their balance fell by the price and the earmark went with it, so Safe
  to Spend does not change.
- **One emergency goal per user.** A second one, created or converted, is refused with
  409 `emergency_goal_exists`, raised from the unique index so concurrent requests cannot
  both succeed.

## Consequences
- A new resource is a schema, a service, a four-line repository, a router, and one entry
  in the test registry; the isolation and contract tests then cover it.
- **Required in 2D: archiving an income source.** Refusing is not enough once paychecks
  exist: someone who leaves a job needs that source to stop producing paychecks. It needs
  an `archived_at` column and a rule for what planning does with an archived source,
  which can only be decided and tested when plans exist.
- Deleting a bill deletes its payment records. Plans still show what was allocated, but
  the list of payments is gone. If payment history must outlive a bill, bills need
  archiving too.
- A deleted goal's progress that was never reserved (`current_cents` entered by hand) is
  simply forgotten; it was never part of the balance.
- Each resource has four types (request schema, service input, model, engine type). That
  is the cost of keeping storage, API and engine free to change separately.
- POST is not idempotent: a retried request creates a duplicate. Idempotency keys are
  deferred to the mobile client work.
- Open for 2D: whether `current_cents` may still be edited by hand once a goal has a
  reserve, and showing `reserved_cents` on bills, debts and goals.
