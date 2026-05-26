from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_judge import JudgeVerdictRow
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_strategy_runner import (
    StrategyRun,
    StrategyRunMode,
    StrategyRunStatus,
)
from app.schemas.budget import BudgetAction, BudgetDecision, TokenUsage
from app.services.llm.client import (
    BudgetKilledError,
    BudgetPausedError,
    LlmCompletionResult,
    LlmMessage,
)
from app.services.llm_judge import JudgeRequest, evaluate


@dataclass
class _RaisingLlmClient:
    exc: Exception
    calls: int = 0

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
        self.calls += 1
        raise self.exc


@dataclass
class _FixedResponseLlmClient:
    """Returns a fixed response and seeds an LlmCallLog row so the FK on
    judge_verdicts.llm_call_log_id does not fail when the verdict row links it.
    """

    content: str
    calls: int = 0
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
        self.calls += 1
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
                latency_ms=10,
                status=LlmCallStatus.success,
                prompt_version=prompt_version,
                stage=stage,
                agent_name=agent_name,
            )
        )
        await session.commit()
        return LlmCompletionResult(
            content=self.content,
            model=model,
            usage=TokenUsage(),
            cost_usd=Decimal("0.00"),
            latency_ms=10,
            log_id=self.log_id,
        )


async def _seed_non_sparse(session: AsyncSession, ticker: str) -> uuid.UUID:
    """Seed Entity + Hypothesis so gather_context returns non-sparse."""
    from app.db.models_graph import Entity, Hypothesis, HypothesisStatus

    entity_id = uuid.uuid4()
    session.add(
        Entity(
            id=entity_id,
            type="company",
            canonical_name=f"{ticker} Corp",
            aliases=[],
            external_ids={},
            attributes={},
            ticker_normalized=ticker,
            confidence=1.0,
        )
    )
    session.add(
        Hypothesis(
            id=uuid.uuid4(),
            claim_text=f"{ticker} active thesis",
            scope_entity_ids=[str(entity_id)],
            scope_theme_ids=[],
            status=HypothesisStatus.active.value,
            belief=0.5,
            last_activity_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await session.flush()
    return entity_id


async def _seed_run(session: AsyncSession, ticker: str) -> uuid.UUID:
    run_id = uuid.uuid4()
    session.add(
        StrategyRun(
            id=run_id,
            strategy_key="macd_rsi_adx",
            ticker=ticker,
            mode=StrategyRunMode.paper.value,
            status=StrategyRunStatus.running.value,
            params={},
        )
    )
    await session.flush()
    return run_id


def _req(run_id: uuid.UUID, ticker: str) -> JudgeRequest:
    return JudgeRequest(
        run_id=run_id,
        strategy_key="macd_rsi_adx",
        ticker=ticker,
        side="buy",
        qty=Decimal("10"),
        estimated_fill_price=Decimal("100.00"),
        mode="paper",
        bar_ts=datetime(2026, 5, 24, 14, 30, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_evaluate_vetoes_on_sparse_context_without_calling_llm(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    run_id = await _seed_run(db_session, ticker="ZZZZ")
    await db_session.commit()
    llm_stub = _FixedResponseLlmClient(content="should not be called")

    verdict = await evaluate(
        _req(run_id, "ZZZZ"),
        session_maker=session_maker,
        llm_client=llm_stub,
    )
    assert verdict.decision == "veto"
    assert "context_sparse" in verdict.reasoning_md
    assert llm_stub.calls == 0

    row = (
        await db_session.execute(
            select(JudgeVerdictRow).where(JudgeVerdictRow.run_id == run_id)
        )
    ).scalar_one()
    assert row.decision == "veto"
    assert row.llm_model is None
    assert row.llm_call_log_id is None


@pytest.mark.asyncio
async def test_evaluate_vetoes_on_llm_budget_paused(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_non_sparse(db_session, ticker="AAA")
    run_id = await _seed_run(db_session, ticker="AAA")
    await db_session.commit()

    paused_exc = BudgetPausedError(
        BudgetDecision(
            action=BudgetAction.pause,
            reason="run budget exceeded",
            run_cost_usd=Decimal("0.00"),
            daily_cost_usd=Decimal("0.00"),
            threshold_crossed=None,
        )
    )
    llm_stub = _RaisingLlmClient(exc=paused_exc)
    verdict = await evaluate(
        _req(run_id, "AAA"),
        session_maker=session_maker,
        llm_client=llm_stub,
    )
    assert verdict.decision == "veto"
    assert "llm_unavailable" in verdict.reasoning_md
    assert "BudgetPausedError" in verdict.reasoning_md
    assert llm_stub.calls == 1

    row = (
        await db_session.execute(
            select(JudgeVerdictRow).where(JudgeVerdictRow.run_id == run_id)
        )
    ).scalar_one()
    assert row.decision == "veto"
    assert row.llm_call_log_id is None


@pytest.mark.asyncio
async def test_evaluate_vetoes_on_llm_budget_killed(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_non_sparse(db_session, ticker="AAK")
    run_id = await _seed_run(db_session, ticker="AAK")
    await db_session.commit()

    killed_exc = BudgetKilledError(
        BudgetDecision(
            action=BudgetAction.kill,
            reason="daily budget exceeded",
            run_cost_usd=Decimal("0.00"),
            daily_cost_usd=Decimal("0.00"),
            threshold_crossed=None,
        )
    )
    llm_stub = _RaisingLlmClient(exc=killed_exc)
    verdict = await evaluate(
        _req(run_id, "AAK"),
        session_maker=session_maker,
        llm_client=llm_stub,
    )
    assert verdict.decision == "veto"
    assert "llm_unavailable" in verdict.reasoning_md
    assert "BudgetKilledError" in verdict.reasoning_md
    assert llm_stub.calls == 1

    row = (
        await db_session.execute(
            select(JudgeVerdictRow).where(JudgeVerdictRow.run_id == run_id)
        )
    ).scalar_one()
    assert row.decision == "veto"
    assert row.llm_call_log_id is None


@pytest.mark.asyncio
async def test_evaluate_vetoes_on_llm_transport_error(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_non_sparse(db_session, ticker="AAT")
    run_id = await _seed_run(db_session, ticker="AAT")
    await db_session.commit()

    llm_stub = _RaisingLlmClient(exc=RuntimeError("connection refused"))
    verdict = await evaluate(
        _req(run_id, "AAT"),
        session_maker=session_maker,
        llm_client=llm_stub,
    )
    assert verdict.decision == "veto"
    assert "llm_unavailable" in verdict.reasoning_md
    assert "RuntimeError" in verdict.reasoning_md
    assert llm_stub.calls == 1

    row = (
        await db_session.execute(
            select(JudgeVerdictRow).where(JudgeVerdictRow.run_id == run_id)
        )
    ).scalar_one()
    assert row.decision == "veto"
    assert row.llm_call_log_id is None


@pytest.mark.asyncio
async def test_evaluate_vetoes_on_malformed_llm_response(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Parser returns None on non-JSON content — veto, but LLM call IS linked."""
    await _seed_non_sparse(db_session, ticker="BBB")
    run_id = await _seed_run(db_session, ticker="BBB")
    await db_session.commit()

    llm_stub = _FixedResponseLlmClient(content="not json at all")
    verdict = await evaluate(
        _req(run_id, "BBB"),
        session_maker=session_maker,
        llm_client=llm_stub,
    )
    assert verdict.decision == "veto"
    assert "unparseable_response" in verdict.reasoning_md
    assert llm_stub.calls == 1

    row = (
        await db_session.execute(
            select(JudgeVerdictRow).where(JudgeVerdictRow.run_id == run_id)
        )
    ).scalar_one()
    assert row.decision == "veto"
    assert row.llm_call_log_id == llm_stub.log_id


@pytest.mark.asyncio
async def test_evaluate_vetoes_on_approve_reduced_with_invalid_multiplier(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense-in-depth: if the parser is loosened in the future and lets a
    bad multiplier through, evaluate() catches it and vetos.
    """
    from app.services import llm_judge

    await _seed_non_sparse(db_session, ticker="AAI")
    run_id = await _seed_run(db_session, ticker="AAI")
    await db_session.commit()

    def _bad_parser(_content: str) -> llm_judge.JudgeVerdict:
        return llm_judge.JudgeVerdict(
            decision="approve_reduced",
            reasoning_md="hypothetical loose parser output",
            size_multiplier=1.5,
        )

    monkeypatch.setattr(
        "app.services.llm_judge_prompt.parse_verdict_response", _bad_parser
    )
    monkeypatch.setattr(
        "app.services.llm_judge.parse_verdict_response", _bad_parser, raising=False
    )

    llm_stub = _FixedResponseLlmClient(
        content='{"decision": "approve_reduced", "reasoning_md": "x", "size_multiplier": 1.5}'
    )
    verdict = await evaluate(
        _req(run_id, "AAI"),
        session_maker=session_maker,
        llm_client=llm_stub,
    )
    assert verdict.decision == "veto"
    assert "approve_reduced_invalid_multiplier" in verdict.reasoning_md

    row = (
        await db_session.execute(
            select(JudgeVerdictRow).where(JudgeVerdictRow.run_id == run_id)
        )
    ).scalar_one()
    assert row.decision == "veto"
    assert row.llm_call_log_id == llm_stub.log_id
