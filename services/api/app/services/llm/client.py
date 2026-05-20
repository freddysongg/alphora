import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_runs import RunEventLevel
from app.schemas.budget import (
    BudgetAction,
    BudgetDecision,
    TokenUsage,
)
from app.services.budget import BudgetGuard, compute_cost
from app.services.model_pricing import UnknownModelError, get_pricing
from app.services.redis_lock import (
    BudgetLockFactory,
    make_local_budget_lock_factory,
)
from app.services.run_events import COST_EVENT, emit_run_event

MessageRole = Literal["system", "user", "assistant"]
ReasoningEffort = Literal["minimal", "low", "medium", "high"]


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
      7. Persists an LlmCallLog row (including rendered input_payload + output_content)
         with status reflecting the decision.
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
        budget_lock_factory: BudgetLockFactory | None = None,
    ) -> None:
        self._openai = openai_client
        self._guard = budget_guard if budget_guard is not None else BudgetGuard()
        self._budget_lock_factory = (
            budget_lock_factory
            if budget_lock_factory is not None
            else make_local_budget_lock_factory()
        )

    async def complete(
        self,
        *,
        session: AsyncSession,
        messages: Sequence[LlmMessage],
        model: str,
        run_id: UUID | None = None,
        evidence_ids: Sequence[str] | None = None,
        prompt_version: str | None = None,
        stage: str | None = None,
        agent_name: str | None = None,
        temperature: float | None = None,
        seed: int | None = None,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> LlmCompletionResult:
        prompt_hash = _hash_messages(messages)
        input_hash = _hash_input(
            model=model,
            messages=messages,
            temperature=temperature,
            seed=seed,
            reasoning_effort=reasoning_effort,
        )
        input_payload = _build_input_payload(
            model=model,
            messages=messages,
            temperature=temperature,
            seed=seed,
            reasoning_effort=reasoning_effort,
        )
        ev_ids = list(evidence_ids) if evidence_ids else None
        try:
            get_pricing(model)
        except UnknownModelError as exc:
            await _persist_log(
                session,
                run_id=run_id,
                model=model,
                prompt_hash=prompt_hash,
                input_hash=input_hash,
                usage=TokenUsage(),
                cost_usd=Decimal("0"),
                latency_ms=0,
                status=LlmCallStatus.error,
                error_message=str(exc),
                evidence_ids=ev_ids,
                prompt_version=prompt_version,
                stage=stage,
                agent_name=agent_name,
                temperature=temperature,
                seed=seed,
                reasoning_effort=reasoning_effort,
                input_payload=input_payload,
                output_content=None,
                budget_action=None,
            )
            await session.commit()
            raise
        response, latency_ms = await self._call_openai_with_error_log(
            session=session,
            run_id=run_id,
            model=model,
            messages=messages,
            prompt_hash=prompt_hash,
            input_hash=input_hash,
            evidence_ids=ev_ids,
            prompt_version=prompt_version,
            stage=stage,
            agent_name=agent_name,
            temperature=temperature,
            seed=seed,
            reasoning_effort=reasoning_effort,
            input_payload=input_payload,
        )
        usage = _extract_usage(response)
        cost = compute_cost(usage, model)
        content_raw = response.choices[0].message.content if response.choices else ""
        content = content_raw if isinstance(content_raw, str) else ""
        log, decision = await self._evaluate_and_persist(
            session=session,
            run_id=run_id,
            model=model,
            prompt_hash=prompt_hash,
            input_hash=input_hash,
            usage=usage,
            cost=cost,
            latency_ms=latency_ms,
            evidence_ids=ev_ids,
            prompt_version=prompt_version,
            stage=stage,
            agent_name=agent_name,
            temperature=temperature,
            seed=seed,
            reasoning_effort=reasoning_effort,
            input_payload=input_payload,
            output_content=content,
        )
        if decision.action is BudgetAction.kill:
            raise BudgetKilledError(decision)
        if decision.action is BudgetAction.pause:
            raise BudgetPausedError(decision)
        return LlmCompletionResult(
            content=content,
            model=model,
            usage=usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            log_id=log.id,
        )

    async def _call_openai_with_error_log(
        self,
        *,
        session: AsyncSession,
        run_id: UUID | None,
        model: str,
        messages: Sequence[LlmMessage],
        prompt_hash: str,
        input_hash: str,
        evidence_ids: list[str] | None,
        prompt_version: str | None,
        stage: str | None,
        agent_name: str | None,
        temperature: float | None,
        seed: int | None,
        reasoning_effort: ReasoningEffort | None,
        input_payload: dict[str, object],
    ) -> tuple[ChatCompletion, int]:
        """Call OpenAI. On exception, persist an error log + commit, then re-raise.

        Returns (response, latency_ms) on success.
        """
        started = time.monotonic()
        try:
            response = await self._openai.chat.completions.create(  # type: ignore[call-overload]
                model=model,
                messages=cast(
                    list[ChatCompletionMessageParam],
                    [{"role": m.role, "content": m.content} for m in messages],
                ),
                **_optional_openai_kwargs(
                    temperature=temperature,
                    seed=seed,
                    reasoning_effort=reasoning_effort,
                ),
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
                evidence_ids=evidence_ids,
                prompt_version=prompt_version,
                stage=stage,
                agent_name=agent_name,
                temperature=temperature,
                seed=seed,
                reasoning_effort=reasoning_effort,
                input_payload=input_payload,
                output_content=None,
                budget_action=None,
            )
            await session.commit()
            raise
        return response, int((time.monotonic() - started) * 1000)

    async def _evaluate_and_persist(
        self,
        *,
        session: AsyncSession,
        run_id: UUID | None,
        model: str,
        prompt_hash: str,
        input_hash: str,
        usage: TokenUsage,
        cost: Decimal,
        latency_ms: int,
        evidence_ids: list[str] | None,
        prompt_version: str | None,
        stage: str | None,
        agent_name: str | None,
        temperature: float | None,
        seed: int | None,
        reasoning_effort: ReasoningEffort | None,
        input_payload: dict[str, object],
        output_content: str,
    ) -> tuple[LlmCallLog, BudgetDecision]:
        """Sum prior costs, evaluate the guard, persist the log, emit the event, commit.

        The prior-sum + decision + persist sequence is serialized per-run via
        the configured budget lock so concurrent sector fan-out tasks cannot
        race the cumulative cost evaluation.

        Returns the persisted log + the decision so the caller can raise as needed.
        """
        async with self._budget_lock_factory(run_id):
            prior_run_cost = await _sum_run_cost(session, run_id)
            prior_daily_cost = await _sum_daily_cost(session)
            run_cost_total = prior_run_cost + cost
            daily_cost_total = prior_daily_cost + cost
            decision = self._guard.evaluate(
                run_cost_usd=run_cost_total,
                daily_cost_usd=daily_cost_total,
            )
            log = await _persist_log(
                session,
                run_id=run_id,
                model=model,
                prompt_hash=prompt_hash,
                input_hash=input_hash,
                usage=usage,
                cost_usd=cost,
                latency_ms=latency_ms,
                status=_status_for_decision(decision),
                error_message=None,
                evidence_ids=evidence_ids,
                prompt_version=prompt_version,
                stage=stage,
                agent_name=agent_name,
                temperature=temperature,
                seed=seed,
                reasoning_effort=reasoning_effort,
                input_payload=input_payload,
                output_content=output_content,
                budget_action=decision.action,
            )
            if run_id is not None:
                await _emit_cost_event(
                    session,
                    run_id=run_id,
                    log_id=log.id,
                    model=model,
                    usage=usage,
                    cost=cost,
                    cumulative_run_cost=run_cost_total,
                    decision=decision,
                )
            await session.commit()
            return log, decision


def _optional_openai_kwargs(
    *,
    temperature: float | None,
    seed: int | None,
    reasoning_effort: ReasoningEffort | None,
) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if seed is not None:
        kwargs["seed"] = seed
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    return kwargs


def _hash_messages(messages: Sequence[LlmMessage]) -> str:
    canonical = "\n".join(f"{m.role}:{m.content}" for m in messages)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hash_input(
    *,
    model: str,
    messages: Sequence[LlmMessage],
    temperature: float | None,
    seed: int | None,
    reasoning_effort: ReasoningEffort | None,
) -> str:
    payload = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": temperature,
        "seed": seed,
        "reasoning_effort": reasoning_effort,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_input_payload(
    *,
    model: str,
    messages: Sequence[LlmMessage],
    temperature: float | None,
    seed: int | None,
    reasoning_effort: ReasoningEffort | None,
) -> dict[str, object]:
    return {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": temperature,
        "seed": seed,
        "reasoning_effort": reasoning_effort,
    }


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
    prompt_version: str | None,
    stage: str | None,
    agent_name: str | None,
    temperature: float | None,
    seed: int | None,
    reasoning_effort: ReasoningEffort | None,
    input_payload: dict[str, object],
    output_content: str | None,
    budget_action: BudgetAction | None,
) -> LlmCallLog:
    call_index = await _next_call_index(session, run_id)
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
        prompt_version=prompt_version,
        stage=stage,
        agent_name=agent_name,
        call_index=call_index,
        temperature=temperature,
        seed=seed,
        reasoning_effort=reasoning_effort,
        input_payload=input_payload,
        output_content=output_content,
        budget_action=budget_action.value if budget_action is not None else None,
    )
    session.add(log)
    await session.flush()
    return log


async def _next_call_index(
    session: AsyncSession, run_id: UUID | None
) -> int | None:
    if run_id is None:
        return None
    stmt = select(func.count(LlmCallLog.id)).where(LlmCallLog.run_id == run_id)
    raw: Any = (await session.execute(stmt)).scalar_one()
    return int(raw or 0)


async def _sum_run_cost(session: AsyncSession, run_id: UUID | None) -> Decimal:
    if run_id is None:
        return Decimal("0")
    stmt = select(func.coalesce(func.sum(LlmCallLog.cost_usd), 0)).where(
        LlmCallLog.run_id == run_id
    )
    total = (await session.execute(stmt)).scalar_one()
    return total if isinstance(total, Decimal) else Decimal(str(total))


async def _sum_daily_cost(session: AsyncSession) -> Decimal:
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.coalesce(func.sum(LlmCallLog.cost_usd), 0)).where(
        LlmCallLog.created_at >= today_start
    )
    total = (await session.execute(stmt)).scalar_one()
    return total if isinstance(total, Decimal) else Decimal(str(total))


async def _emit_cost_event(
    session: AsyncSession,
    *,
    run_id: UUID,
    log_id: UUID,
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
        "event": COST_EVENT,
        "log_id": str(log_id),
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
    emit_run_event(
        session,
        run_id=run_id,
        level=level,
        message=f"llm call cost ${cost}",
        data=data,
    )
