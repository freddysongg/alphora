from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_backtest import BacktestRun
from app.db.models_graph import Evidence, EvidenceChunk
from app.services.backtest_engine import run_backtest
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy


async def _seed_spy_minute_bars(
    session: AsyncSession,
    *,
    start: datetime,
    minutes: int,
    start_price: float = 500.0,
    step: float = 0.01,
) -> None:
    evidence_id = uuid.uuid4()
    session.add(
        Evidence(
            id=evidence_id,
            source="polygon_aggregates",
            document_id=f"agg|SPY|{start.date()}|{start.date()}|1|minute",
            content_hash=f"e-{evidence_id}",
        )
    )
    await session.flush()
    for i in range(minutes):
        ts = start + timedelta(minutes=i)
        price = start_price + step * i
        session.add(
            EvidenceChunk(
                id=uuid.uuid4(),
                evidence_id=evidence_id,
                chunk_index=i,
                text=f"chunk-{i}",
                attributes={
                    "source": "polygon_aggregates",
                    "ticker": "SPY",
                    "timestamp_ms": int(ts.timestamp() * 1000),
                    "open": price,
                    "high": price + 0.05,
                    "low": price - 0.05,
                    "close": price,
                    "volume": 1000.0,
                },
                content_hash=f"c-{i}",
            )
        )
    await session.commit()


@pytest.mark.asyncio
async def test_run_backtest_loads_simulates_and_persists(
    db_session: AsyncSession,
) -> None:
    start = datetime(2026, 4, 1, 13, 30, tzinfo=UTC)
    await _seed_spy_minute_bars(db_session, start=start, minutes=60)
    run_id = await run_backtest(
        db_session,
        strategy=MacdRsiAdxStrategy(),
        ticker="SPY",
        from_ts=start,
        to_ts=start + timedelta(hours=1),
        params={},
    )
    runs = (await db_session.execute(select(BacktestRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].id == run_id
    assert runs[0].ticker == "SPY"
    assert runs[0].strategy_key == "macd_rsi_adx"
    assert runs[0].bar_count == 60


@pytest.mark.asyncio
async def test_run_backtest_raises_when_no_bars(db_session: AsyncSession) -> None:
    start = datetime(2026, 4, 1, 13, 30, tzinfo=UTC)
    with pytest.raises(ValueError, match="no bars"):
        await run_backtest(
            db_session,
            strategy=MacdRsiAdxStrategy(),
            ticker="SPY",
            from_ts=start,
            to_ts=start + timedelta(hours=1),
            params={},
        )
