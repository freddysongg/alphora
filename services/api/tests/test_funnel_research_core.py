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
        assert "ingest" in stage_names and "succeeded" in stage_names


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
