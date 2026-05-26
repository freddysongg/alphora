from __future__ import annotations

import inspect
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm.client import LlmCompletionResult, LlmMessage
from app.services.llm_judge import JudgeLlmClient


@dataclass
class _NoopJudgeLlmClient:
    log_id: uuid.UUID = field(default_factory=uuid.uuid4)

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
        import json

        from app.schemas.budget import TokenUsage

        return LlmCompletionResult(
            content=json.dumps({
                "decision": "approve",
                "reasoning_md": "noop stub for runner tests",
                "size_multiplier": None,
            }),
            model=model,
            usage=TokenUsage(),
            cost_usd=Decimal("0.00"),
            latency_ms=1,
            log_id=self.log_id,
        )


def test_strategy_runner_context_requires_llm_client() -> None:
    from app.services.strategy_runner import StrategyRunnerContext

    sig = inspect.signature(StrategyRunnerContext)
    assert "llm_client" in sig.parameters
    param = sig.parameters["llm_client"]
    assert param.default is inspect.Parameter.empty


def test_noop_judge_llm_client_satisfies_protocol() -> None:
    stub = _NoopJudgeLlmClient()
    assert isinstance(stub, JudgeLlmClient)
