FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.32.0" \
        "pydantic>=2.9.0" \
        "pydantic-settings>=2.5.0" \
        "sqlalchemy>=2.0.35" \
        "asyncpg>=0.30.0" \
        "alembic>=1.13.3" \
        "structlog>=24.4.0" \
        "redis>=5.1.0" \
        "rq>=1.16.2" \
        "httpx>=0.27.2" \
        "python-multipart>=0.0.12" \
        "cryptography>=43.0.1" \
        "greenlet>=3.0.0"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

RUN pip install --no-deps -e .

RUN groupadd --system --gid 1001 alphora \
    && useradd --system --uid 1001 --gid alphora alphora \
    && chown -R alphora:alphora /srv

USER alphora

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
