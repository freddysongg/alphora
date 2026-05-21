import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.db.models_graph import Hypothesis
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_portfolio import PortfolioBrief as PortfolioBriefRow
from app.db.models_runs import ResearchRun, RunEvent, RunStatus, Strategy
from app.db.session import session_factory
from app.schemas.budget import TokenUsage
from app.services.llm.client import LlmCompletionResult


def _brief_json(chunk_id: uuid.UUID, sector_eid: uuid.UUID) -> str:
    return json.dumps(
        {
            "themes": [
                {"name": "rates", "evidence_ids": [], "confidence": 0.5},
            ],
            "sector_calls": [
                {
                    "sector_entity_id": str(sector_eid),
                    "sector_name": "Energy",
                    "direction": "overweight",
                    "conviction": 0.6,
                    "evidence_ids": [],
                }
            ],
            "watch_items": [
                {"name": "w", "reason": "r", "evidence_ids": []},
            ],
            "cited_claims": [
                {
                    "claim_text": "c",
                    "exact_quote": "FRED series CPIAUCSL",
                    "chunk_id": str(chunk_id),
                    "source": "fred",
                }
            ],
            "proposed_hypotheses": [
                {
                    "claim_text": "Energy outperforms",
                    "scope_entity_ids": [str(sector_eid)],
                    "evidence_ids": [],
                }
            ],
            "confidence": 0.7,
            "evidence_ids": [],
            "verifier_status": "verified",
            "regeneration_count": 0,
        }
    )


@pytest.mark.asyncio
async def test_run_macro_brief_end_to_end_success(initialized_schema: None) -> None:
    from app.services.run_orchestrator import RunOrchestrator
    from app.services.source_clients.fred import FredObservation, FredSeriesObservations
    from app.services.strategies.funnel_research._ingest import SourceFetcher
    from app.services.strategies.funnel_research.core import run_macro_brief
    from app.trading_agents.adapter import TradingAgentsAdapter

    run_id = uuid.uuid4()
    async with session_factory() as setup:
        run = ResearchRun(
            id=run_id,
            ticker=None,
            trade_date=date(2026, 5, 18),
            strategy=Strategy.funnel_research.value,
            status=RunStatus.queued,
            config={},
            scope_payload={"kind": "macro", "universe": "us_equities"},
        )
        setup.add(run)
        await setup.commit()

    fred_payload = FredSeriesObservations(
        series_id="CPIAUCSL",
        observation_start=date(2025, 1, 1),
        observation_end=date(2026, 1, 1),
        count=1,
        observations=[
            FredObservation(
                date=date(2026, 1, 1),
                value=Decimal("310.0"),
                realtime_start=date(2026, 1, 15),
                realtime_end=date(2026, 12, 31),
            )
        ],
    )

    fetcher = SourceFetcher(
        fred=lambda client, series_id: (fred_payload, "a" * 64),
        polymarket=lambda client, limit: ([], "b" * 64),
        kalshi=lambda client, limit: ([], "c" * 64),
        congress=lambda client, limit: ([], "d" * 64),
        tiingo_news=lambda client, limit: ([], "e" * 64),
    )

    runtime_state: dict[str, uuid.UUID] = {}

    class StubLlm:
        async def complete(self, **kwargs: Any) -> LlmCompletionResult:
            messages = kwargs.get("messages", [])
            is_judge = any(
                "Brief kind:" in getattr(m, "content", "") for m in messages
            )
            if is_judge:
                content = json.dumps({"status": "passed", "reasons": []})
            else:
                chunk_id = runtime_state["__chunk_id__"]
                sector_eid = runtime_state["Energy"]
                content = _brief_json(chunk_id, sector_eid)

            session = kwargs["session"]
            log = LlmCallLog(
                id=uuid.uuid4(),
                run_id=kwargs.get("run_id"),
                model=kwargs.get("model", "gpt-5-mini"),
                prompt_hash="0" * 64,
                input_hash="0" * 64,
                input_tokens=10,
                output_tokens=10,
                cached_input_tokens=0,
                reasoning_tokens=0,
                cost_usd=Decimal("0.001"),
                latency_ms=10,
                status=LlmCallStatus.success,
                evidence_ids=None,
            )
            session.add(log)
            await session.flush()

            return LlmCompletionResult(
                content=content,
                model=kwargs.get("model", "gpt-5-mini"),
                usage=TokenUsage(
                    input_tokens=10,
                    output_tokens=10,
                    cached_input_tokens=0,
                    reasoning_tokens=0,
                ),
                cost_usd=Decimal("0.001"),
                latency_ms=10,
                log_id=log.id,
            )

    orchestrator = RunOrchestrator(
        session_factory=session_factory, adapter=TradingAgentsAdapter()
    )

    async with httpx.AsyncClient() as http_client:
        await run_macro_brief(
            session_factory=session_factory,
            run_id=run_id,
            llm_client=StubLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
            fetcher=fetcher,
            sector_constituents={},
            chunk_id_capture=runtime_state,
        )

    async with session_factory() as session:
        loaded_run = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
        ).scalar_one()
        assert loaded_run.status == RunStatus.succeeded
        brief = (
            await session.execute(
                select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
            )
        ).scalar_one()
        assert brief.verifier_status == "verified"
        assert brief.judge_status == "passed"
        assert brief.judge_call_id is not None
        assert loaded_run.started_at is not None
        hypotheses = (
            (
                await session.execute(
                    select(Hypothesis).where(Hypothesis.proposed_by_run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(hypotheses) == 1

        stage_events = (
            (
                await session.execute(
                    select(RunEvent).where(RunEvent.run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
        stage_names = [
            (event.data or {}).get("stage_name")
            for event in stage_events
            if (event.data or {}).get("event") == "stage"
        ]
        assert "ingest" in stage_names
        assert "portfolio_brief" in stage_names
        assert "consolidate" in stage_names
        assert "succeeded" in stage_names

        portfolio_row = (
            await session.execute(
                select(PortfolioBriefRow).where(PortfolioBriefRow.run_id == run_id)
            )
        ).scalar_one()
        assert portfolio_row.judge_status == "passed"
        assert portfolio_row.verifier_status == "verified"


@pytest.mark.asyncio
async def test_run_macro_brief_invalid_scope_fails_run(initialized_schema: None) -> None:
    from app.services.run_orchestrator import RunOrchestrator
    from app.services.strategies.funnel_research._ingest import SourceFetcher
    from app.services.strategies.funnel_research.core import run_macro_brief
    from app.trading_agents.adapter import TradingAgentsAdapter

    run_id = uuid.uuid4()
    async with session_factory() as setup:
        run = ResearchRun(
            id=run_id,
            ticker=None,
            trade_date=date(2026, 5, 18),
            strategy=Strategy.funnel_research.value,
            status=RunStatus.queued,
            config={},
            scope_payload={"kind": "wrong"},
        )
        setup.add(run)
        await setup.commit()

    fetcher = SourceFetcher(
        fred=lambda client, series_id: ([], ""),
        polymarket=lambda client, limit: ([], ""),
        kalshi=lambda client, limit: ([], ""),
        congress=lambda client, limit: ([], ""),
        tiingo_news=lambda client, limit: ([], ""),
    )

    class StubLlm:
        async def complete(self, **kwargs: Any) -> LlmCompletionResult:
            raise AssertionError("should not reach llm")

    orchestrator = RunOrchestrator(
        session_factory=session_factory, adapter=TradingAgentsAdapter()
    )

    async with httpx.AsyncClient() as http_client:
        await run_macro_brief(
            session_factory=session_factory,
            run_id=run_id,
            llm_client=StubLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
            fetcher=fetcher,
        )

    async with session_factory() as session:
        loaded = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
        ).scalar_one()
        assert loaded.status == RunStatus.failed
        assert loaded.error_message and "scope" in loaded.error_message.lower()


@pytest.mark.asyncio
async def test_run_macro_brief_resume_with_all_stages_persisted_skips_all_llm(
    initialized_schema: None,
) -> None:
    """A resumed funnel run with macro, sector, company, and portfolio rows
    already persisted must invoke zero LLM calls and persist no duplicate rows.
    """
    from app.db.models_company import CompanyThesis as CompanyThesisRow
    from app.db.models_graph import Entity, EntityType
    from app.db.models_portfolio import PortfolioBrief as PortfolioBriefRow
    from app.db.models_sector import SectorBrief as SectorBriefRow
    from app.schemas.company_thesis import (
        CompanyCatalyst,
        CompanyRisk,
        CompanyThesis,
    )
    from app.schemas.macro_brief import SectorCallDirection, VerifierStatus
    from app.schemas.portfolio_brief import (
        PortfolioBrief,
        PortfolioCoverage,
        PortfolioMacroSummary,
    )
    from app.schemas.sector_brief import JudgeStatus, SectorBrief
    from app.services.run_orchestrator import RunOrchestrator
    from app.services.source_clients.fred import (
        FredObservation,
        FredSeriesObservations,
    )
    from app.services.strategies.funnel_research._ingest import SourceFetcher
    from app.services.strategies.funnel_research.core import run_macro_brief
    from app.trading_agents.adapter import TradingAgentsAdapter

    run_id = uuid.uuid4()
    sector_entity_id = uuid.uuid4()
    company_entity_id = uuid.uuid4()

    async with session_factory() as setup:
        run = ResearchRun(
            id=run_id,
            ticker=None,
            trade_date=date(2026, 5, 18),
            strategy=Strategy.funnel_research.value,
            status=RunStatus.queued,
            config={},
            scope_payload={"kind": "macro", "universe": "us_equities"},
        )
        setup.add(run)
        await setup.flush()

        setup.add_all(
            [
                Entity(
                    id=sector_entity_id,
                    type=EntityType.sector.value,
                    canonical_name="Information Technology",
                    aliases=[],
                    external_ids={},
                    attributes={},
                ),
                Entity(
                    id=company_entity_id,
                    type=EntityType.company.value,
                    canonical_name="Apple Inc.",
                    aliases=[],
                    external_ids={},
                    attributes={},
                ),
            ]
        )
        await setup.flush()

        setup.add(
            MacroBriefRow(
                run_id=run_id,
                themes=[],
                sector_calls=[],
                watch_items=[],
                cited_claims=[],
                proposed_hypotheses=[],
                confidence=0.5,
                verifier_status="verified",
                regeneration_count=0,
                evidence_ids=[],
                judge_status="passed",
                judge_reasons=None,
                judge_call_id=None,
            )
        )

        sector_brief = SectorBrief(
            sector_entity_id=sector_entity_id,
            sector_name="Information Technology",
            direction=SectorCallDirection.overweight,
            themes=[],
            companies=[],
            watch_items=[],
            cited_claims=[],
            confidence=0.8,
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
        )
        setup.add(
            SectorBriefRow(
                run_id=run_id,
                sector_entity_id=sector_entity_id,
                direction="overweight",
                payload=sector_brief.model_dump(mode="json"),
                verifier_status="verified",
                regeneration_count=0,
                judge_status="passed",
                judge_reasons=None,
                judge_call_id=None,
                wall_clock_ms=100,
            )
        )

        company_thesis = CompanyThesis(
            company_entity_id=company_entity_id,
            company_name="Apple Inc.",
            sector_entity_id=sector_entity_id,
            sector_name="Information Technology",
            ticker="AAPL",
            direction=SectorCallDirection.overweight,
            conviction=0.85,
            bull_case="Strong fundamentals.",
            bear_case="Demand risks.",
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
            confidence=0.85,
            evidence_ids=[uuid.uuid4()],
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
        )
        setup.add(
            CompanyThesisRow(
                run_id=run_id,
                company_entity_id=company_entity_id,
                sector_entity_id=sector_entity_id,
                ticker="AAPL",
                direction="overweight",
                payload=company_thesis.model_dump(mode="json"),
                verifier_status="verified",
                regeneration_count=0,
                judge_status="passed",
                judge_reasons=None,
                judge_call_id=None,
                wall_clock_ms=200,
            )
        )

        portfolio = PortfolioBrief(
            run_id=run_id,
            macro=PortfolioMacroSummary(
                themes=[],
                watch_items=[],
                confidence=0.5,
                judge_status=JudgeStatus.passed,
            ),
            sectors=[],
            companies=[],
            cited_claims=[],
            cited_chunk_ids=[],
            coverage=PortfolioCoverage(
                sectors_selected=1,
                sectors_verified=1,
                sectors_judge_passed=1,
                sectors_judge_flagged=0,
                companies_selected=1,
                companies_verified=1,
                companies_judge_passed=1,
                companies_judge_flagged=0,
            ),
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
        )
        setup.add(
            PortfolioBriefRow(
                run_id=run_id,
                payload=portfolio.model_dump(mode="json"),
                verifier_status="verified",
                regeneration_count=0,
                judge_status="passed",
                judge_reasons=None,
                judge_call_id=None,
                wall_clock_ms=42,
            )
        )
        await setup.commit()

    fred_payload = FredSeriesObservations(
        series_id="CPIAUCSL",
        observation_start=date(2025, 1, 1),
        observation_end=date(2026, 1, 1),
        count=1,
        observations=[
            FredObservation(
                date=date(2026, 1, 1),
                value=Decimal("310.0"),
                realtime_start=date(2026, 1, 15),
                realtime_end=date(2026, 12, 31),
            )
        ],
    )
    fetcher = SourceFetcher(
        fred=lambda client, series_id: (fred_payload, "a" * 64),
        polymarket=lambda client, limit: ([], "b" * 64),
        kalshi=lambda client, limit: ([], "c" * 64),
        congress=lambda client, limit: ([], "d" * 64),
        tiingo_news=lambda client, limit: ([], "e" * 64),
    )

    class _AssertionLlm:
        async def complete(self, **_: Any) -> LlmCompletionResult:
            raise AssertionError(
                "no llm call expected when all stages already persisted"
            )

    orchestrator = RunOrchestrator(
        session_factory=session_factory, adapter=TradingAgentsAdapter()
    )

    async with httpx.AsyncClient() as http_client:
        await run_macro_brief(
            session_factory=session_factory,
            run_id=run_id,
            llm_client=_AssertionLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
            fetcher=fetcher,
            sector_constituents={},
        )

    async with session_factory() as session:
        loaded = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
        ).scalar_one()
        assert loaded.status == RunStatus.succeeded

        macro_rows = (
            await session.execute(
                select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
            )
        ).scalars().all()
        sector_rows = (
            await session.execute(
                select(SectorBriefRow).where(SectorBriefRow.run_id == run_id)
            )
        ).scalars().all()
        company_rows = (
            await session.execute(
                select(CompanyThesisRow).where(CompanyThesisRow.run_id == run_id)
            )
        ).scalars().all()
        portfolio_rows = (
            await session.execute(
                select(PortfolioBriefRow).where(PortfolioBriefRow.run_id == run_id)
            )
        ).scalars().all()
        events = (
            await session.execute(
                select(RunEvent).where(RunEvent.run_id == run_id)
            )
        ).scalars().all()

    assert len(macro_rows) == 1
    assert len(sector_rows) == 1
    assert len(company_rows) == 1
    assert len(portfolio_rows) == 1

    resumed_events = {
        (event.data or {}).get("event")
        for event in events
        if isinstance(event.data, dict)
    }
    assert "run_resumed" in resumed_events
    assert "portfolio_brief_resumed" in resumed_events


@pytest.mark.asyncio
async def test_run_macro_brief_resume_with_persisted_macro_skips_synthesis(
    initialized_schema: None,
) -> None:
    """A resumed funnel run with a persisted macro brief must not retry
    synthesis or duplicate the macro_briefs row.
    """
    from app.services.run_orchestrator import RunOrchestrator
    from app.services.strategies.funnel_research._ingest import SourceFetcher
    from app.services.strategies.funnel_research.core import run_macro_brief
    from app.trading_agents.adapter import TradingAgentsAdapter

    run_id = uuid.uuid4()
    async with session_factory() as setup:
        run = ResearchRun(
            id=run_id,
            ticker=None,
            trade_date=date(2026, 5, 18),
            strategy=Strategy.funnel_research.value,
            status=RunStatus.queued,
            config={},
            scope_payload={"kind": "macro", "universe": "us_equities"},
        )
        setup.add(run)
        await setup.flush()
        macro_row = MacroBriefRow(
            run_id=run_id,
            themes=[],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.5,
            verifier_status="verified",
            regeneration_count=0,
            evidence_ids=[],
            judge_status="passed",
            judge_reasons=None,
            judge_call_id=None,
        )
        setup.add(macro_row)
        await setup.commit()

    from app.services.source_clients.fred import (
        FredObservation,
        FredSeriesObservations,
    )

    fred_payload = FredSeriesObservations(
        series_id="CPIAUCSL",
        observation_start=date(2025, 1, 1),
        observation_end=date(2026, 1, 1),
        count=1,
        observations=[
            FredObservation(
                date=date(2026, 1, 1),
                value=Decimal("310.0"),
                realtime_start=date(2026, 1, 15),
                realtime_end=date(2026, 12, 31),
            )
        ],
    )
    fetcher = SourceFetcher(
        fred=lambda client, series_id: (fred_payload, "a" * 64),
        polymarket=lambda client, limit: ([], "b" * 64),
        kalshi=lambda client, limit: ([], "c" * 64),
        congress=lambda client, limit: ([], "d" * 64),
        tiingo_news=lambda client, limit: ([], "e" * 64),
    )

    class StubLlm:
        def __init__(self) -> None:
            self.synthesis_calls = 0
            self.judge_calls = 0

        async def complete(self, **kwargs: Any) -> LlmCompletionResult:
            messages = kwargs.get("messages", [])
            is_judge = any(
                "Brief kind:" in getattr(m, "content", "") for m in messages
            )
            if not is_judge:
                self.synthesis_calls += 1
                raise AssertionError(
                    "synthesis llm must not be called when macro brief is persisted"
                )
            self.judge_calls += 1
            session = kwargs["session"]
            log = LlmCallLog(
                id=uuid.uuid4(),
                run_id=kwargs.get("run_id"),
                model=kwargs.get("model", "gpt-5-mini"),
                prompt_hash="0" * 64,
                input_hash="0" * 64,
                input_tokens=10,
                output_tokens=10,
                cached_input_tokens=0,
                reasoning_tokens=0,
                cost_usd=Decimal("0.001"),
                latency_ms=10,
                status=LlmCallStatus.success,
                evidence_ids=None,
            )
            session.add(log)
            await session.flush()
            return LlmCompletionResult(
                content=json.dumps({"status": "passed", "reasons": []}),
                model=kwargs.get("model", "gpt-5-mini"),
                usage=TokenUsage(
                    input_tokens=10,
                    output_tokens=10,
                    cached_input_tokens=0,
                    reasoning_tokens=0,
                ),
                cost_usd=Decimal("0.001"),
                latency_ms=10,
                log_id=log.id,
            )

    llm = StubLlm()
    orchestrator = RunOrchestrator(
        session_factory=session_factory, adapter=TradingAgentsAdapter()
    )

    async with httpx.AsyncClient() as http_client:
        await run_macro_brief(
            session_factory=session_factory,
            run_id=run_id,
            llm_client=llm,
            orchestrator=orchestrator,
            http_client=http_client,
            fetcher=fetcher,
            sector_constituents={},
        )

    assert llm.synthesis_calls == 0
    assert llm.judge_calls == 1

    async with session_factory() as session:
        loaded = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
        ).scalar_one()
        assert loaded.status == RunStatus.succeeded

        macro_count = (
            await session.execute(
                select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
            )
        ).scalars().all()
        assert len(macro_count) == 1

        events = (
            await session.execute(
                select(RunEvent).where(RunEvent.run_id == run_id)
            )
        ).scalars().all()

    stage_names = [
        (event.data or {}).get("stage_name")
        for event in events
        if (event.data or {}).get("event") == "stage"
    ]
    assert "ingest" not in stage_names
    assert "synthesize" not in stage_names
    assert "verify" not in stage_names
    assert "portfolio_brief" in stage_names
    assert "consolidate" in stage_names
    assert "succeeded" in stage_names

    assert any(
        (event.data or {}).get("event") == "run_resumed"
        and (event.data or {}).get("stage") == "macro_brief"
        for event in events
    )


@pytest.mark.asyncio
async def test_run_macro_brief_invalid_llm_json_marks_run_failed(
    initialized_schema: None,
) -> None:
    """A synthesis call that returns non-JSON content must fail the run, not leave it running."""
    from app.services.run_orchestrator import RunOrchestrator
    from app.services.source_clients.fred import FredObservation, FredSeriesObservations
    from app.services.strategies.funnel_research import FunnelResearchError
    from app.services.strategies.funnel_research._ingest import SourceFetcher
    from app.services.strategies.funnel_research.core import run_macro_brief
    from app.trading_agents.adapter import TradingAgentsAdapter

    run_id = uuid.uuid4()
    async with session_factory() as setup:
        run = ResearchRun(
            id=run_id,
            ticker=None,
            trade_date=date(2026, 5, 18),
            strategy=Strategy.funnel_research.value,
            status=RunStatus.queued,
            config={},
            scope_payload={"kind": "macro", "universe": "us_equities"},
        )
        setup.add(run)
        await setup.commit()

    fred_payload = FredSeriesObservations(
        series_id="CPIAUCSL",
        observation_start=date(2025, 1, 1),
        observation_end=date(2026, 1, 1),
        count=1,
        observations=[
            FredObservation(
                date=date(2026, 1, 1),
                value=Decimal("310.0"),
                realtime_start=date(2026, 1, 15),
                realtime_end=date(2026, 12, 31),
            )
        ],
    )
    fetcher = SourceFetcher(
        fred=lambda client, series_id: (fred_payload, "a" * 64),
        polymarket=lambda client, limit: ([], "b" * 64),
        kalshi=lambda client, limit: ([], "c" * 64),
        congress=lambda client, limit: ([], "d" * 64),
        tiingo_news=lambda client, limit: ([], "e" * 64),
    )

    class StubLlm:
        async def complete(self, **kwargs: Any) -> LlmCompletionResult:
            return LlmCompletionResult(
                content="not json at all",
                model=kwargs.get("model", "gpt-5-mini"),
                usage=TokenUsage(
                    input_tokens=1,
                    output_tokens=1,
                    cached_input_tokens=0,
                    reasoning_tokens=0,
                ),
                cost_usd=Decimal("0.001"),
                latency_ms=10,
                log_id=uuid.uuid4(),
            )

    orchestrator = RunOrchestrator(
        session_factory=session_factory, adapter=TradingAgentsAdapter()
    )

    async with httpx.AsyncClient() as http_client:
        with pytest.raises(FunnelResearchError):
            await run_macro_brief(
                session_factory=session_factory,
                run_id=run_id,
                llm_client=StubLlm(),
                orchestrator=orchestrator,
                http_client=http_client,
                fetcher=fetcher,
            )

    async with session_factory() as session:
        loaded = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
        ).scalar_one()
        assert loaded.status == RunStatus.failed
        assert loaded.error_message and "synthesis" in loaded.error_message.lower()
