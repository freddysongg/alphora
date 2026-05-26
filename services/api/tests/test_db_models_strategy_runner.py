from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunEvent,
    StrategyRunEventLevel,
    StrategyRunMode,
    StrategyRunStatus,
)


def _run_alembic_upgrade(db_path: Path, revision: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    subprocess.run(
        [".venv/bin/python", "-m", "alembic", "upgrade", revision],
        env=env,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )


def _build_engine(db_path: Path) -> AsyncEngine:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn: DBAPIConnection, _: ConnectionPoolEntry) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


@pytest.mark.asyncio
async def test_strategy_run_insertable_with_required_columns() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "models_runner.db"
        _run_alembic_upgrade(db_path, "020")
        engine = _build_engine(db_path)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            run = StrategyRun(
                id=uuid.uuid4(),
                strategy_key="macd_rsi_adx",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.pending.value,
                params={"adx_min": 25.0},
            )
            session.add(run)
            await session.commit()
            stmt = select(StrategyRun).where(StrategyRun.id == run.id)
            result = await session.scalar(stmt)
            assert result is not None
            assert result.strategy_key == "macd_rsi_adx"
            assert result.status == "pending"
            assert result.params == {"adx_min": 25.0}
        await engine.dispose()


@pytest.mark.asyncio
async def test_strategy_run_event_fk_cascades_on_run_delete() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "models_runner_cascade.db"
        _run_alembic_upgrade(db_path, "020")
        engine = _build_engine(db_path)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            run = StrategyRun(
                id=uuid.uuid4(),
                strategy_key="macd_rsi_adx",
                ticker="SPY",
                mode=StrategyRunMode.paper.value,
                status=StrategyRunStatus.running.value,
                params={},
            )
            session.add(run)
            await session.flush()
            run_event = StrategyRunEvent(
                id=uuid.uuid4(),
                run_id=run.id,
                bar_ts=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
                event_kind="signal",
                level=StrategyRunEventLevel.info.value,
                payload={"target": 1},
            )
            session.add(run_event)
            await session.commit()
            event_id = run_event.id
            await session.delete(run)
            await session.commit()
            stmt = select(StrategyRunEvent).where(StrategyRunEvent.id == event_id)
            assert await session.scalar(stmt) is None
        await engine.dispose()


def test_strategy_run_status_enum_values_match_spec() -> None:
    """Spec §11.1: pending, running, paused, stopped, errored."""
    expected = {"pending", "running", "paused", "stopped", "errored"}
    actual = {s.value for s in StrategyRunStatus}
    assert actual == expected


def test_strategy_run_mode_enum_values_match_spec() -> None:
    expected = {"paper", "live"}
    actual = {s.value for s in StrategyRunMode}
    assert actual == expected


def test_strategy_run_event_level_enum_values() -> None:
    expected = {"info", "warn", "error"}
    actual = {s.value for s in StrategyRunEventLevel}
    assert actual == expected


def test_models_re_export() -> None:
    from app.db.models import (
        StrategyRun,
        StrategyRunEvent,
        StrategyRunEventLevel,
        StrategyRunMode,
        StrategyRunStatus,
    )
    assert StrategyRun.__name__ == "StrategyRun"
    assert StrategyRunEvent.__name__ == "StrategyRunEvent"
    assert StrategyRunMode.paper.value == "paper"
    assert StrategyRunStatus.running.value == "running"
    assert StrategyRunEventLevel.info.value == "info"
