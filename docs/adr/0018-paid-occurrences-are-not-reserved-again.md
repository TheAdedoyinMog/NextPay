# 0018. Occurrences already paid are not reserved for again

- Status: Accepted
- Date: 2026-11-22

## Context
The planner reserves for each bill's and debt's next due date after the paycheck, less what is
already reserved. It does not know what has been paid. A car loan due Nov 25 that was paid
early, on Nov 22, has its reserve drawn down to $0 by the payment (ADR 0011). The next plan
then sees $0 reserved and the Nov 25 due date still ahead, so it reserves the full $150 again.
Nothing is underfunded, because the extra ends up covering December, but that plan's Safe to
Spend is too low, and its explanation names a payment that has already been made. ADR 0011
recorded this as a known limitation, to be fixed in the engine rather than patched in the
backend. ADRs 0015 and 0017 carried it forward.

Two gaps stand in the way:
- **Debt payments don't record which occurrence they pay.** Bill payments store `due_date`
  (ADR 0011). Debt payments store only `paid_on`, and the app guesses whether a debt line is
  paid by comparing `paid_on` with the plan's pay date. That guess is a rule, and rules don't
  belong in the app.
- **The default occurrence can't express "early".** With no `due_date` given, a payment is
  matched to the nearest due date, the earlier one on a tie. A car loan due on the 20th and
  paid on Nov 20 is therefore applied to Nov 20, never to Dec 20. An early payment only works
  if the occurrence is named, and the app names it for bills: "Mark paid" on a plan line sends
  that line's `due_date`.

## Decision

### 1. A payment pays the occurrence it names
- **Debt payments get a `due_date`, as bill payments already have.**
  `POST /debts/{id}/payments` accepts an optional `due_date`, which must be one of the debt's
  due dates. Responses include it.
- **The app always names the occurrence.** "Mark paid" on a bill or debt line sends that
  line's `due_date`, which the engine wrote. Debt lines show "✓ Paid" by matching `due_date`,
  as bill lines do, and the app's `paid_on >= pay_date` guess goes away.
- **When nothing is named, the default stays the nearest due date** (earlier on a tie), and
  debts now use it too. Only direct API calls rely on it. The rule moves into the engine as
  `closest_due_date` on `Bill` and `Debt`, so all date and money rules live in one place.
- **The engine matches payments by exact date.** A payment counts toward an occurrence only
  if its `due_date` equals that occurrence's date. If a bill's or debt's schedule is edited
  later, a payment that no longer lands on a due date matches nothing. That makes the planner
  reserve again, which is the safe direction.

### 2. A partial payment lowers what is still needed
$100 paid toward a $150 occurrence leaves $50 needed. Not counting it until fully paid would
reserve the $100 a second time, which is the very bug this ADR fixes. For each occurrence:

- **bill:** `unpaid = max(amount − paid, 0)`
- **debt:** `unpaid = min(max(minimum − paid, 0), balance)`

`paid` is the sum of the payments matched to that occurrence. For a debt, `balance` is the
current balance, which those payments have already lowered. The line asks for
`(unpaid − reserved).split(paychecks)[0]`, exactly as it does today with `amount` in place
of `unpaid`.

### 3. For a debt, "covered" means the minimum is paid; extra goes to principal only
- An occurrence is covered once the payments matched to it reach the minimum, or reach what
  is left on the debt if that is less.
- **Anything above the minimum is principal.** It is already reflected in the lower balance.
  It does not pay future minimums: $300 paid toward a $35 minimum covers that month only, and
  next month's $35 is still reserved. That matches credit cards and most loans. Someone who
  really pays two months ahead records two payments, one for each due date.
- **Debts that "pay ahead" are deliberately not modelled.** Some installment lenders move
  the next due date out when you overpay. NextPay treats extra as principal only, which is the
  conservative choice: it may reserve a minimum the lender wouldn't collect, but it never
  skips one the lender will. A per-debt "pays ahead" option is a possible future change.
- **Bills have no principal, so overpaying covers that occurrence only.** Paying $70 on a $60
  bill covers it. The extra $10 does not count toward the next occurrence, which still needs
  $60. A credit or refund is outside what NextPay tracks.

### 4. The line moves on to the next occurrence that isn't fully paid
The planner takes the first due date after the paycheck. While that occurrence is fully
paid, it moves to the next due date. The loop ends because each fully paid occurrence needs
at least one payment. A one-time bill with nothing left to pay gets no line, as happens today
when its reserve covers it.

Moving on, rather than leaving a $0 line, spreads the next occurrence across every paycheck
before it, so reserving is smoother. It also gives the explanation a place to say what was
skipped.

### 5. Reserves (ADR 0016) and undo (ADR 0017) need no new rules
- A payment still draws its reserve down when it is recorded, and still lowers Safe to Spend
  on Home by whatever it paid beyond the reserve. Reserves stay per target, not per
  occurrence. What is left in a reserve counts toward whichever occurrence the line targets.
  So the amount asked for is always `unpaid − reserved`, and never counts the same dollars
  twice.
- **Undone payments never reach the engine.** The backend passes only payments with
  `undone_at IS NULL`. The engine has no idea of undo. Undo already puts reserves and balances
  back exactly (ADR 0017), so after an undo, every input is what it was before the payment.
  The hash matches again, and the same plan comes out.

### Engine shape
- New input type `Payment(kind, target_id, due, paid_on, amount)`. `kind` is a new
  `PaymentKind` enum (`bill` or `debt`). New field `FinancialState.payments: tuple[Payment, ...]`.
  `FinancialState` checks that each target exists. It does not check that `due` falls on a
  due date (see §1).
- The engine stays pure: payments are plain data. No I/O and no clock.
- `Basis` gains five facts. Each becomes a column on `allocations` in the same migration, so
  that stored plans can still be explained:
  - `paid` — paid toward the line's own due date
  - `paid_on` — the date of the latest of those payments
  - `paid_ahead` — how many fully paid occurrences were skipped
  - `paid_through` — the due date of the last skipped occurrence
  - `paid_ahead_on` — the date of the latest payment toward the skipped occurrences

### Input hash
`canonical_input` gains `payments`. It holds kind, target id, due date, paid-on date and
amount, sorted, with duplicates kept. It holds no ids and no timestamps. It includes **only
payments due after the paycheck's pay date**: the planner never reads earlier ones, just as a
$0 reserve is left out. So:

- recording or undoing a payment for a later occurrence makes that paycheck's draft out of
  date;
- a payment for an occurrence that has already passed leaves the draft alone.

### 6. Explanation text (exact)
The words added to today's sentences are shown in **bold**.

- **Partly paid**, nothing reserved yet:
  "We reserved $25 toward Phone because the $90 bill is due Dec 10; **with $40 already paid on
  Nov 21**, the rest is split across the 2 paychecks before then."
- **Partly paid and partly reserved:** "…; with **$40 already paid on Nov 21 and $5** set
  aside, the rest is…"
- **One occurrence skipped.** A sentence is added at the end:
  - bill: "**The Nov 25 bill was already paid on Nov 22.**"
  - debt: "**The Nov 25 minimum payment was already paid on Nov 22.**"
- **Several occurrences skipped:** "**Everything due through Dec 25 was already paid, most
  recently on Nov 22.**"
- **Underfunded lines** keep their "Car loan needs $50 from this paycheck because…" opening.
  The same additions apply.

Old plans have no payment facts stored (zeros and nulls), so they read exactly as they do now.
A golden test pins this.

### ENGINE_VERSION goes from 0.2.0 to 0.3.0
The same inputs can now give a different plan, so the version changes. Because the version is
part of the input hash:

- **every existing draft becomes out of date once.** The app already handles this (ADR 0011
  and ADR 0015): it shows "update" and plans again.
- **Committed plans don't change.** They are final, and the new `Basis` columns default to
  "nothing paid", so their wording stays the same.

### Migration
One migration:
- Adds `debt_payments.due_date`. Existing rows are backfilled with **the debt's due date on or
  before `paid_on`**. This is a conservative choice: a backfilled payment can never skip a
  future occurrence the user didn't clearly pay. The column then becomes NOT NULL, and an
  index on `(debt_id, due_date)` is added, as for bills.
- Adds the five `Basis` columns to `allocations`, with defaults of 0 and NULL.

## Worked examples
All three use a biweekly paycheck on Fridays: Nov 6, Nov 20, Dec 4, Dec 18 and Jan 1.

**A. Debt paid early, then the payment undone.**
Car loan: minimum $150, due on the 25th, balance $3,000.

1. The Nov 6 plan targets Nov 25. Two paychecks come before it (Nov 6 and Nov 20), so it
   reserves **$75**. Commit: reserve $75.
2. On Nov 22, "Mark paid" on that line records $150 for **Nov 25**. It draws the $75 reserve,
   pays $75 beyond it (Home drops by $75 under ADR 0016), and leaves a balance of $2,850.
3. Planning Nov 20:
   - **Before this ADR:** it targets Nov 25, needs $150 − $0, with one paycheck left, so it
     reserves **$150**.
   - **After:** Nov 25 is fully paid, so it moves on to Dec 25. Three paychecks come before it
     (Nov 20, Dec 4, Dec 18), so it reserves **$50**. Safe to Spend is **$100 higher**.

   The explanation reads: "We reserved $50 toward Car loan because the $150 minimum payment is
   due Dec 25 and is split across the 3 paychecks before then. The Nov 25 minimum payment was
   already paid on Nov 22."
4. Undo the payment. The reserve goes back to $75 and the balance to $3,000, and the payment
   drops out of the inputs. The Nov 20 draft made in step 3 is now out of date. Planning again
   gives **$75**, as if nothing had been paid: "…due Nov 25; with $75 already set aside, the
   rest is due before your next paycheck."

**B. Partial bill payment.**
Phone: $90, due Dec 10, nothing reserved. $40 paid on Nov 21 for Dec 10.

The Nov 20 plan's unpaid amount is $90 − $40 = $50, split over two paychecks (Nov 20 and
Dec 4), so it reserves **$25** (before this ADR: $45).

Had $45 been reserved before the payment: the payment draws $40, leaving $5 reserved. The
need is $50 − $5 = $45, so **$22.50** now and $22.50 on Dec 4. In total that is
$40 + $5 + $22.50 + $22.50 = $90.

**C. Extra principal.**
Card: minimum $35, due on the 15th, balance $1,200. $300 paid on Nov 21 for Dec 15. The
balance becomes $900.

The Dec 4 plan:
- Dec 15's unpaid amount is min(max($35 − $300, 0), $900) = $0, so it moves on to Jan 15.
- Three paychecks come before Jan 15 (Dec 4, Dec 18, Jan 1), and $35 splits as $11.66,
  $11.66, $11.68, so it reserves **$11.66**.
- The extra $265 lowered the balance and paid nothing toward January.

Before this ADR: **$35**.

## Consequences
- The ADR 0011 limitation is closed for bills and debts whose payment names its occurrence,
  which every payment made from the app does.
- **Editing a bill's amount after paying it leaves a remainder.** A $150 bill that is paid
  and then raised to $160 shows $10 still needed for that occurrence. That is correct if the
  bill went up. If the change was only meant for future bills, it is a small nuisance, and
  recording a $10 payment clears it.
- Editing a schedule orphans earlier payments, and the occurrence is reserved for again. That
  is safe, but the Safe to Spend is low, as before this ADR.
- The planning state now loads payments that haven't been undone: one indexed query per
  target table.
- Every draft goes out of date once, when the new engine is deployed.
- Tests:
  - Hypothesis property: no line ever asks for more than `unpaid − reserved` of its
    occurrence.
  - Hypothesis property: removing a payment and restoring what it drew from the reserve and
    the balance gives the same plan as never paying.
  - The worked examples above become example tests, along with $70 paid on a $60 bill
    (covered; the next occurrence still needs the full $60).
  - A backend test: pay, then undo, and the input hash matches the one from before paying.
