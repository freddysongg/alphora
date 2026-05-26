from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.llm_judge import (
    JudgeRequest,
    JudgeVerdict,
)
from app.services.llm_judge import (
    evaluate as judge_evaluate,
)


def _basic_request() -> JudgeRequest:
    return JudgeRequest(
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("500"),
        mode="paper",
        strategy_meta={"target": 1, "ema_8": 100.0},
    )


@pytest.mark.asyncio
async def test_stub_returns_approve_for_paper() -> None:
    request = _basic_request()
    verdict = await judge_evaluate(request)
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.decision == "approve"
    assert verdict.reasoning_md.startswith("phase4 stub")
    assert verdict.size_multiplier is None


@pytest.mark.asyncio
async def test_stub_returns_approve_for_live_too() -> None:
    """The stub is mode-blind — Phase 6 introduces real LLM logic that
    might veto in live. Phase 4's stub must approve both so the runner's
    parity-correct call path works for both modes from day one."""
    request = JudgeRequest(
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("500"),
        mode="live",
        strategy_meta={},
    )
    verdict = await judge_evaluate(request)
    assert verdict.decision == "approve"


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
    assert r.strategy_key == "macd_rsi_adx"
    assert r.ticker == "SPY"
    assert r.side == "buy"
    assert r.qty == Decimal("1")
    assert r.estimated_fill_price == Decimal("500")
    assert r.mode == "paper"
    assert r.strategy_meta == {"target": 1, "ema_8": 100.0}
