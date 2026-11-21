# 0017. Undoing a payment

- Status: Accepted
- Date: 2026-11-21

## Context
A bill or debt payment draws its reserve down, lowers a debt's balance, and lowers the
dashboard's Safe to Spend by whatever it paid beyond its reserve (ADR 0011, ADR 0016). A tap
on the wrong line, or the wrong amount, could not be taken back: both confirmations said
"can't be undone yet" (ADR 0015). An undo has to put everything back exactly, be safe to
repeat on a bad connection like every other money action, and keep Safe to Spend honest.

## Decision

### Undo marks the payment undone; nothing is deleted
- `POST /bills/{bill_id}/payments/{payment_id}/undo` and the same under `/debts`. Both return
  the payment (200) with `undone_at` set. It is an action, not a `DELETE`: the row stays as
  history.
- **It puts back exactly what the payment took.** The reserve gets `reserve_drawn_cents` back
  (ADR 0016 stored it for this). A debt's balance gets `balance_reduced_cents` back, a new
  column, because a payment that overpaid past $0 took less off the balance than its amount:
  $100 owed and $150 paid leaves $0, and an undo must restore $100, not $150. Migration
  `a3c5e7f9b1d2` adds it, with `undone_at` on both payment tables.
- **Undone payments count for nothing.** They drop out of `GET .../payments` and out of the
  dashboard's "paid beyond reserves", so Safe to Spend returns to what it was before the
  payment. Paying the car loan $150 with $50 set aside takes Home from $590 to $490; undoing
  it brings Home back to $590 and the reserve back to $50.

### Undoing is safe to repeat by nature
Under the user's row lock, a payment that is already undone is returned unchanged, so a
double tap and a retry after a lost reply both undo once. The payment id names the payment,
so no client-made id or `Idempotency-Key` is needed (ADR 0015's order of preference).

### Undo is allowed only until a plan is committed after the payment
Committing a plan after a payment means that plan was made around the drawn-down reserve,
from a balance entered after the payment. Putting the reserve back then would hold the same
money twice: once in the new plan's free money and once in the reserve. So a later commit
(of any plan, by `committed_at`, the clock that stamps payments) makes undo a 409
`payment_undo_too_late`, and the message says to correct the balance instead. Each payment
says `can_undo`, so the app never decides the rule. A payment recorded at a commit's own
instant counts as after it, as it does for Safe to Spend. A mistaken tap is normally noticed
long before the next payday.

### Out-of-date drafts follow from the inputs, not from the undo
A draft is out of date when the hash of today's inputs no longer matches it (ADR 0011);
nothing about it is stored. Reserves and debt balances are inputs, and undo restores both
exactly, so:
- a draft made before the payment, which the payment made out of date, is **current again**
  and can be committed;
- a draft made again after the payment is **out of date** after the undo;
- if anything else changed in between, the draft stays out of date.

### Paying again after an undo is a new payment
The app makes a new id for every "Mark paid", so paying again records a new payment that
draws down and lowers Safe to Spend again. The undone payment's own id still means that
payment: a late retry of the original request returns it, undone (200), and changes nothing,
so a stale retry can never bring an undone payment back.

### The app
The "✓ Paid" row shows **Undo** when `can_undo` is true. Undo asks first ("Undo the Rent
payment?"), names what is put back in words, never a sum, and shows the server's message if
it fails, with a retry that sends the same request. When `can_undo` is false the row says
"Can't undo after a newer plan." instead, and for a debt adds "To correct the balance, edit
it in Setup." "Mark paid" now says the payment can be undone until the next plan is
committed.

## Consequences
- One migration. Existing debt payments take `balance_reduced_cents = amount_cents`, since
  nothing recorded more. Any of them made before the latest commit can't be undone anyway.
- The payment list and pay responses look up the user's latest commit time: one indexed
  `max()` per request.
- A payment made before the latest commit can't be undone. If it never happened, the user
  edits the debt's balance; for a bill, the next plan simply reserves for it again.
- The fake backend in the app's tests marks every draft out of date on an undo. The
  backend's tests are the authority on a draft becoming current again.
- Still open from ADR 0011: a bill or debt paid early is reserved for again by the next plan.
