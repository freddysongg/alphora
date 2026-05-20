import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_JSON"] = "false"


def _enable_sqlite_foreign_keys() -> None:
    from app.db.session import engine

    sync_engine = engine.sync_engine
    if sync_engine.dialect.name != "sqlite":
        return

    @event.listens_for(sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()


_enable_sqlite_foreign_keys()


@pytest.fixture(scope="session", autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_source_client_registry() -> Iterator[None]:
    """Reset the source-client rate-limiter / cache registry between tests.

    Worker tests install a Redis-backed limiter and a request cache into the
    registry. Without an explicit reset between tests, that state leaks into
    source-client tests, which then try to acquire tokens from a fake Redis
    or hit a stale cached response. The reset is cheap (a dict clear) and
    keeps every test starting from the default local-bucket state.
    """
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    yield
    reset_registry()


@pytest.fixture()
async def initialized_schema() -> AsyncIterator[None]:
    from app.db import models as _models  # noqa: F401
    from app.db.base import Base
    from app.db.session import engine

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture()
async def db_session(initialized_schema: None) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


class _FakeJob:
    def __init__(self, job_id: str = "job-id") -> None:
        self.id = job_id


class _FakeQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def enqueue(self, *args: Any, **kwargs: Any) -> _FakeJob:
        self.calls.append((args, kwargs))
        return _FakeJob()


@pytest.fixture()
def fake_queue() -> Iterator[_FakeQueue]:
    """Override the run-queue dependency to avoid Redis during tests."""
    from app.main import app
    from app.workers.queue import get_run_queue

    queue = _FakeQueue()
    app.dependency_overrides[get_run_queue] = lambda: queue
    try:
        yield queue
    finally:
        app.dependency_overrides.pop(get_run_queue, None)
