# infra

`docker-compose.yml` runs PostgreSQL 17 for local development. The API itself runs
on the host (`uv run fastapi dev backend/app/main.py`) and connects on
`localhost:5432`; containerizing it waits for hosting (ADR 0007). Set
`NEXTPAY_POSTGRES_PORT` to publish on another port if 5432 is taken.

See the repository README for the commands.
