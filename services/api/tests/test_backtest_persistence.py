from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_backtest import (
    BacktestEquityPoint,
    BacktestRun,
    BacktestTrade,
)
from app.services.backtest_engine import (
    CommissionModel,
    SlippageModel,
    persist_backtest_result,
    simulate,
)
from app.strategies.base import Bars, StrategyParams, StrategyResult, Timeframe
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy


def _bars(n: int, *, start: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    idx = [base + timedelta(minutes=i) for i in range(n)]
    closes = [start + step * i for i in range(n)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.25 for c in closes],
            "low": [c - 0.25 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=pd.DatetimeIndex(idx, tz="UTC"),
    )


class _LongFromBar1(MacdRsiAdxStrategy):
    def evaluate(
        self,
        primary_bars: Bars,
        secondary_bars: dict[Timeframe, Bars],
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult:
        if len(primary_bars) == 2:
            return StrategyResult(target=1, meta={})
        return StrategyResult(target=1, meta={})


@pytest.mark.asyncio
async def test_persist_backtest_result_writes_run_trades_and_equity(
    db_session: AsyncSession,
) -> None:
    bars = _bars(10)
    result = simulate(bars=bars, strategy=_LongFromBar1(), params={})
    run_id = await persist_backtest_result(
        db_session,
        result=result,
        bars=bars,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        timeframe="1min",
        params={"fast": 12},
        slippage=SlippageModel(),
        commission=CommissionModel(),
        position_size_shares=1,
    )
    runs = (await db_session.execute(select(BacktestRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].id == run_id
    assert runs[0].strategy_key == "macd_rsi_adx"
    assert runs[0].ticker == "SPY"
    assert runs[0].bar_count == 10
    trades = (
        await db_session.execute(
            select(BacktestTrade).where(BacktestTrade.backtest_id == run_id)
        )
    ).scalars().all()
    assert len(trades) >= 1
    equity = (
        await db_session.execute(
            select(BacktestEquityPoint).where(
                BacktestEquityPoint.backtest_id == run_id
            )
        )
    ).scalars().all()
    assert len(equity) >= 1


@pytest.mark.asyncio
async def test_persist_backtest_result_groups_equity_by_utc_day(
    db_session: AsyncSession,
) -> None:
    base = datetime(2026, 6, 15, 13, 30, tzinfo=UTC)
    bars = pd.DataFrame(
        {
            "open": [100.0, 100.5, 100.0, 100.5],
            "high": [100.5, 101.0, 100.5, 101.0],
            "low": [99.5, 100.0, 99.5, 100.0],
            "close": [100.5, 100.0, 100.5, 100.0],
            "volume": [1000.0] * 4,
        },
        index=pd.DatetimeIndex(
            [
                base,
                base + timedelta(minutes=1),
                base + timedelta(days=1),
                base + timedelta(days=1, minutes=1),
            ],
            tz="UTC",
        ),
    )
    result = simulate(bars=bars, strategy=_LongFromBar1(), params={})
    run_id = await persist_backtest_result(
        db_session,
        result=result,
        bars=bars,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        timeframe="1min",
        params={},
        slippage=SlippageModel(),
        commission=CommissionModel(),
        position_size_shares=1,
    )
    equity = (
        await db_session.execute(
            select(BacktestEquityPoint).where(
                BacktestEquityPoint.backtest_id == run_id
            )
        )
    ).scalars().all()
    # Two distinct UTC days resolve to two equity points.
    days = sorted(p.day for p in equity)
    assert len(days) == 2
    assert days[0] != days[1]
