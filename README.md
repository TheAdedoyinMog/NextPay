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

## Ground rules

1. All financial math lives in `engine/`. Never in the backend routes, never in the app.
2. Money is integer cents. Never floats. (ADR 0001)
3. The engine never imports from the backend, FastAPI, SQLAlchemy, or Pydantic. CI enforces this.
4. Every major decision gets a short ADR in `docs/adr/`.
