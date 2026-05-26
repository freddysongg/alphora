"""LLM judge gate (spec sections 4.4 and 4.6).

Phase 4 ships the call site as a pass-through stub that always returns
`approve`. Phase 6 swaps the implementation to call a real LLM with
Alphora research context (filings, news sentiment, macro, sector,
congressional trades, prediction-market priors); the runner's call site
does not change.

JudgeRequest / JudgeVerdict dataclasses are the wire shape — designed
to remain stable across Phase 4 -> Phase 6 -> Phase 9 (audit search) so
persistence layers can be added without disrupting callers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

JudgeDecision = Literal["approve", "veto", "approve_reduced"]


@dataclass(frozen=True)
class JudgeRequest:
    """Everything the judge needs to evaluate a single proposed order.

    `strategy_meta` is the strategy's `StrategyResult.meta` verbatim;
    Phase 6 will augment with research-context fields pulled from the
    Alphora substrate.
    """

    strategy_key: str
    ticker: str
    side: Literal["buy", "sell"]
    qty: Decimal
    estimated_fill_price: Decimal
    mode: Literal["paper", "live"]
    strategy_meta: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class JudgeVerdict:
    """Verdict + reasoning persisted to `judge_verdicts` in Phase 6.

    `size_multiplier` is non-None only when `decision == "approve_reduced"`;
    the runner multiplies its proposed `qty` by this factor.
    """

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
    "JudgeRequest",
    "JudgeVerdict",
    "evaluate",
]
