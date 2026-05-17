# alphora-api

FastAPI backend for the Alphora research desk. Wraps the TradingAgents engine, persists runs and reports to Postgres, and brokers background jobs via Redis/RQ.

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2.0 (async)
- Postgres 16 via asyncpg, Alembic for migrations
- Redis + RQ for the worker (separate service)
- structlog for structured logging

## Install

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`uv sync` also works if you prefer uv.

## Run

```bash
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

API is served at `http://localhost:8000/api`. Health probe: `GET /api/health`.

## Tests

```bash
pytest -q
```

Tests use an in-memory SQLite database via aiosqlite. No Postgres or Redis is required for the test suite.

## Migrations

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Lint & types

```bash
ruff check .
mypy app/
```
