"""Tests for belief_update.runner: end-to-end pass orchestration."""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    Entity,
    EntityType,
    Evidence,
    EvidenceChunk,
    Hypothesis,
    Relation,
    RelationType,
)
from app.db.models_runs import (
    ResearchRun,
    RunEvent,
    RunEventLevel,
    RunStatus,
    Strategy,
)
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.db.session import session_factory
from app.schemas.budget import (
    BudgetAction,
    BudgetDecision,
    BudgetThresholdName,
    TokenUsage,
)
from app.services.belief_update import (
    BeliefUpdateBudgetHaltError,
    BeliefUpdateOutcome,
    run_belief_update_pass,
)
from app.services.llm import (
    BudgetPausedError,
    LlmClient,
    LlmCompletionResult,
)


def _make_run_id() -> uuid.UUID:
    return uuid.uuid4()


def _completion(content: str, *, model: str = "gpt-4o-mini") -> LlmCompletionResult:
    return LlmCompletionResult(
        content=content,
        model=model,
        usage=TokenUsage(),
        cost_usd=Decimal("0"),
        latency_ms=1,
        log_id=uuid.uuid4(),
    )


def _budget_decision() -> BudgetDecision:
    return BudgetDecision(
        action=BudgetAction.pause,
        reason="per-stage cap hit",
        run_cost_usd=Decimal("0.05"),
        daily_cost_usd=Decimal("0.05"),
        threshold_crossed=BudgetThresholdName.per_stage,
    )


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=_make_run_id(),
        ticker=None,
        trade_date=date(2026, 5, 20),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


async def _seed_sector_entity(session: AsyncSession, name: str) -> uuid.UUID:
    entity = Entity(
        type=EntityType.sector.value,
        canonical_name=name,
        aliases=[],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.flush()
    return entity.id


async def _seed_hypothesis(
    session: AsyncSession, claim: str, scope_ids: list[uuid.UUID]
) -> Hypothesis:
    mirror = Entity(
        type=EntityType.hypothesis.value,
        canonical_name=claim,
        aliases=[claim],
        external_ids={},
        attributes={},
    )
    session.add(mirror)
    await session.flush()
    hypothesis = Hypothesis(
        claim_text=claim,
        scope_entity_ids=[str(s) for s in scope_ids],
        scope_theme_ids=[],
        status="active",
        belief=0.5,
        belief_history=[],
        entity_id=mirror.id,
    )
    session.add(hypothesis)
    await session.flush()
    return hypothesis


async def _seed_evidence(
    session: AsyncSession, chunk_count: int
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    evidence = Evidence(
        source="tiingo_news",
        document_id=f"doc|{uuid.uuid4()}",
        raw_url=None,
        content_hash=uuid.uuid4().hex,
        structured={},
    )
    session.add(evidence)
    await session.flush()
    ids: list[uuid.UUID] = []
    for idx in range(chunk_count):
        chunk = EvidenceChunk(
            evidence_id=evidence.id,
            chunk_index=idx,
            text=f"chunk text {idx}",
            start_offset=None,
            end_offset=None,
            attributes={"source": "tiingo_news"},
            content_hash=uuid.uuid4().hex,
        )
        session.add(chunk)
        await session.flush()
        ids.append(chunk.id)
    return evidence.id, ids


async def _seed_sector_brief(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    sector_entity_id: uuid.UUID,
    evidence_id: uuid.UUID,
) -> None:
    session.add(
        SectorBriefRow(
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            direction="overweight",
            payload={"evidence_ids": [str(evidence_id)]},
            verifier_status="verified",
            regeneration_count=0,
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
            wall_clock_ms=0,
        )
    )
    await session.commit()


class _StubLlmClient(LlmClient):
    """LlmClient stub that returns canned responses keyed on call order."""

    def __init__(self, responses: list[LlmCompletionResult]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> LlmCompletionResult:  # type: ignore[override]
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("no canned response left")
        return self._responses.pop(0)


def _orchestrator() -> MagicMock:
    mock = MagicMock()
    mock.pause = AsyncMock()
    mock.fail = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_run_returns_zero_outcome_when_no_open_hypotheses(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        await _seed_run(session)
    orchestrator = _orchestrator()
    llm = _StubLlmClient([])
    outcome = await run_belief_update_pass(
        session_factory=session_factory,
        run_id=uuid.uuid4(),
        llm_client=llm,
        orchestrator=orchestrator,
    )
    assert outcome == BeliefUpdateOutcome(
        hypothesis_count=0,
        chunks_judged=0,
        relations_written=0,
        recomputed_hypothesis_ids=[],
    )
    assert llm.calls == []


@pytest.mark.asyncio
async def test_run_happy_path_writes_three_relations_and_recomputes(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_id = await _seed_sector_entity(session, "Information Technology")
        evidence_id, chunk_ids = await _seed_evidence(session, chunk_count=3)
        await _seed_sector_brief(
            session,
            run_id=run_id,
            sector_entity_id=sector_id,
            evidence_id=evidence_id,
        )
        hypothesis = await _seed_hypothesis(
            session, "Tech earnings beat", [sector_id]
        )
        await session.commit()
        hypothesis_id = hypothesis.id
        hypothesis_entity_id = hypothesis.entity_id

    llm_content = json.dumps(
        {
            "verdicts": [
                {
                    "chunk_id": str(chunk_ids[0]),
                    "verdict": "supports",
                    "confidence": 0.9,
                    "quote": "chunk text 0",
                },
                {
                    "chunk_id": str(chunk_ids[1]),
                    "verdict": "contradicts",
                    "confidence": 0.6,
                    "quote": "chunk text 1",
                },
                {
                    "chunk_id": str(chunk_ids[2]),
                    "verdict": "unrelated",
                    "confidence": 0.3,
                    "quote": None,
                },
            ]
        }
    )
    llm = _StubLlmClient([_completion(llm_content)])
    orchestrator = _orchestrator()

    outcome = await run_belief_update_pass(
        session_factory=session_factory,
        run_id=run_id,
        llm_client=llm,
        orchestrator=orchestrator,
    )

    assert outcome.hypothesis_count == 1
    assert outcome.chunks_judged == 3
    assert outcome.relations_written == 2  # unrelated filtered
    assert hypothesis_id in outcome.recomputed_hypothesis_ids

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Relation).where(Relation.to_id == hypothesis_entity_id)
            )
        ).scalars().all()
        assert len(rows) == 2
        by_type = {row.type: row for row in rows}
        supports = by_type[RelationType.supports_hypothesis.value]
        assert supports.sign == 1.0
        assert supports.is_explicit is True
        assert supports.relevance == pytest.approx(0.9)
        assert supports.prompt_version == "belief-update-v1"
        assert supports.source_id == evidence_id
        contradicts = by_type[RelationType.contradicts_hypothesis.value]
        assert contradicts.sign == -1.0
        assert contradicts.is_explicit is False  # 0.6 < 0.7 threshold
        hypothesis_after = (
            await session.execute(
                select(Hypothesis).where(Hypothesis.id == hypothesis_id)
            )
        ).scalar_one()
        assert hypothesis_after.belief != pytest.approx(0.5)


@pytest.mark.asyncio
async def test_re_running_writes_zero_new_relations_when_all_chunks_already_judged(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_id = await _seed_sector_entity(session, "Energy")
        evidence_id, chunk_ids = await _seed_evidence(session, chunk_count=2)
        await _seed_sector_brief(
            session,
            run_id=run_id,
            sector_entity_id=sector_id,
            evidence_id=evidence_id,
        )
        await _seed_hypothesis(session, "Energy weakens", [sector_id])
        await session.commit()

    first_content = json.dumps(
        {
            "verdicts": [
                {
                    "chunk_id": str(chunk_ids[0]),
                    "verdict": "supports",
                    "confidence": 0.8,
                    "quote": "chunk text 0",
                },
                {
                    "chunk_id": str(chunk_ids[1]),
                    "verdict": "supports",
                    "confidence": 0.8,
                    "quote": "chunk text 1",
                },
            ]
        }
    )
    llm = _StubLlmClient([_completion(first_content)])
    orchestrator = _orchestrator()
    first = await run_belief_update_pass(
        session_factory=session_factory,
        run_id=run_id,
        llm_client=llm,
        orchestrator=orchestrator,
    )
    assert first.relations_written == 2

    second_llm = _StubLlmClient([])
    second = await run_belief_update_pass(
        session_factory=session_factory,
        run_id=run_id,
        llm_client=second_llm,
        orchestrator=orchestrator,
    )
    assert second.hypothesis_count == 1
    assert second.chunks_judged == 0
    assert second.relations_written == 0
    assert second_llm.calls == []


@pytest.mark.asyncio
async def test_per_hypothesis_llm_error_is_warn_event_other_hypotheses_continue(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_id = await _seed_sector_entity(session, "Financials")
        evidence_id, chunk_ids = await _seed_evidence(session, chunk_count=1)
        await _seed_sector_brief(
            session,
            run_id=run_id,
            sector_entity_id=sector_id,
            evidence_id=evidence_id,
        )
        bad = await _seed_hypothesis(session, "claim A", [sector_id])
        good = await _seed_hypothesis(session, "claim B", [sector_id])
        await session.commit()
        bad_id = bad.id
        good_id = good.id

    good_content = json.dumps(
        {
            "verdicts": [
                {
                    "chunk_id": str(chunk_ids[0]),
                    "verdict": "supports",
                    "confidence": 0.85,
                    "quote": "chunk text 0",
                }
            ]
        }
    )

    llm = _StubLlmClient(
        [_completion("this is not json"), _completion(good_content)]
    )
    orchestrator = _orchestrator()
    outcome = await run_belief_update_pass(
        session_factory=session_factory,
        run_id=run_id,
        llm_client=llm,
        orchestrator=orchestrator,
    )

    assert outcome.hypothesis_count == 2
    assert outcome.relations_written == 1
    assert good_id in outcome.recomputed_hypothesis_ids
    assert bad_id not in outcome.recomputed_hypothesis_ids

    async with session_factory() as session:
        warns = (
            await session.execute(
                select(RunEvent).where(
                    RunEvent.run_id == run_id,
                    RunEvent.level == RunEventLevel.warn,
                )
            )
        ).scalars().all()
        warn_hypothesis_ids = {
            event.data.get("hypothesis_id")
            for event in warns
            if isinstance(event.data, dict)
        }
        assert str(bad_id) in warn_hypothesis_ids


@pytest.mark.asyncio
async def test_budget_pause_routes_through_orchestrator_and_raises_halt(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_id = await _seed_sector_entity(session, "Health Care")
        evidence_id, _chunk_ids = await _seed_evidence(session, chunk_count=1)
        await _seed_sector_brief(
            session,
            run_id=run_id,
            sector_entity_id=sector_id,
            evidence_id=evidence_id,
        )
        await _seed_hypothesis(session, "HC margin holds", [sector_id])
        await session.commit()

    class _PausingLlm(LlmClient):
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, **kwargs: Any) -> LlmCompletionResult:  # type: ignore[override]
            self.calls += 1
            raise BudgetPausedError(_budget_decision())

    llm = _PausingLlm()
    orchestrator = _orchestrator()
    with pytest.raises(BeliefUpdateBudgetHaltError):
        await run_belief_update_pass(
            session_factory=session_factory,
            run_id=run_id,
            llm_client=llm,
            orchestrator=orchestrator,
        )
    orchestrator.pause.assert_awaited_once()
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_relation_from_id_is_first_scope_entity_when_present(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_id = await _seed_sector_entity(session, "Materials")
        evidence_id, chunk_ids = await _seed_evidence(session, chunk_count=1)
        await _seed_sector_brief(
            session,
            run_id=run_id,
            sector_entity_id=sector_id,
            evidence_id=evidence_id,
        )
        hypothesis = await _seed_hypothesis(
            session, "Steel demand softens", [sector_id]
        )
        await session.commit()
        hypothesis_entity_id = hypothesis.entity_id

    content = json.dumps(
        {
            "verdicts": [
                {
                    "chunk_id": str(chunk_ids[0]),
                    "verdict": "supports",
                    "confidence": 0.8,
                    "quote": "chunk text 0",
                }
            ]
        }
    )
    llm = _StubLlmClient([_completion(content)])
    orchestrator = _orchestrator()
    await run_belief_update_pass(
        session_factory=session_factory,
        run_id=run_id,
        llm_client=llm,
        orchestrator=orchestrator,
    )

    async with session_factory() as session:
        relation = (
            await session.execute(
                select(Relation).where(Relation.to_id == hypothesis_entity_id)
            )
        ).scalar_one()
        assert relation.from_id == sector_id
