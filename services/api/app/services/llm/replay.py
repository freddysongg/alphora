"""Replay a logged LLM call from the stored row alone.

The replay path is informational: it does not enforce budget, does not emit
cost events, does not retry. It re-invokes the underlying chat completion
with the same model + messages + sampling params recorded in the original
row's ``input_payload`` and persists a sibling ``LlmCallReplay`` row keyed
to the original log id.

Replay output is stored separately from the original output so the audit
trail is preserved on each invocation.
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import cast
from uuid import UUID

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_llm import LlmCallLog, LlmCallReplay, LlmCallStatus
from app.services.budget import compute_cost
from app.services.llm.client import (
    ReasoningEffort,
    _extract_usage,
    _optional_openai_kwargs,
)
from app.services.model_pricing import UnknownModelError, get_pricing


class ReplayError(Exception):
    """Raised when a logged call cannot be replayed."""


async def replay_llm_call(
    *,
    session: AsyncSession,
    original_log_id: UUID,
    openai_client: AsyncOpenAI,
) -> LlmCallReplay:
    original = (
        await session.execute(
            select(LlmCallLog).where(LlmCallLog.id == original_log_id)
        )
    ).scalar_one_or_none()
    if original is None:
        raise ReplayError(f"llm_call_log {original_log_id} not found")
    payload = original.input_payload
    if not payload:
        raise ReplayError(
            f"llm_call_log {original_log_id} has no input_payload; cannot replay"
        )

    model_value = payload.get("model")
    if not isinstance(model_value, str) or not model_value:
        raise ReplayError("input_payload.model must be a non-empty string")
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        raise ReplayError("input_payload.messages must be a list")
    messages = _rehydrate_messages(raw_messages)

    temperature = _as_float(payload.get("temperature"))
    seed = _as_int(payload.get("seed"))
    reasoning_effort = _as_reasoning_effort(payload.get("reasoning_effort"))

    try:
        get_pricing(model_value)
    except UnknownModelError as exc:
        return await _persist_replay(
            session,
            original=original,
            output_content=None,
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=0,
            reasoning_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=0,
            error_message=str(exc),
            status=LlmCallStatus.error,
        )

    started = time.monotonic()
    try:
        response = await openai_client.chat.completions.create(  # type: ignore[call-overload]
            model=model_value,
            messages=messages,
            **_optional_openai_kwargs(
                temperature=temperature,
                seed=seed,
                reasoning_effort=reasoning_effort,
            ),
        )
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        return await _persist_replay(
            session,
            original=original,
            output_content=None,
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=0,
            reasoning_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=latency_ms,
            error_message=str(exc),
            status=LlmCallStatus.error,
        )

    latency_ms = int((time.monotonic() - started) * 1000)
    usage = _extract_usage(response)
    cost = compute_cost(usage, model_value)
    content_raw = response.choices[0].message.content if response.choices else ""
    content = content_raw if isinstance(content_raw, str) else ""
    return await _persist_replay(
        session,
        original=original,
        output_content=content,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        cost_usd=cost,
        latency_ms=latency_ms,
        error_message=None,
        status=LlmCallStatus.success,
    )


def _rehydrate_messages(
    raw_messages: list[object],
) -> list[ChatCompletionMessageParam]:
    messages: list[ChatCompletionMessageParam] = []
    for entry in raw_messages:
        if not isinstance(entry, dict):
            raise ReplayError("each message must be an object")
        role = entry.get("role")
        content = entry.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            raise ReplayError("message role/content must be strings")
        messages.append(
            cast(
                ChatCompletionMessageParam,
                {"role": role, "content": content},
            )
        )
    return messages


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


_REASONING_VALUES: frozenset[str] = frozenset({"minimal", "low", "medium", "high"})


def _as_reasoning_effort(value: object) -> ReasoningEffort | None:
    if isinstance(value, str) and value in _REASONING_VALUES:
        return cast(ReasoningEffort, value)
    return None


async def _persist_replay(
    session: AsyncSession,
    *,
    original: LlmCallLog,
    output_content: str | None,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int,
    reasoning_tokens: int,
    cost_usd: Decimal,
    latency_ms: int,
    error_message: str | None,
    status: LlmCallStatus,
) -> LlmCallReplay:
    replay = LlmCallReplay(
        original_log_id=original.id,
        model=original.model,
        prompt_version=original.prompt_version,
        input_payload=dict(original.input_payload or {}),
        output_content=output_content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        status=status,
        error_message=error_message,
    )
    session.add(replay)
    await session.commit()
    await session.refresh(replay)
    return replay


__all__ = ["ReplayError", "replay_llm_call"]
