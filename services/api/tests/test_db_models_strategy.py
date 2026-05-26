from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_strategy import StrategyConfig


@pytest.mark.asyncio
async def test_strategy_config_round_trip(db_session: AsyncSession) -> None:
    cfg = StrategyConfig(
        id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        params={"fast": 12, "slow": 26, "signal": 9},
        notes="Phase 3 sweep best params",
    )
    db_session.add(cfg)
    await db_session.commit()
    rows = (await db_session.execute(select(StrategyConfig))).scalars().all()
    assert len(rows) == 1
    assert rows[0].strategy_key == "macd_rsi_adx"
    assert rows[0].ticker == "SPY"
    assert rows[0].params == {"fast": 12, "slow": 26, "signal": 9}
    assert rows[0].notes == "Phase 3 sweep best params"


@pytest.mark.asyncio
async def test_strategy_config_unique_strategy_ticker_pair(
    db_session: AsyncSession,
) -> None:
    db_session.add(
        StrategyConfig(
            id=uuid.uuid4(),
            strategy_key="bb_rsi",
            ticker="QQQ",
            params={"bb_period": 20},
        )
    )
    await db_session.commit()
    db_session.add(
        StrategyConfig(
            id=uuid.uuid4(),
            strategy_key="bb_rsi",
            ticker="QQQ",
            params={"bb_period": 30},
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_strategy_config_allows_same_strategy_different_tickers(
    db_session: AsyncSession,
) -> None:
    db_session.add(
        StrategyConfig(
            id=uuid.uuid4(),
            strategy_key="bb_rsi",
            ticker="SPY",
            params={"bb_period": 20},
        )
    )
    db_session.add(
        StrategyConfig(
            id=uuid.uuid4(),
            strategy_key="bb_rsi",
            ticker="QQQ",
            params={"bb_period": 25},
        )
    )
    await db_session.commit()
    rows = (await db_session.execute(select(StrategyConfig))).scalars().all()
    assert len(rows) == 2
