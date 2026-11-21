# 0016. Safe to Spend after payments

- Status: Accepted
- Date: 2026-11-20

## Context
Home showed the committed plan's Safe to Spend as stored at commit (ADR 0015). Payments
never changed it. A payment covered by its reserve should change nothing: the money leaves,
and what was set aside for it falls by the same amount. But paying more than was set aside
(a $150 car payment with $50 reserved) takes the extra $100 from money the plan called free.
Home still said $590 when only $490 was free.

## Decision
- **Each payment records how much it drew from its reserve**: `reserve_drawn_cents` on bill
  and debt payments, between 0 and the amount, set when the payment is recorded (migration
  `7d1f3a9c2e64`). Existing payments are treated as fully covered, so nothing moves when the
  migration runs. Undoing a payment will need the same number, to put back exactly what came
  out.
- **The dashboard's Safe to Spend is now the plan's, less what payments since its commit paid
  beyond their reserves**, worked out on the server:
  `free = plan Safe to Spend − plan shortfall − paid beyond reserves`.
  Safe to Spend is `max(free, 0)`, and anything below $0 becomes `reserve_deficit_cents`, so
  it is never negative, as in a plan. `paid_beyond_reserves_cents` is returned too, so Home
  can say why the number moved without the app doing any arithmetic.
- **"Since its commit"** means payments recorded at or after `committed_at`. Payments are
  stamped with the app's clock, the same clock that sets `committed_at`. Payments recorded
  before the commit are left out: the plan started from a balance entered after them (ADR
  0015 asks for it every time).
- **A committed plan itself does not change.** It is a record of what was decided. Its screen
  says "Safe to Spend when committed" and points to Home for the current number.
- A repeated payment (the same id) is one payment, so it lowers Safe to Spend once.

## Consequences
- One migration, with no backfill risk. Each `GET /dashboard` adds two indexed sums.
- A payment recorded late, for money that left before the balance was entered, is counted
  again. It is the same limitation as ADR 0015's balance double count, and a bank connection
  (Phase 7) fixes both.
- When the next paycheck's plan is committed, its newly entered balance takes over, and the
  count starts again from that commit.
