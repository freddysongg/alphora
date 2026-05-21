from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_backtest import (
    BacktestEquityPoint,
    BacktestRun,
    BacktestTrade,
)


@pytest.mark.asyncio
async def test_backtest_run_round_trip(db_session: AsyncSession) -> None:
    run = BacktestRun(
        id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        timeframe="1min",
        from_ts=datetime(2026, 4, 1, 13, 30, tzinfo=UTC),
        to_ts=datetime(2026, 4, 30, 20, 0, tzinfo=UTC),
        params={"fast": 12, "slow": 26},
        slippage_per_share_cents=2.0,
        commission_per_trade_usd=0.0,
        position_size_shares=1,
        bar_count=11700,
        trade_count=4,
        net_pnl_usd=12.34,
        win_count=3,
        loss_count=1,
        max_drawdown_usd=5.0,
        profit_factor=2.1,
    )
    db_session.add(run)
    await db_session.commit()
    result = await db_session.execute(select(BacktestRun).where(BacktestRun.id == run.id))
    fetched = result.scalar_one()
    assert fetched.strategy_key == "macd_rsi_adx"
    assert fetched.params == {"fast": 12, "slow": 26}


@pytest.mark.asyncio
async def test_backtest_trade_round_trip(db_session: AsyncSession) -> None:
    run = BacktestRun(
        id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        timeframe="1min",
        from_ts=datetime(2026, 4, 1, 13, 30, tzinfo=UTC),
        to_ts=datetime(2026, 4, 1, 20, 0, tzinfo=UTC),
        params={},
        slippage_per_share_cents=2.0,
        commission_per_trade_usd=0.0,
        position_size_shares=1,
        bar_count=0,
        trade_count=0,
        net_pnl_usd=0.0,
        win_count=0,
        loss_count=0,
        max_drawdown_usd=0.0,
        profit_factor=None,
    )
    db_session.add(run)
    await db_session.commit()
    trade = BacktestTrade(
        id=uuid.uuid4(),
        backtest_id=run.id,
        side=1,
        entry_bar_index=10,
        exit_bar_index=25,
        entry_ts=datetime(2026, 4, 1, 13, 40, tzinfo=UTC),
        exit_ts=datetime(2026, 4, 1, 13, 55, tzinfo=UTC),
        entry_price=500.02,
        exit_price=501.48,
        shares=1,
        pnl_usd=1.46,
        bars_held=15,
        exit_reason="signal",
    )
    db_session.add(trade)
    await db_session.commit()
    result = await db_session.execute(
        select(BacktestTrade).where(BacktestTrade.backtest_id == run.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].pnl_usd == 1.46


@pytest.mark.asyncio
async def test_backtest_equity_point_round_trip(db_session: AsyncSession) -> None:
    run = BacktestRun(
        id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        timeframe="1min",
        from_ts=datetime(2026, 4, 1, 13, 30, tzinfo=UTC),
        to_ts=datetime(2026, 4, 1, 20, 0, tzinfo=UTC),
        params={},
        slippage_per_share_cents=2.0,
        commission_per_trade_usd=0.0,
        position_size_shares=1,
        bar_count=0,
        trade_count=0,
        net_pnl_usd=0.0,
        win_count=0,
        loss_count=0,
        max_drawdown_usd=0.0,
        profit_factor=None,
    )
    db_session.add(run)
    await db_session.commit()
    point = BacktestEquityPoint(
        id=uuid.uuid4(),
        backtest_id=run.id,
        day=date(2026, 4, 1),
        equity_usd=1.46,
        drawdown_usd=0.0,
    )
    db_session.add(point)
    await db_session.commit()
    result = await db_session.execute(
        select(BacktestEquityPoint).where(BacktestEquityPoint.backtest_id == run.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].day == date(2026, 4, 1)
