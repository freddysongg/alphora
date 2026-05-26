"""Runner refuses to start when mode=live AND HUMAN_APPROVAL_TOKEN is empty."""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.brokers.base import Bar, Position, TradabilityCheck
from app.services.strategy_runner import StrategyRunnerContext, run
from app.strategies.base import StrategyResult, Timeframe

_StrategyParams = dict[str, float | int | bool | str]


class _NoopBroker:
    """Minimal broker stub whose stream_bars yields nothing."""

    async def get_positions(self) -> list[Position]:
        return []

    async def is_tradable(self, ticker: str) -> TradabilityCheck:
        return TradabilityCheck(
            ticker=ticker,
            is_tradable=True,
            is_shortable=True,
            is_halted=False,
            fractionable=True,
        )

    def stream_bars(self, tickers: list[str], timeframe: str) -> AsyncIterator[Bar]:
        async def _gen() -> AsyncIterator[Bar]:
            return
            yield  # makes _gen an async generator; never reached

        return _gen()


class _NoopStrategy:
    key: str = "noop"
    name: str = "Noop"
    primary_timeframe: Timeframe = "1min"
    secondary_timeframes: list[Timeframe] = []  # noqa: RUF012
    requires_rth: bool = False

    def evaluate(
        self,
        primary_bars: object,
        secondary_bars: object,
        current_position: int,
        params: _StrategyParams,
    ) -> StrategyResult:
        return StrategyResult(
            target=0, size_hint=None, stop_pts=None, target_pts=None, trail=None, meta={}
        )


@pytest.mark.asyncio
async def test_runner_refuses_live_without_token(
    monkeypatch: pytest.MonkeyPatch,
    noop_judge_llm_client: object,
    session_maker: async_sessionmaker,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", "")
    get_settings.cache_clear()

    ctx = StrategyRunnerContext(
        run_id=uuid.uuid4(),
        strategy=_NoopStrategy(),
        ticker="SPY",
        mode="live",
        params={},
        broker=_NoopBroker(),  # type: ignore[arg-type]
        session_maker=session_maker,
        cancel_event=asyncio.Event(),
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError, match="HUMAN_APPROVAL_TOKEN"):
        await run(ctx)
    get_settings.cache_clear()
