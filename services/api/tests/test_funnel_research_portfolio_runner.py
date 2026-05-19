import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis as CompanyThesisRow
from app.db.models_graph import (
    Entity,
    EntityType,
    Evidence,
    EvidenceChunk,
)
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_portfolio import PortfolioBrief as PortfolioBriefRow
from app.db.models_runs import ResearchRun, RunEvent, RunStatus, Strategy
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.db.session import session_factory
from app.schemas.budget import BudgetAction, BudgetDecision, TokenUsage
from app.schemas.company_thesis import (
    CompanyCatalyst,
    CompanyRisk,
    CompanyThesis,
)
from app.schemas.macro_brief import (
    CitedClaim,
    MacroBrief,
    SectorCallDirection,
    Theme,
    VerifierStatus,
    WatchItem,
)
from app.schemas.sector_brief import (
    JudgePublic,
    JudgeStatus,
    SectorBrief,
)
from app.services.llm.client import BudgetPausedError, LlmCompletionResult
from app.services.strategies.funnel_research._errors import FunnelResearchError
from app.services.strategies.funnel_research.portfolio.runner import (
    run_portfolio_brief,
)


async def _persist_log(session: AsyncSession, run_id: uuid.UUID) -> uuid.UUID:
    log = LlmCallLog(
        run_id=run_id,
        model="gpt-5-mini",
        prompt_hash="0" * 64,
        input_hash="0" * 64,
        input_tokens=10,
        output_tokens=5,
        cached_input_tokens=0,
        reasoning_tokens=0,
        cost_usd=Decimal("0.001"),
        latency_ms=10,
        status=LlmCallStatus.success,
    )
    session.add(log)
    await session.flush()
    return log.id


def _completion(content: str, log_id: uuid.UUID) -> LlmCompletionResult:
    return LlmCompletionResult(
        content=content,
        model="gpt-5-mini",
        usage=TokenUsage(input_tokens=10, output_tokens=5),
        cost_usd=Decimal("0.001"),
        latency_ms=10,
        log_id=log_id,
    )


class _StaticLlm:
    def __init__(self, *, content: str) -> None:
        self._content = content
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> LlmCompletionResult:
        self.calls.append(kwargs)
        session = kwargs["session"]
        run_id = kwargs.get("run_id")
        assert isinstance(session, AsyncSession)
        assert isinstance(run_id, uuid.UUID)
        log_id = await _persist_log(session, run_id)
        return _completion(self._content, log_id=log_id)


class _ErrorLlm:
    async def complete(self, **_: Any) -> LlmCompletionResult:
        raise RuntimeError("llm offline")


class _PausingLlm:
    async def complete(self, **_: Any) -> LlmCompletionResult:
        raise BudgetPausedError(
            BudgetDecision(
                action=BudgetAction.pause,
                reason="soft cap",
                run_cost_usd=Decimal("5"),
                daily_cost_usd=Decimal("5"),
                threshold_crossed=None,
            )
        )


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.commit()
    return run.id


async def _seed_entity(
    session: AsyncSession,
    *,
    entity_type: EntityType,
    name: str,
) -> uuid.UUID:
    entity = Entity(
        type=entity_type.value,
        canonical_name=name,
        aliases=[],
        external_ids={},
        attributes={},
    )
    session.add(entity)
    await session.commit()
    return entity.id


async def _seed_sector_brief_row(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    sector_entity_id: uuid.UUID,
    sector_name: str,
    direction: SectorCallDirection,
    confidence: float,
    judge_status: JudgeStatus,
    cited_claims: list[CitedClaim] | None = None,
) -> None:
    brief = SectorBrief(
        sector_entity_id=sector_entity_id,
        sector_name=sector_name,
        direction=direction,
        themes=[],
        companies=[],
        watch_items=[],
        cited_claims=cited_claims or [],
        confidence=confidence,
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    row = SectorBriefRow(
        run_id=run_id,
        sector_entity_id=sector_entity_id,
        direction=direction.value,
        payload=brief.model_dump(mode="json"),
        verifier_status=VerifierStatus.verified.value,
        regeneration_count=0,
        judge_status=judge_status.value,
        judge_reasons=None,
        judge_call_id=None,
        wall_clock_ms=100,
    )
    session.add(row)
    await session.commit()


async def _seed_company_thesis_row(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    company_entity_id: uuid.UUID,
    sector_entity_id: uuid.UUID,
    sector_name: str,
    company_name: str,
    direction: SectorCallDirection,
    conviction: float,
    judge_status: JudgeStatus,
) -> None:
    thesis = CompanyThesis(
        company_entity_id=company_entity_id,
        company_name=company_name,
        sector_entity_id=sector_entity_id,
        sector_name=sector_name,
        ticker=None,
        direction=direction,
        conviction=conviction,
        bull_case="Demand is strong.",
        bear_case="Risks remain.",
        catalysts=[
            CompanyCatalyst(
                name="earnings",
                expected_timing=None,
                evidence_ids=[uuid.uuid4()],
            )
        ],
        risks=[
            CompanyRisk(
                name="competition",
                severity=0.3,
                evidence_ids=[uuid.uuid4()],
            )
        ],
        cited_claims=[],
        confidence=conviction,
        evidence_ids=[uuid.uuid4()],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    row = CompanyThesisRow(
        run_id=run_id,
        company_entity_id=company_entity_id,
        sector_entity_id=sector_entity_id,
        ticker=None,
        direction=direction.value,
        payload=thesis.model_dump(mode="json"),
        verifier_status=VerifierStatus.verified.value,
        regeneration_count=0,
        judge_status=judge_status.value,
        judge_reasons=None,
        judge_call_id=None,
        wall_clock_ms=200,
    )
    session.add(row)
    await session.commit()


async def _seed_evidence_chunk(
    session: AsyncSession,
    *,
    chunk_id: uuid.UUID,
    text: str = "evidence text",
) -> None:
    evidence = Evidence(
        source="tiingo_news",
        document_id=f"doc-{uuid.uuid4().hex}",
        raw_url=None,
        content_hash=f"{uuid.uuid4().hex}{uuid.uuid4().hex}",
        structured={},
    )
    session.add(evidence)
    await session.flush()
    chunk = EvidenceChunk(
        id=chunk_id,
        evidence_id=evidence.id,
        chunk_index=0,
        text=text,
        start_offset=0,
        end_offset=len(text),
        attributes={"source": "tiingo_news"},
        content_hash="0" * 64,
    )
    session.add(chunk)
    await session.commit()


def _macro_brief(cited_claims: list[CitedClaim] | None = None) -> MacroBrief:
    return MacroBrief(
        themes=[Theme(name="ai capex", evidence_ids=[uuid.uuid4()], confidence=0.7)],
        sector_calls=[],
        watch_items=[
            WatchItem(name="rate path", reason="watch", evidence_ids=[uuid.uuid4()])
        ],
        cited_claims=cited_claims or [],
        proposed_hypotheses=[],
        confidence=0.65,
        evidence_ids=[uuid.uuid4()],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


@pytest.mark.asyncio
async def test_run_portfolio_brief_empty_upstream(initialized_schema: None) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    llm = _StaticLlm(content=json.dumps({"status": "passed", "reasons": []}))
    orchestrator = AsyncMock()

    outcome = await run_portfolio_brief(
        session_factory=session_factory,
        run_id=run_id,
        macro_brief=_macro_brief(),
        macro_judge=JudgePublic(status=JudgeStatus.passed, reasons=[], call_id=None),
        llm_client=llm,
        orchestrator=orchestrator,
    )

    assert outcome.persisted is True
    assert outcome.judge_status is JudgeStatus.passed
    assert outcome.wall_clock_ms >= 0
    assert len(llm.calls) == 1

    async with session_factory() as session:
        row = (
            await session.execute(
                select(PortfolioBriefRow).where(PortfolioBriefRow.run_id == run_id)
            )
        ).scalar_one()
    assert row.judge_status == "passed"
    assert row.verifier_status == "verified"
    payload = row.payload
    assert isinstance(payload, dict)
    assert payload["sectors"] == []
    assert payload["companies"] == []


@pytest.mark.asyncio
async def test_run_portfolio_brief_aggregates_persisted_rows(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_entity_id = await _seed_entity(
            session, entity_type=EntityType.sector, name="Information Technology"
        )
        company_entity_id = await _seed_entity(
            session, entity_type=EntityType.company, name="Apple Inc."
        )
        await _seed_sector_brief_row(
            session,
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            sector_name="Information Technology",
            direction=SectorCallDirection.overweight,
            confidence=0.8,
            judge_status=JudgeStatus.passed,
        )
        await _seed_company_thesis_row(
            session,
            run_id=run_id,
            company_entity_id=company_entity_id,
            sector_entity_id=sector_entity_id,
            sector_name="Information Technology",
            company_name="Apple Inc.",
            direction=SectorCallDirection.overweight,
            conviction=0.85,
            judge_status=JudgeStatus.passed,
        )

    llm = _StaticLlm(content=json.dumps({"status": "passed", "reasons": []}))
    orchestrator = AsyncMock()

    outcome = await run_portfolio_brief(
        session_factory=session_factory,
        run_id=run_id,
        macro_brief=_macro_brief(),
        macro_judge=JudgePublic(status=JudgeStatus.passed, reasons=[], call_id=None),
        llm_client=llm,
        orchestrator=orchestrator,
    )

    assert outcome.persisted is True
    assert outcome.judge_status is JudgeStatus.passed

    async with session_factory() as session:
        row = (
            await session.execute(
                select(PortfolioBriefRow).where(PortfolioBriefRow.run_id == run_id)
            )
        ).scalar_one()
    payload = row.payload
    assert isinstance(payload, dict)
    assert len(payload["sectors"]) == 1
    assert payload["sectors"][0]["sector_name"] == "Information Technology"
    assert payload["sectors"][0]["rank"] == 1
    assert len(payload["companies"]) == 1
    assert payload["companies"][0]["company_name"] == "Apple Inc."
    assert payload["coverage"]["sectors_judge_passed"] == 1
    assert payload["coverage"]["companies_judge_passed"] == 1


@pytest.mark.asyncio
async def test_run_portfolio_brief_judge_llm_failure_marks_not_run(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    orchestrator = AsyncMock()

    outcome = await run_portfolio_brief(
        session_factory=session_factory,
        run_id=run_id,
        macro_brief=_macro_brief(),
        macro_judge=JudgePublic(status=JudgeStatus.passed, reasons=[], call_id=None),
        llm_client=_ErrorLlm(),
        orchestrator=orchestrator,
    )

    assert outcome.persisted is True
    assert outcome.judge_status is JudgeStatus.not_run

    async with session_factory() as session:
        row = (
            await session.execute(
                select(PortfolioBriefRow).where(PortfolioBriefRow.run_id == run_id)
            )
        ).scalar_one()
        events = (
            await session.execute(
                select(RunEvent).where(RunEvent.run_id == run_id)
            )
        ).scalars().all()
    assert row.judge_status == "not_run"
    assert any(
        isinstance(event.data, dict)
        and event.data.get("event") == "judge_failure"
        for event in events
    )


@pytest.mark.asyncio
async def test_run_portfolio_brief_judge_flagged_persists_reasons(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    llm = _StaticLlm(
        content=json.dumps(
            {"status": "flagged", "reasons": ["picks contradict macro"]}
        )
    )
    orchestrator = AsyncMock()

    outcome = await run_portfolio_brief(
        session_factory=session_factory,
        run_id=run_id,
        macro_brief=_macro_brief(),
        macro_judge=JudgePublic(status=JudgeStatus.passed, reasons=[], call_id=None),
        llm_client=llm,
        orchestrator=orchestrator,
    )

    assert outcome.judge_status is JudgeStatus.flagged

    async with session_factory() as session:
        row = (
            await session.execute(
                select(PortfolioBriefRow).where(PortfolioBriefRow.run_id == run_id)
            )
        ).scalar_one()
    assert row.judge_status == "flagged"
    assert row.judge_reasons == ["picks contradict macro"]


@pytest.mark.asyncio
async def test_run_portfolio_brief_budget_pause_routes_through_orchestrator(
    initialized_schema: None,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)

    orchestrator = AsyncMock()

    with pytest.raises(FunnelResearchError):
        await run_portfolio_brief(
            session_factory=session_factory,
            run_id=run_id,
            macro_brief=_macro_brief(),
            macro_judge=JudgePublic(
                status=JudgeStatus.passed, reasons=[], call_id=None
            ),
            llm_client=_PausingLlm(),
            orchestrator=orchestrator,
        )

    orchestrator.pause.assert_awaited_once()
    orchestrator.fail.assert_not_awaited()

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(PortfolioBriefRow).where(PortfolioBriefRow.run_id == run_id)
            )
        ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_run_portfolio_brief_loads_judge_chunks_when_cited(
    initialized_schema: None,
) -> None:
    chunk_id = uuid.uuid4()
    async with session_factory() as session:
        run_id = await _seed_run(session)
        sector_entity_id = await _seed_entity(
            session, entity_type=EntityType.sector, name="Energy"
        )
        await _seed_evidence_chunk(
            session, chunk_id=chunk_id, text="distinctive marker phrase"
        )
        await _seed_sector_brief_row(
            session,
            run_id=run_id,
            sector_entity_id=sector_entity_id,
            sector_name="Energy",
            direction=SectorCallDirection.overweight,
            confidence=0.7,
            judge_status=JudgeStatus.passed,
            cited_claims=[
                CitedClaim(
                    claim_text="capex acceleration",
                    exact_quote="Capex grew 30%",
                    chunk_id=chunk_id,
                    source="tiingo_news",
                )
            ],
        )

    llm = _StaticLlm(content=json.dumps({"status": "passed", "reasons": []}))
    orchestrator = AsyncMock()

    await run_portfolio_brief(
        session_factory=session_factory,
        run_id=run_id,
        macro_brief=_macro_brief(),
        macro_judge=JudgePublic(status=JudgeStatus.passed, reasons=[], call_id=None),
        llm_client=llm,
        orchestrator=orchestrator,
    )

    assert len(llm.calls) == 1
    rendered = "".join(m.content for m in llm.calls[0]["messages"])
    assert "distinctive marker phrase" in rendered
