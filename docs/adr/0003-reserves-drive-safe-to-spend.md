# 0003. Reserves and committed plans are the source of truth for Safe to Spend

- Status: Accepted
- Date: 2026-10-06

## Context
V1 has no bank connection, so NextPay cannot see whether money was actually set aside.
Without tracking it, Safe to Spend would count the same dollars twice.

## Decision
When a user commits a plan, its allocations become reserves. Paying a bill draws its reserve
down; deleting a goal releases its reserve.
Safe to Spend = available funds - all reserves - this period planned allocations,
floored at zero with any shortfall reported separately.

## Consequences
- Safe to Spend is consistent across paychecks.
- Accuracy depends on the user committing plans and recording payments; Phase 7 (Plaid)
  will reconcile reserves against real balances.
