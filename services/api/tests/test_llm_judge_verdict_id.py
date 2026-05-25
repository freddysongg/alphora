"""Phase 7: evaluate() must surface the persisted verdict-row id.

Five return paths covered:
  1. Sparse-context veto (no LLM call).
  2. LLM transport-exception veto.
  3. Parse-failure veto.
  4. approve_reduced with invalid multiplier veto.
  5. Happy-path approve verdict.

Each test seeds a strategy_run + (for non-sparse) an Entity/Hypothesis,
runs evaluate(), asserts verdict_id is a UUID matching the persisted
row's id.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_graph import Entity, EntityType, Hypothesis, HypothesisStatus
from app.db.models_judge import JudgeVerdictRow
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.schemas.budget import TokenUsage
from app.services.llm.client import LlmCompletionResult, LlmMessage
from app.services.llm_judge import JudgeRequest, JudgeVerdict, evaluate


@dataclass
class _FixedJsonLlmClient:
    response_content: str
    raise_exc: BaseException | None = None
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
        if self.raise_exc is not None:
            raise self.raise_exc
        session.add(
            LlmCallLog(
                id=self.log_id,
                model=model,
                prompt_hash="t",
                input_hash="t",
                input_tokens=0,
                output_tokens=0,
                cached_input_tokens=0,
                reasoning_tokens=0,
                cost_usd=Decimal("0"),
                latency_ms=1,
                status=LlmCallStatus.success,
                prompt_version=prompt_version,
                stage=stage,
                agent_name=agent_name,
            )
        )
        await session.commit()
        return LlmCompletionResult(
            content=self.response_content,
            model=model,
            log_id=self.log_id,
            usage=TokenUsage(),
            cost_usd=Decimal("0"),
            latency_ms=1,
        )


async def _seed_run(session: AsyncSession) -> StrategyRun:
    run = StrategyRun(
        id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        mode=StrategyRunMode.live.value,
        status=StrategyRunStatus.running.value,
        params={},
    )
    session.add(run)
    await session.commit()
    return run


async def _seed_substrate(session: AsyncSession, *, ticker: str) -> None:
    """Seed enough substrate that gather_context returns non-sparse."""
    entity_id = uuid.uuid4()
    session.add(
        Entity(
            id=entity_id,
            type=EntityType.company.value,
            canonical_name=ticker,
            aliases=[],
            external_ids={},
            attributes={},
            ticker_normalized=ticker.upper(),
            confidence=0.9,
        )
    )
    session.add(
        Hypothesis(
            id=uuid.uuid4(),
            claim_text="seeded claim",
            scope_entity_ids=[str(entity_id)],
            scope_theme_ids=[],
            status=HypothesisStatus.active.value,
            belief=0.5,
            last_activity_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    await session.commit()


def _request(run: StrategyRun) -> JudgeRequest:
    return JudgeRequest(
        run_id=run.id,
        strategy_key="macd_rsi_adx",
        ticker="SPY",
        side="buy",
        qty=Decimal("1"),
        estimated_fill_price=Decimal("100"),
        mode="live",
        bar_ts=datetime(2026, 5, 25, 14, 30, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_evaluate_returns_verdict_id_on_sparse_path(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        run = await _seed_run(session)
    client = _FixedJsonLlmClient(response_content="unused")
    verdict = await evaluate(_request(run), session_maker=session_maker, llm_client=client)
    assert verdict.decision == "veto"
    assert verdict.verdict_id is not None
    async with session_maker() as session:
        row = await session.scalar(
            select(JudgeVerdictRow).where(JudgeVerdictRow.id == verdict.verdict_id)
        )
    assert row is not None
    assert row.decision == "veto"


@pytest.mark.asyncio
async def test_evaluate_returns_verdict_id_on_llm_error_path(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        run = await _seed_run(session)
        await _seed_substrate(session, ticker="SPY")
    client = _FixedJsonLlmClient(
        response_content="", raise_exc=RuntimeError("budget paused")
    )
    verdict = await evaluate(_request(run), session_maker=session_maker, llm_client=client)
    assert verdict.decision == "veto"
    assert verdict.verdict_id is not None
    async with session_maker() as session:
        row = await session.scalar(
            select(JudgeVerdictRow).where(JudgeVerdictRow.id == verdict.verdict_id)
        )
    assert row is not None
    assert "llm_unavailable" in row.reasoning_md


@pytest.mark.asyncio
async def test_evaluate_returns_verdict_id_on_parse_failure_path(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        run = await _seed_run(session)
        await _seed_substrate(session, ticker="SPY")
    client = _FixedJsonLlmClient(response_content="not json")
    verdict = await evaluate(_request(run), session_maker=session_maker, llm_client=client)
    assert verdict.decision == "veto"
    assert verdict.verdict_id is not None
    async with session_maker() as session:
        row = await session.scalar(
            select(JudgeVerdictRow).where(JudgeVerdictRow.id == verdict.verdict_id)
        )
    assert row is not None
    assert "unparseable_response" in row.reasoning_md


@pytest.mark.asyncio
async def test_evaluate_returns_verdict_id_on_happy_path(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        run = await _seed_run(session)
        await _seed_substrate(session, ticker="SPY")
    client = _FixedJsonLlmClient(
        response_content='{"decision":"approve","reasoning_md":"ok"}'
    )
    verdict = await evaluate(_request(run), session_maker=session_maker, llm_client=client)
    assert verdict.decision == "approve"
    assert verdict.verdict_id is not None
    async with session_maker() as session:
        row = await session.scalar(
            select(JudgeVerdictRow).where(JudgeVerdictRow.id == verdict.verdict_id)
        )
    assert row is not None
    assert row.decision == "approve"


@pytest.mark.asyncio
async def test_evaluate_returns_verdict_id_on_invalid_multiplier_path(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import llm_judge_prompt

    async with session_maker() as session:
        run = await _seed_run(session)
        await _seed_substrate(session, ticker="SPY")
    bad = JudgeVerdict(
        decision="approve_reduced",
        reasoning_md="bad multiplier",
        size_multiplier=2.0,
    )
    monkeypatch.setattr(
        llm_judge_prompt, "parse_verdict_response", lambda content: bad
    )
    client = _FixedJsonLlmClient(
        response_content='{"decision":"approve_reduced","reasoning_md":"x","size_multiplier":2.0}'
    )
    verdict = await evaluate(_request(run), session_maker=session_maker, llm_client=client)
    assert verdict.decision == "veto"
    assert verdict.verdict_id is not None
