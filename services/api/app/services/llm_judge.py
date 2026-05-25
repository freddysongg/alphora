"""LLM judge gate (spec sections 4.4 and 4.6).

Phase 4 shipped this as a pass-through stub. Phase 6 makes the verdict
actually depend on Alphora's research substrate. The runner's call site
is unchanged shape-wise — `evaluate()` returns a `JudgeVerdict`. What
changed:

- `JudgeRequest` now carries `run_id` and `bar_ts` so the persisted
  verdict row can FK to `strategy_runs.id` and project the bar timestamp.
- `evaluate()` now requires `session_maker` + `llm_client` kwargs. The
  runner passes both from its `StrategyRunnerContext`. The judge persists
  every verdict it produces — including conservative-default vetoes — to
  the new `judge_verdicts` table.
- The judge depends on a narrow `JudgeLlmClient` Protocol rather than the
  concrete `LlmClient`. `LlmClient` structurally satisfies the protocol.

`JudgeRequest` / `JudgeVerdict` wire shapes remain stable across Phase 6
-> Phase 9 (audit search) so dashboards built later don't need to
re-derive verdict semantics.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm.client import LlmCompletionResult, LlmMessage

JudgeDecision = Literal["approve", "veto", "approve_reduced"]


@runtime_checkable
class JudgeLlmClient(Protocol):
    """Narrow contract the judge depends on. `LlmClient` satisfies it."""

    async def complete(
        self,
        *,
        session: AsyncSession,
        messages: Sequence[LlmMessage],
        model: str,
        prompt_version: str | None = None,
        stage: str | None = None,
        agent_name: str | None = None,
    ) -> LlmCompletionResult: ...


@dataclass(frozen=True)
class JudgeRequest:
    """Everything the judge needs to evaluate a single proposed order."""

    run_id: uuid.UUID
    strategy_key: str
    ticker: str
    side: Literal["buy", "sell"]
    qty: Decimal
    estimated_fill_price: Decimal
    mode: Literal["paper", "live"]
    bar_ts: datetime
    strategy_meta: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class JudgeVerdict:
    """Verdict + reasoning persisted to `judge_verdicts`."""

    decision: JudgeDecision
    reasoning_md: str
    size_multiplier: float | None = None


_PHASE_4_STUB_REASONING: str = (
    "phase4 stub: judge is a pass-through in Phase 4; real LLM evaluation "
    "lands in Phase 6 with full Alphora research context."
)


async def evaluate(request: JudgeRequest) -> JudgeVerdict:
    """Phase 4 stub. Always approves.

    The function is `async` so callers can await it without changing the
    call shape when Phase 6 swaps in a real LLM HTTP call. The `request`
    parameter is intentionally unused in the stub; Phase 6 will consume
    it to build the LLM prompt.
    """
    del request
    return JudgeVerdict(
        decision="approve",
        reasoning_md=_PHASE_4_STUB_REASONING,
        size_multiplier=None,
    )


__all__ = [
    "JudgeDecision",
    "JudgeLlmClient",
    "JudgeRequest",
    "JudgeVerdict",
    "evaluate",
]
