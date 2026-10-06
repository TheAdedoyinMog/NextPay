# 0004. Purchases are goals

- Status: Accepted
- Date: 2026-10-06

## Context
"I Want This" items and savings goals both have a target amount, a date, and a priority.

## Decision
A purchase is a Goal with kind = purchase. "Can I afford it?" is a stateless engine call that
simulates adding the goal before the user saves it.

## Consequences
- One goal system instead of two parallel ones.
- Purchase-specific fields, if ever needed, are added to goals rather than a new table.
