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
from app.services.strategy_run_events import (
    EVENT_APPROVAL_DECISION,
    EVENT_EVALUATE,
    EVENT_JUDGE_VERDICT,
    EVENT_ORDER_FILL,
    EVENT_ORDER_REJECT,
    EVENT_ORDER_SUBMIT,
    EVENT_POSITION_ADOPTION,
    EVENT_RISK_HALT,
    EVENT_RISK_REJECT,
    EVENT_RISK_THROTTLE,
    EVENT_RUN_STARTED,
    EVENT_RUN_STOPPED,
    EVENT_SIGNAL,
    EVENT_STOP_HIT,
    emit_strategy_run_event,
)


def _migrate(db_path: Path) -> None:
    env_vars = os.environ.copy()
    env_vars["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    subprocess.run(
        [".venv/bin/python", "-m", "alembic", "upgrade", "020"],
        env=env_vars,
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
async def test_emit_strategy_run_event_adds_to_session() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "events.db"
        _migrate(db_path)
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
            event_row = emit_strategy_run_event(
                session,
                run_id=run.id,
                event_kind=EVENT_SIGNAL,
                level=StrategyRunEventLevel.info,
                payload={"target": 1, "ema_8": 100.0},
                bar_ts=datetime(2026, 6, 15, 13, 30, tzinfo=UTC),
            )
            assert event_row.run_id == run.id
            assert event_row.event_kind == EVENT_SIGNAL
            assert event_row.payload == {"target": 1, "ema_8": 100.0}
            await session.commit()
            rows = (
                await session.scalars(
                    select(StrategyRunEvent).where(StrategyRunEvent.run_id == run.id)
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].event_kind == EVENT_SIGNAL
        await engine.dispose()


def test_event_kind_constants_cover_runner_lifecycle() -> None:
    constants = {
        EVENT_APPROVAL_DECISION,
        EVENT_EVALUATE,
        EVENT_JUDGE_VERDICT,
        EVENT_ORDER_FILL,
        EVENT_ORDER_REJECT,
        EVENT_ORDER_SUBMIT,
        EVENT_POSITION_ADOPTION,
        EVENT_RISK_HALT,
        EVENT_RISK_REJECT,
        EVENT_RISK_THROTTLE,
        EVENT_RUN_STARTED,
        EVENT_RUN_STOPPED,
        EVENT_SIGNAL,
        EVENT_STOP_HIT,
    }
    expected = {
        "approval_decision",
        "evaluate",
        "judge_verdict",
        "order_fill",
        "order_reject",
        "order_submit",
        "position_adoption",
        "risk_halt",
        "risk_reject",
        "risk_throttle",
        "run_started",
        "run_stopped",
        "signal",
        "stop_hit",
    }
    assert constants == expected
