# 0001. Store money as integer cents

- Status: Accepted
- Date: 2026-10-06

## Context
Floating-point numbers cannot represent most decimal amounts exactly (0.1 + 0.2 != 0.3).
In a finance app, small rounding errors compound and break user trust.

## Decision
All money is stored as integer cents: BIGINT in PostgreSQL, int in Python, integer
amount_cents in the API. A single immutable Money value object in the engine owns all
arithmetic, rounding, and splitting. When an amount is split, leftover cents go to the
last share (100.00 / 3 = 33.33, 33.33, 33.34).

### Rounding direction in the planner (2026-10-07)
Bills and debt minimums round each paycheck's share down: they use the split above, so
the leftover cents fall on the last paycheck before the due date. Goals round their share
up, so paying it every paycheck never falls short of the deadline ($2,000 over 30 paychecks
is $66.67, not $66.66). Both are intentional. The difference is harmless because bills are
recalculated every paycheck from what is still owed, so the last paycheck always covers
the rest.

## Consequences
- Exact arithmetic everywhere; one place defines rounding.
- Clients must format cents for display.
- Interest calculations need explicit rounding rules, defined in Money.
