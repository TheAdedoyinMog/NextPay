# 0005. Variable income is deferred past V1

- Status: Accepted
- Date: 2026-10-06

## Context
Forecasting irregular income (tips, gig work, commissions) is a separate, hard problem.

## Decision
V1 supports weekly, biweekly, semi-monthly, and monthly schedules. Each income source has an
expected amount, and the actual amount is recorded when the paycheck arrives; plans can be
regenerated from the actual amount.

## Consequences
- V1 stays focused and correct for regular earners.
- Users with irregular income can use a conservative estimate until forecasting is added.
