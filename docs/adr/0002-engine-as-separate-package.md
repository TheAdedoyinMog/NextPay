# 0002. The planning engine is a separate, pure package

- Status: Accepted
- Date: 2026-10-06

## Context
The financial math is the most important and most error-prone part of NextPay. It must be
testable without a database or web server and must not leak into the mobile app.

## Decision
The engine lives in engine/ as its own Python package (nextpay_engine). It has no
dependencies, does no I/O, and never reads the clock; the current date is always passed in.
It is built around one pure function, plan_paycheck(state, paycheck, as_of) -> PlanResult.
Simulation, what-if, and affordability are compositions of that function.
An import-linter contract fails CI if the engine imports the backend, FastAPI, SQLAlchemy,
or Pydantic.

## Consequences
- Deterministic, fast, isolated tests for all financial logic.
- Small mapping code is needed between database models and engine types.
