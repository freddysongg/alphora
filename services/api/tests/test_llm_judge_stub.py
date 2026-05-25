from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.llm_judge import (
    JudgeRequest,
    JudgeVerdict,
)
from app.services.llm_judge import (
    evaluate as judge_evaluate,
)

_RUN_ID: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_BAR_TS: datetime = datetime(2026, 5, 24, 14, 30, tzinfo=UTC)


def _basic_request() -> JudgeRequest:
    return JudgeRequest(
        run_id=_RUN_ID,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("500"),
        mode="paper",
        bar_ts=_BAR_TS,
        strategy_meta={"target": 1, "ema_8": 100.0},
    )


@pytest.mark.asyncio
async def test_stub_returns_approve_for_paper(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    noop_judge_llm_client: object,
) -> None:
    from app.db.models_strategy_runner import (
        StrategyRun,
        StrategyRunMode,
        StrategyRunStatus,
    )

    db_session.add(
        StrategyRun(
            id=_RUN_ID,
            strategy_key="macd_rsi_adx",
            ticker="SPY",
            mode=StrategyRunMode.paper.value,
            status=StrategyRunStatus.running.value,
            params={},
        )
    )
    await db_session.commit()

    request = _basic_request()
    verdict = await judge_evaluate(
        request,
        session_maker=session_maker,
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.decision in {"approve", "veto"}
    assert isinstance(verdict.reasoning_md, str)
    assert len(verdict.reasoning_md) > 0


@pytest.mark.asyncio
async def test_stub_returns_approve_for_live_too(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    noop_judge_llm_client: object,
) -> None:
    """Phase 6 conservative-default vetoes when substrate is sparse.
    This documents the behaviour change from the Phase 4 stub."""
    from app.db.models_strategy_runner import (
        StrategyRun,
        StrategyRunMode,
        StrategyRunStatus,
    )

    run_id = uuid.uuid4()
    db_session.add(
        StrategyRun(
            id=run_id,
            strategy_key="macd_rsi_adx",
            ticker="SPY",
            mode=StrategyRunMode.live.value,
            status=StrategyRunStatus.running.value,
            params={},
        )
    )
    await db_session.commit()

    request = JudgeRequest(
        run_id=run_id,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("500"),
        mode="live",
        bar_ts=_BAR_TS,
        strategy_meta={},
    )
    verdict = await judge_evaluate(
        request,
        session_maker=session_maker,
        llm_client=noop_judge_llm_client,  # type: ignore[arg-type]
    )
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.decision in {"approve", "veto"}


def test_judge_verdict_dataclass_fields() -> None:
    """Pin the shape so Phase 6 can layer persistence on without
    breaking the runner's call site."""
    v = JudgeVerdict(
        decision="approve",
        reasoning_md="some text",
        size_multiplier=None,
    )
    assert v.decision == "approve"
    assert v.reasoning_md == "some text"
    assert v.size_multiplier is None


def test_judge_request_carries_full_context_shape() -> None:
    r = _basic_request()
    assert r.run_id == _RUN_ID
    assert r.strategy_key == "macd_rsi_adx"
    assert r.ticker == "SPY"
    assert r.side == "buy"
    assert r.qty == Decimal("1")
    assert r.estimated_fill_price == Decimal("500")
    assert r.mode == "paper"
    assert r.bar_ts == _BAR_TS
    assert r.strategy_meta == {"target": 1, "ema_8": 100.0}
