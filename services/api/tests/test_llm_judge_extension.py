from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.services.llm_judge import JudgeLlmClient, JudgeRequest


def test_judge_request_carries_run_id_and_bar_ts() -> None:
    rid = uuid.uuid4()
    ts = datetime(2026, 5, 24, 14, 30, tzinfo=UTC)
    req = JudgeRequest(
        run_id=rid,
        strategy_key="macd_rsi_adx",
        ticker="NVDA",
        side="buy",
        qty=Decimal("10"),
        estimated_fill_price=Decimal("450.00"),
        mode="paper",
        bar_ts=ts,
    )
    assert req.run_id == rid
    assert req.bar_ts == ts
    assert req.strategy_meta == {}


def test_judge_llm_client_protocol_is_runtime_checkable() -> None:
    """A minimal stub that implements `complete` must pass isinstance against the Protocol."""
    from collections.abc import Sequence
    from decimal import Decimal
    from uuid import uuid4

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.budget import TokenUsage
    from app.services.llm.client import LlmCompletionResult, LlmMessage

    class _MinimalStub:
        async def complete(
            self,
            *,
            session: AsyncSession,
            messages: Sequence[LlmMessage],
            model: str,
            prompt_version: str | None = None,
            stage: str | None = None,
            agent_name: str | None = None,
        ) -> LlmCompletionResult:
            return LlmCompletionResult(
                content="{}",
                model=model,
                usage=TokenUsage(),
                cost_usd=Decimal("0"),
                latency_ms=0,
                log_id=uuid4(),
            )

    assert isinstance(_MinimalStub(), JudgeLlmClient)
