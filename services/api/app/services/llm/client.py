import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import RunEvent, RunEventLevel
from app.schemas.budget import (
    BudgetAction,
    BudgetDecision,
    TokenUsage,
)
from app.services.budget import BudgetGuard, compute_cost

MessageRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class LlmMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True)
class LlmCompletionResult:
    content: str
    model: str
    usage: TokenUsage
    cost_usd: Decimal
    latency_ms: int
    log_id: UUID


class BudgetPausedError(Exception):
    def __init__(self, decision: BudgetDecision) -> None:
        super().__init__(decision.reason or "budget pause")
        self.decision = decision


class BudgetKilledError(Exception):
    def __init__(self, decision: BudgetDecision) -> None:
        super().__init__(decision.reason or "budget kill")
        self.decision = decision


class LlmClient:
    """Thin OpenAI wrapper that logs every call and enforces budgets.

    Each call:
      1. Hashes the request (prompt and full input) for idempotency / cache lookup.
      2. Calls OpenAI Chat Completions.
      3. Extracts token usage (input, output, cached input, reasoning).
      4. Computes cost via the owned pricing config.
      5. Sums prior costs for the run and the day from llm_call_logs.
      6. Asks BudgetGuard.evaluate for an action.
      7. Persists an LlmCallLog row with status reflecting the decision.
      8. Emits a RunEvent with level=info and a "cost" payload.
      9. On allow/warn: returns LlmCompletionResult.
         On pause: raises BudgetPausedError.
         On kill: raises BudgetKilledError.
    """

    def __init__(
        self,
        *,
        openai_client: AsyncOpenAI,
        budget_guard: BudgetGuard | None = None,
    ) -> None:
        self._openai = openai_client
        self._guard = budget_guard if budget_guard is not None else BudgetGuard()

    async def complete(
        self,
        *,
        session: AsyncSession,
        messages: Sequence[LlmMessage],
        model: str,
        run_id: UUID | None = None,
        evidence_ids: Sequence[str] | None = None,
    ) -> LlmCompletionResult:
        prompt_hash = _hash_messages(messages)
        input_hash = _hash_input(model=model, messages=messages)
        started = time.monotonic()
        openai_messages = cast(
            list[ChatCompletionMessageParam],
            [{"role": m.role, "content": m.content} for m in messages],
        )
        try:
            response = await self._openai.chat.completions.create(
                model=model,
                messages=openai_messages,
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            await _persist_log(
                session,
                run_id=run_id,
                model=model,
                prompt_hash=prompt_hash,
                input_hash=input_hash,
                usage=TokenUsage(),
                cost_usd=Decimal("0"),
                latency_ms=latency_ms,
                status=LlmCallStatus.error,
                error_message=str(exc),
                evidence_ids=list(evidence_ids) if evidence_ids else None,
            )
            await session.commit()
            raise
        latency_ms = int((time.monotonic() - started) * 1000)
        usage = _extract_usage(response)
        cost = compute_cost(usage, model)
        run_cost = await _sum_run_cost(session, run_id) + cost if run_id else cost
        daily_cost = await _sum_daily_cost(session) + cost
        decision = self._guard.evaluate(
            run_cost_usd=run_cost,
            daily_cost_usd=daily_cost,
        )
        status = _status_for_decision(decision)
        log = await _persist_log(
            session,
            run_id=run_id,
            model=model,
            prompt_hash=prompt_hash,
            input_hash=input_hash,
            usage=usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            status=status,
            error_message=None,
            evidence_ids=list(evidence_ids) if evidence_ids else None,
        )
        if run_id is not None:
            await _emit_cost_event(
                session,
                run_id=run_id,
                model=model,
                usage=usage,
                cost=cost,
                cumulative_run_cost=run_cost,
                decision=decision,
            )
        await session.commit()
        if decision.action is BudgetAction.kill:
            raise BudgetKilledError(decision)
        if decision.action is BudgetAction.pause:
            raise BudgetPausedError(decision)
        content_raw = response.choices[0].message.content
        content = content_raw if isinstance(content_raw, str) else ""
        return LlmCompletionResult(
            content=content,
            model=model,
            usage=usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            log_id=log.id,
        )


def _hash_messages(messages: Sequence[LlmMessage]) -> str:
    canonical = "\n".join(f"{m.role}:{m.content}" for m in messages)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hash_input(*, model: str, messages: Sequence[LlmMessage]) -> str:
    payload = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _extract_usage(response: object) -> TokenUsage:
    """Extract token usage from a Chat Completions response.

    Handles both classic prompt_tokens/completion_tokens and the newer
    input_tokens/output_tokens with details. Missing fields default to 0.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return TokenUsage()
    input_tokens = (
        getattr(usage, "input_tokens", None)
        or getattr(usage, "prompt_tokens", None)
        or 0
    )
    output_tokens = (
        getattr(usage, "output_tokens", None)
        or getattr(usage, "completion_tokens", None)
        or 0
    )
    cached_input_tokens = 0
    reasoning_tokens = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached_input_tokens = getattr(details, "cached_tokens", 0) or 0
    output_details = getattr(usage, "completion_tokens_details", None)
    if output_details is not None:
        reasoning_tokens = getattr(output_details, "reasoning_tokens", 0) or 0
    return TokenUsage(
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        cached_input_tokens=int(cached_input_tokens),
        reasoning_tokens=int(reasoning_tokens),
    )


def _status_for_decision(decision: BudgetDecision) -> LlmCallStatus:
    if decision.action is BudgetAction.kill:
        return LlmCallStatus.budget_killed
    if decision.action is BudgetAction.pause:
        return LlmCallStatus.budget_paused
    return LlmCallStatus.success


async def _persist_log(
    session: AsyncSession,
    *,
    run_id: UUID | None,
    model: str,
    prompt_hash: str,
    input_hash: str,
    usage: TokenUsage,
    cost_usd: Decimal,
    latency_ms: int,
    status: LlmCallStatus,
    error_message: str | None,
    evidence_ids: list[str] | None,
) -> LlmCallLog:
    log = LlmCallLog(
        run_id=run_id,
        model=model,
        prompt_hash=prompt_hash,
        input_hash=input_hash,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        status=status,
        error_message=error_message,
        evidence_ids=evidence_ids,
    )
    session.add(log)
    await session.flush()
    return log


async def _sum_run_cost(session: AsyncSession, run_id: UUID | None) -> Decimal:
    if run_id is None:
        return Decimal("0")
    stmt = select(LlmCallLog.cost_usd).where(LlmCallLog.run_id == run_id)
    rows = (await session.execute(stmt)).scalars().all()
    total = Decimal("0")
    for value in rows:
        total += value
    return total


async def _sum_daily_cost(session: AsyncSession) -> Decimal:
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(LlmCallLog.cost_usd).where(LlmCallLog.created_at >= today_start)
    rows = (await session.execute(stmt)).scalars().all()
    total = Decimal("0")
    for value in rows:
        total += value
    return total


async def _emit_cost_event(
    session: AsyncSession,
    *,
    run_id: UUID,
    model: str,
    usage: TokenUsage,
    cost: Decimal,
    cumulative_run_cost: Decimal,
    decision: BudgetDecision,
) -> None:
    level = (
        RunEventLevel.warn
        if decision.action is not BudgetAction.allow
        else RunEventLevel.info
    )
    data: dict[str, object] = {
        "event": "cost",
        "model": model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "cost_usd": str(cost),
        "cumulative_run_cost_usd": str(cumulative_run_cost),
        "budget_action": decision.action.value,
    }
    if decision.threshold_crossed is not None:
        data["threshold_crossed"] = decision.threshold_crossed.value
    session.add(
        RunEvent(
            run_id=run_id,
            level=level,
            message=f"llm call cost ${cost}",
            data=data,
        )
    )
