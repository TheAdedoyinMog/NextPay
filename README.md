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
uv run fastapi dev backend/app/main.py   # start the API (needs fastapi[standard])
```

### Local database

Requires Docker. Settings come from `NEXTPAY_*` environment variables; copy
`.env.example` to `.env` for local defaults (PowerShell: `Copy-Item .env.example .env`).

```bash
docker compose -f infra/docker-compose.yml up -d --wait   # PostgreSQL 17 on localhost:5432
uv run alembic -c backend/alembic.ini upgrade head         # create or update the schema
uv run alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
uv run alembic -c backend/alembic.ini check                # fails if models and migrations differ
docker compose -f infra/docker-compose.yml down            # stop (add -v to delete the data)
```

Database tests use `NEXTPAY_TEST_DATABASE_URL`, a database they drop and recreate,
and are skipped when it is unset. CI always runs them.

## Ground rules

1. All financial math lives in `engine/`. Never in the backend routes, never in the app.
2. Money is integer cents. Never floats. (ADR 0001)
3. The engine never imports from the backend, FastAPI, SQLAlchemy, or Pydantic. CI enforces this.
4. Every major decision gets a short ADR in `docs/adr/`.
