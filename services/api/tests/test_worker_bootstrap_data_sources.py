"""Verify the worker seeds `data_sources` once per `asyncio.run` cycle,
before dispatch, so per-ingestion `Evidence.source_id` lookups resolve."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.workers.tasks as tasks_module
from app.db.models_graph import DataSource
from app.services.data_sources_bootstrap import KNOWN_DATA_SOURCES
from app.services.source_clients._registry import reset_registry


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    reset_registry()
    yield
    reset_registry()


@pytest.mark.asyncio
async def test_run_with_source_client_runtime_bootstraps_data_sources_before_dispatch(
    initialized_schema: None,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dispatch must observe the canonical `data_sources` rows already
    committed when `_run_with_source_client_runtime` runs."""
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        tasks_module, "_build_async_redis_client", lambda: fake_redis
    )

    observed: dict[str, set[str]] = {}

    async def fake_dispatch(_: object) -> None:
        from app.db.session import session_factory

        async with session_factory() as probe:
            rows = (await probe.execute(select(DataSource))).scalars().all()
            observed["names"] = {row.name for row in rows}

    monkeypatch.setattr(tasks_module, "_dispatch", fake_dispatch)

    await tasks_module._run_with_source_client_runtime(uuid4())

    expected = {seed.name for seed in KNOWN_DATA_SOURCES}
    assert observed["names"] == expected


@pytest.mark.asyncio
async def test_bootstrap_data_sources_for_run_is_idempotent(
    initialized_schema: None,
    db_session: AsyncSession,
) -> None:
    """Two calls in the same worker process must not duplicate rows."""
    await tasks_module._bootstrap_data_sources_for_run()
    await tasks_module._bootstrap_data_sources_for_run()

    rows = (await db_session.execute(select(DataSource))).scalars().all()
    assert len(rows) == len(KNOWN_DATA_SOURCES)


@pytest.mark.asyncio
async def test_run_with_source_client_runtime_still_tears_down_when_bootstrap_fails(
    initialized_schema: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bootstrap failure must not leak the Redis client or registry state."""
    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()
    monkeypatch.setattr(
        tasks_module, "_build_async_redis_client", lambda: fake_redis
    )

    async def failing_bootstrap() -> None:
        raise RuntimeError("bootstrap boom")

    dispatched: dict[str, bool] = {"called": False}

    async def fake_dispatch(_: object) -> None:
        dispatched["called"] = True

    monkeypatch.setattr(
        tasks_module, "_bootstrap_data_sources_for_run", failing_bootstrap
    )
    monkeypatch.setattr(tasks_module, "_dispatch", fake_dispatch)

    with pytest.raises(RuntimeError, match="bootstrap boom"):
        await tasks_module._run_with_source_client_runtime(uuid4())

    assert dispatched["called"] is False
    fake_redis.aclose.assert_awaited_once()
