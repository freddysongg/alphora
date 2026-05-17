import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from sqlalchemy import event

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
