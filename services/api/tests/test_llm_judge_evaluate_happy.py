from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_graph import Entity, Hypothesis, HypothesisStatus
from app.db.models_judge import JudgeVerdictRow
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.schemas.budget import TokenUsage
from app.services.llm.client import LlmCompletionResult, LlmMessage
from app.services.llm_judge import JudgeRequest, evaluate


@dataclass
class _StubJudgeLlmClient:
    """Records the most recent call; returns a fixed completion result.

    Inserts a minimal LlmCallLog row so that judge_verdicts.llm_call_log_id
    satisfies the FK constraint when persisting the verdict.
    """

    response_content: str
    calls: list[dict[str, Any]] = field(default_factory=list)
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
        self.calls.append({
            "messages": list(messages),
            "model": model,
            "prompt_version": prompt_version,
            "stage": stage,
            "agent_name": agent_name,
        })
        session.add(
            LlmCallLog(
                id=self.log_id,
                model=model,
                prompt_hash="stub",
                input_hash="stub",
                input_tokens=0,
                output_tokens=0,
                cached_input_tokens=0,
                reasoning_tokens=0,
                cost_usd=Decimal("0.00"),
                latency_ms=42,
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
            usage=TokenUsage(),
            cost_usd=Decimal("0.00"),
            latency_ms=42,
            log_id=self.log_id,
        )


async def _seed_substrate(session: AsyncSession) -> uuid.UUID:
    entity_id = uuid.uuid4()
    session.add(
        Entity(
            id=entity_id,
            type="company",
            canonical_name="Nvidia Corp",
            aliases=[],
            external_ids={},
            attributes={},
            ticker_normalized="NVDA",
            confidence=1.0,
        )
    )
    session.add(
        Hypothesis(
            id=uuid.uuid4(),
            claim_text="data-center growth re-accelerates",
            scope_entity_ids=[str(entity_id)],
            scope_theme_ids=[],
            status=HypothesisStatus.active.value,
            belief=0.85,
            last_activity_at=datetime.now(UTC) - timedelta(hours=2),
        )
    )
    await session.flush()
    return entity_id


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run_id = uuid.uuid4()
    session.add(
        StrategyRun(
            id=run_id,
            strategy_key="macd_rsi_adx",
            ticker="NVDA",
            mode=StrategyRunMode.paper.value,
            status=StrategyRunStatus.running.value,
            params={},
        )
    )
    await session.flush()
    return run_id


@pytest.mark.asyncio
async def test_evaluate_happy_path_approves_persists_calls_llm(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    entity_id = await _seed_substrate(db_session)
    run_id = await _seed_run(db_session)
    await db_session.commit()

    llm_stub = _StubJudgeLlmClient(
        response_content=json.dumps({
            "decision": "approve",
            "reasoning_md": "high-belief hypothesis aligns with long entry.",
            "size_multiplier": None,
        })
    )
    request = JudgeRequest(
        run_id=run_id,
        strategy_key="macd_rsi_adx",
        ticker="NVDA",
        side="buy",
        qty=Decimal("10"),
        estimated_fill_price=Decimal("450.00"),
        mode="paper",
        bar_ts=datetime(2026, 5, 24, 14, 30, tzinfo=UTC),
        strategy_meta={"macd_hist": 0.42},
    )

    verdict = await evaluate(
        request,
        session_maker=session_maker,
        llm_client=llm_stub,
    )
    assert verdict.decision == "approve"
    assert verdict.size_multiplier is None
    assert "hypothesis" in verdict.reasoning_md

    rows = (
        await db_session.execute(
            select(JudgeVerdictRow).where(JudgeVerdictRow.run_id == run_id)
        )
    ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.decision == "approve"
    assert row.ticker == "NVDA"
    assert row.strategy_key == "macd_rsi_adx"
    assert row.proposed_qty == Decimal("10")
    assert row.prompt_version == "v1"
    assert row.llm_model is not None
    assert row.llm_call_log_id == llm_stub.log_id
    assert "active_hypotheses" in row.context_payload
    assert row.context_payload["entity"]["id"] == str(entity_id)


@pytest.mark.asyncio
async def test_evaluate_happy_path_approve_reduced_records_multiplier(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_substrate(db_session)
    run_id = await _seed_run(db_session)
    await db_session.commit()

    llm_stub = _StubJudgeLlmClient(
        response_content=json.dumps({
            "decision": "approve_reduced",
            "reasoning_md": "context supports half size only.",
            "size_multiplier": 0.5,
        })
    )
    request = JudgeRequest(
        run_id=run_id,
        strategy_key="macd_rsi_adx",
        ticker="NVDA",
        side="buy",
        qty=Decimal("10"),
        estimated_fill_price=Decimal("450.00"),
        mode="paper",
        bar_ts=datetime(2026, 5, 24, 14, 30, tzinfo=UTC),
    )

    verdict = await evaluate(
        request,
        session_maker=session_maker,
        llm_client=llm_stub,
    )
    assert verdict.decision == "approve_reduced"
    assert verdict.size_multiplier == 0.5

    row = (
        await db_session.execute(
            select(JudgeVerdictRow).where(JudgeVerdictRow.run_id == run_id)
        )
    ).scalar_one()
    assert row.size_multiplier == 0.5


@pytest.mark.asyncio
async def test_evaluate_passes_prompt_version_to_llm_client(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_substrate(db_session)
    run_id = await _seed_run(db_session)
    await db_session.commit()

    llm_stub = _StubJudgeLlmClient(
        response_content=json.dumps({
            "decision": "approve",
            "reasoning_md": "ok",
            "size_multiplier": None,
        })
    )
    await evaluate(
        JudgeRequest(
            run_id=run_id,
            strategy_key="macd_rsi_adx",
            ticker="NVDA",
            side="buy",
            qty=Decimal("1"),
            estimated_fill_price=Decimal("450.00"),
            mode="paper",
            bar_ts=datetime(2026, 5, 24, 14, 30, tzinfo=UTC),
        ),
        session_maker=session_maker,
        llm_client=llm_stub,
    )
    assert len(llm_stub.calls) == 1
    assert llm_stub.calls[0]["prompt_version"] == "v1"
    assert llm_stub.calls[0]["stage"] == "judge"
