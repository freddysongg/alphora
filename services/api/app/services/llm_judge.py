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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm.client import LlmCompletionResult, LlmMessage

if TYPE_CHECKING:
    from app.services.llm_judge_context import JudgeContext

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


async def evaluate(
    request: JudgeRequest,
    *,
    session_maker: Callable[[], AsyncSession],
    llm_client: JudgeLlmClient,
    model: str = "gpt-4o-mini",
) -> JudgeVerdict:
    """Judge the proposed order. Persists every verdict (happy + conservative).

    Returns the verdict the runner uses for its mode-policy branch:
    - "approve": runner submits at proposed.qty
    - "approve_reduced": runner submits at proposed.qty * size_multiplier
    - "veto": runner skips submit if mode == "live"; logs only if "paper"

    Three sessions: (1) `ctx_session` reads the research substrate,
    (2) `llm_session` is the handle the LlmClient uses for its own
    `llm_call_logs` write, (3) the persistence session inside
    `_persist_verdict` commits the verdict row atomically after parse
    succeeds.

    Phase 6 happy path only; Task 8 adds the four conservative-default
    branches (sparse context, LLM transport error, parse failure,
    approve_reduced with invalid multiplier).
    """
    # Deferred imports break the circular: llm_judge_prompt imports JudgeRequest/JudgeVerdict from this module.
    from app.services.llm_judge_context import gather_context
    from app.services.llm_judge_prompt import (
        PROMPT_VERSION,
        parse_verdict_response,
        render_prompt,
    )

    async with session_maker() as ctx_session:
        context = await gather_context(ctx_session, ticker=request.ticker)

    messages = render_prompt(request, context)

    async with session_maker() as llm_session:
        completion = await llm_client.complete(
            session=llm_session,
            messages=messages,
            model=model,
            prompt_version=PROMPT_VERSION,
            stage="judge",
            agent_name="strategy_judge",
        )

    parsed = parse_verdict_response(completion.content)
    if parsed is None:
        raise NotImplementedError("parse-failure branch lands in Task 8")

    await _persist_verdict(
        session_maker=session_maker,
        request=request,
        verdict=parsed,
        context=context,
        llm_model=completion.model,
        prompt_version=PROMPT_VERSION,
        llm_call_log_id=completion.log_id,
    )
    return parsed


async def _persist_verdict(
    *,
    session_maker: Callable[[], AsyncSession],
    request: JudgeRequest,
    verdict: JudgeVerdict,
    context: JudgeContext | None,
    llm_model: str | None,
    prompt_version: str | None,
    llm_call_log_id: uuid.UUID | None,
) -> None:
    from app.db.models_judge import JudgeVerdictRow
    from app.services.llm_judge_prompt import context_to_dict

    context_payload: dict[str, object]
    if context is None:
        context_payload = {}
    else:
        context_payload = context_to_dict(context)
    async with session_maker() as write_session:
        row = JudgeVerdictRow(
            id=uuid.uuid4(),
            run_id=request.run_id,
            bar_ts=request.bar_ts,
            ticker=request.ticker,
            strategy_key=request.strategy_key,
            side=request.side,
            proposed_qty=request.qty,
            decision=verdict.decision,
            size_multiplier=verdict.size_multiplier,
            reasoning_md=verdict.reasoning_md,
            context_payload=context_payload,
            llm_model=llm_model,
            prompt_version=prompt_version,
            llm_call_log_id=llm_call_log_id,
        )
        write_session.add(row)
        await write_session.commit()


__all__ = [
    "JudgeDecision",
    "JudgeLlmClient",
    "JudgeRequest",
    "JudgeVerdict",
    "evaluate",
]
