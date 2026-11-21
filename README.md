# NextPay

A mobile app that answers one question every payday: **"What should I do with my next paycheck?"**

## Repository layout

```
engine/    Pure, deterministic planning engine (no DB, no network, no clock)
backend/   FastAPI app: api -> services -> repositories; services call the engine
mobile/    Expo + TypeScript app (Phase 3)
docs/      Design doc link and architecture decision records (ADRs)
infra/     Docker Compose and deployment config (Phase 2+)
```

## Getting started

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-packages        # install everything into one virtual env
uv run pytest                 # run all tests
uv run ruff check             # lint
uv run ruff format            # format
uv run mypy                   # strict type check
uv run lint-imports           # enforce the engine boundary
uv run pre-commit install     # run the checks automatically on every commit
uv run fastapi dev backend/app/main.py   # start the API with auto-reload (needs the database below)
```

### Local database

Requires Docker. Settings come from `NEXTPAY_*` environment variables, or from `.env` at the
repo root (git-ignored), which is read wherever you start the API or Alembic. Copy
`.env.example` to `.env` once for local defaults (PowerShell: `Copy-Item .env.example .env`).
The API refuses to start without the required settings, and names the missing ones.

```bash
docker compose -f infra/docker-compose.yml up -d --wait   # PostgreSQL 17 on localhost:5432
uv run alembic -c backend/alembic.ini upgrade head         # create or update the schema
uv run alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
uv run alembic -c backend/alembic.ini check                # fails if models and migrations differ
docker compose -f infra/docker-compose.yml down            # stop (add -v to delete the data)
```

The API also needs `NEXTPAY_JWT_SECRET` (any 32+ characters locally; `.env.example` has
one). Migrations don't: they read only the database settings. Auth design: ADR 0009.

Database tests use `NEXTPAY_TEST_DATABASE_URL`, a database they drop and recreate,
and are skipped when it is unset. CI always runs them.

### The API

With the API running, the interactive docs are at `http://localhost:8000/docs`. Sign in
with `/auth/register` or `/auth/login`, then send the access token as a Bearer token.

| Resource | Routes |
|---|---|
| `/income-sources`, `/bills`, `/essential-expenses`, `/debts`, `/goals` | `POST`, `GET`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` |
| `/balance-snapshots` | `POST`, `GET` (append-only) |
| `/me/settings` | `PUT` (time zone, goal share) |
| `/paychecks` | `GET` (the timeline of paydays) |
| `/income-sources/{id}/paychecks/{pay_date}` | `PUT` (record what actually arrived) |
| `/plans` | `POST` (plan a paycheck), `GET /{id}`, `POST /{id}/commit` |
| `/bills/{id}/payments`, `/debts/{id}/payments` | `POST`, `GET` (send an `id` you made so a retry pays once) |
| `/dashboard` | `GET` (today, current and next paydays, Safe to Spend, balance) |

Money is integer cents. `PUT` replaces the whole resource, so every field is required and
a nullable one must be sent as `null`. Conventions and delete rules: ADR 0010. A 422
`validation_error` also lists each rejected field in `error.fields`, with what was wrong
(ADR 0014).

A payday goes like this: enter your balance (`POST /balance-snapshots`), find the paycheck
(`GET /paychecks`), plan it (`POST /plans`), and commit the plan. Committing sets aside
what the plan put toward bills, debts and goals; paying a bill or debt draws that down.
How plans, commits and payments work, and one known limitation: ADR 0011. A plan says
`is_out_of_date` when commit would refuse it; how every money action is safe to repeat: ADR 0015.
The dashboard's Safe to Spend falls when a payment goes beyond what was set aside: ADR 0016.

### The mobile app

Setup, daily commands, reaching the API from a phone, and building for iOS are in
[mobile/README.md](mobile/README.md). Decisions: ADR 0012. After any change to the API, run
`npm run api:generate` in `mobile/` and commit the result; CI fails otherwise.

## Ground rules

1. All financial math lives in `engine/`. Never in the backend routes, never in the app.
2. Money is integer cents. Never floats. (ADR 0001)
3. The engine never imports from the backend, FastAPI, SQLAlchemy, or Pydantic. CI enforces this.
4. Every major decision gets a short ADR in `docs/adr/`.
